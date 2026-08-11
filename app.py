from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Visão Executiva de Estoque",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

TABLE_NAME = "painel_estoque"

# Número de registros por requisição.
# 1000 é mais seguro para instalações Supabase/PostgREST
# que mantêm o limite padrão de retorno.
BATCH_SIZE = 1000

# Número de requisições simultâneas.
MAX_WORKERS = 6

COLUNAS_TEXTO = [
    "mes_referencia",
    "ano_referencia",
    "codigo_produto",
    "item_critico",
    "nome_local_estoque",
]

COLUNAS_NUMERICAS = [
    "valor_saldo_atual",
    "valor_entrada_compras",
    "valor_saida_cons_interno",
    "qtde_saldo_atual",
]

COLUNAS_SELECT = [
    "id",
    "valor_saldo_atual",
    "valor_entrada_compras",
    "valor_saida_cons_interno",
    "unidade_almoxarifado",
    "mes_referencia",
    "ano_referencia",
    "codigo_produto",
    "qtde_saldo_atual",
    "item_critico",
    "nome_local_estoque",
]


# ============================================================
# ESTADO DOS FILTROS
# ============================================================

if "f_unidades" not in st.session_state:
    st.session_state.f_unidades = []

if "f_meses" not in st.session_state:
    st.session_state.f_meses = []

if "f_anos" not in st.session_state:
    st.session_state.f_anos = []


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def conectar_supabase():
    """
    Cria uma única conexão reutilizável durante a sessão
    do Streamlit.
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    return create_client(url, key)


supabase = conectar_supabase()


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def limpar_valor(valor):
    """
    Normaliza valores que chegam do banco como string,
    float ou None.
    """
    if pd.isna(valor) or valor is None:
        return ""

    valor = str(valor).strip()

    if valor.endswith(".0"):
        valor = valor[:-2]

    return valor


def fmt_brl(valor):
    valor = float(valor or 0)

    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def fmt_int(valor):
    return f"{int(valor or 0):,}".replace(",", ".")


def fmt_x(valor):
    return (
        f"{float(valor or 0):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
        + "x"
    )


def fmt_mes(valor):
    return (
        f"{float(valor or 0):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def fmt_valor_milhoes(valor):
    valor = float(valor or 0)

    if abs(valor) >= 1e9:
        return f"R$ {valor / 1e9:.1f}B".replace(".", ",")

    if abs(valor) >= 1e6:
        return f"R$ {valor / 1e6:.1f}M".replace(".", ",")

    if abs(valor) >= 1e3:
        return f"R$ {valor / 1e3:.1f}K".replace(".", ",")

    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def chave_numerica(valor):
    try:
        return (0, int(valor))
    except (ValueError, TypeError):
        return (1, str(valor))


def somar_coluna(dataframe, coluna):
    if dataframe.empty or coluna not in dataframe.columns:
        return 0.0

    return (
        pd.to_numeric(dataframe[coluna], errors="coerce")
        .fillna(0.0)
        .sum()
    )


def periodo_label(df):
    """
    Cria a coluna de período no formato MM/AAAA.
    """
    df = df.copy()

    df["Periodo"] = (
        df["tmp_mes_num"]
        .astype(int)
        .astype(str)
        .str.zfill(2)
        + "/"
        + df["ano_referencia"].astype(str)
    )

    return df


# ============================================================
# CARREGAMENTO DO SUPABASE
# ============================================================

def buscar_lote(start_row, end_row):
    """
    Busca um lote específico.
    """

    response = (
        supabase
        .table(TABLE_NAME)
        .select(",".join(COLUNAS_SELECT))
        .order("id")
        .range(start_row, end_row)
        .execute()
    )

    return response.data or []


@st.cache_data(show_spinner=False, ttl=900)
def carregar_dados():
    """
    Carrega a base do Supabase em lotes paralelos.

    TTL de 15 minutos:
    evita consultar toda a base a cada interação do usuário.
    """

    try:
        # --------------------------------------------------------
        # Descobre quantidade de registros
        # --------------------------------------------------------

        count_response = (
            supabase
            .table(TABLE_NAME)
            .select("id", count="exact", head=True)
            .execute()
        )

        total_rows = count_response.count

        if not total_rows:
            return pd.DataFrame()

        # --------------------------------------------------------
        # Cria ranges
        # --------------------------------------------------------

        ranges = [
            (
                inicio,
                min(inicio + BATCH_SIZE - 1, total_rows - 1),
            )
            for inicio in range(0, total_rows, BATCH_SIZE)
        ]

        dados = []

        progress_placeholder = st.empty()

        # --------------------------------------------------------
        # Busca paralela
        # --------------------------------------------------------

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

            futures = {
                executor.submit(
                    buscar_lote,
                    inicio,
                    fim,
                ): (inicio, fim)
                for inicio, fim in ranges
            }

            total_lotes = len(futures)
            lotes_processados = 0

            for future in as_completed(futures):

                inicio, fim = futures[future]

                try:
                    lote = future.result()

                    if lote:
                        dados.extend(lote)

                except Exception as erro:
                    st.warning(
                        f"Falha ao carregar registros {inicio}-{fim}: {erro}"
                    )

                lotes_processados += 1

                progresso = lotes_processados / total_lotes

                progress_placeholder.progress(
                    progresso,
                    text=(
                        f"Carregando base: "
                        f"{lotes_processados}/{total_lotes} lotes"
                    ),
                )

        progress_placeholder.empty()

        if not dados:
            return pd.DataFrame()

        # --------------------------------------------------------
        # DataFrame
        # --------------------------------------------------------

        df = pd.DataFrame(dados)

        # --------------------------------------------------------
        # Normalização
        # --------------------------------------------------------

        if "unidade_almoxarifado" in df.columns:
            df["unidade_almoxarifado"] = (
                df["unidade_almoxarifado"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

        for coluna in COLUNAS_TEXTO:

            if coluna in df.columns:
                df[coluna] = df[coluna].apply(limpar_valor)

        for coluna in COLUNAS_NUMERICAS:

            if coluna in df.columns:
                df[coluna] = (
                    pd.to_numeric(
                        df[coluna],
                        errors="coerce",
                    )
                    .fillna(0.0)
                )

        # --------------------------------------------------------
        # Auxiliares temporários
        # --------------------------------------------------------

        df["tmp_ano_num"] = (
            pd.to_numeric(
                df["ano_referencia"],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

        df["tmp_mes_num"] = (
            pd.to_numeric(
                df["mes_referencia"],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

        # --------------------------------------------------------
        # Flags utilizadas em vários cálculos
        # --------------------------------------------------------

        df["is_critico"] = (
            df["item_critico"] == "1-Sim"
        )

        df["is_obsoleto"] = (
            df["nome_local_estoque"]
            .astype(str)
            .str.contains(
                "obsoleto",
                case=False,
                na=False,
            )
        )

        df["is_obra"] = (
            df["nome_local_estoque"]
            .astype(str)
            .str.contains(
                "obra",
                case=False,
                na=False,
            )
        )

        df["consumo_abs"] = (
            df["valor_saida_cons_interno"]
            .abs()
        )

        return df

    except Exception as erro:

        st.error(
            f"Erro ao carregar dados do Supabase: {erro}"
        )

        return pd.DataFrame()


# ============================================================
# CARREGA BASE
# ============================================================

with st.spinner(
    "Carregando e normalizando base de dados..."
):
    df_completo = carregar_dados()


# ============================================================
# IDENTIFICAÇÃO DO ÚLTIMO PERÍODO
# ============================================================

if not df_completo.empty:

    max_ano_base = int(
        df_completo["tmp_ano_num"].max()
    )

    max_mes_base = int(
        df_completo[
            df_completo["tmp_ano_num"] == max_ano_base
        ]["tmp_mes_num"].max()
    )

else:

    max_ano_base = 2026
    max_mes_base = 7


# ============================================================
# OPÇÕES DOS FILTROS
# ============================================================

if not df_completo.empty:

    unidades_opcoes = sorted(
        df_completo[
            "unidade_almoxarifado"
        ]
        .dropna()
        .unique()
        .tolist()
    )

else:

    unidades_opcoes = []


unidades_gerenciais = [
    unidade
    for unidade in unidades_opcoes
    if "GERENCIAL" in unidade
]

unidades_ativas = [
    unidade
    for unidade in unidades_opcoes
    if "GERENCIAL" not in unidade
]


dict_meses_nome = {
    "1": "01 - Janeiro",
    "01": "01 - Janeiro",
    "2": "02 - Fevereiro",
    "02": "02 - Fevereiro",
    "3": "03 - Março",
    "03": "03 - Março",
    "4": "04 - Abril",
    "04": "04 - Abril",
    "5": "05 - Maio",
    "05": "05 - Maio",
    "6": "06 - Junho",
    "06": "06 - Junho",
    "7": "07 - Julho",
    "07": "07 - Julho",
    "8": "08 - Agosto",
    "08": "08 - Agosto",
    "9": "09 - Setembro",
    "09": "09 - Setembro",
    "10": "10 - Outubro",
    "11": "11 - Novembro",
    "12": "12 - Dezembro",
}


if not df_completo.empty:

    raw_meses = sorted(
        df_completo[
            "mes_referencia"
        ]
        .dropna()
        .unique()
        .tolist(),
        key=chave_numerica,
    )

else:

    raw_meses = []


map_raw_para_fmt = {
    mes: dict_meses_nome.get(
        str(mes).strip(),
        f"{str(mes).strip().zfill(2)} - Mês {mes}",
    )
    for mes in raw_meses
}

map_fmt_para_raw = {
    valor: chave
    for chave, valor in map_raw_para_fmt.items()
}

meses_opcoes_formatadas = list(
    map_raw_para_fmt.values()
)


if not df_completo.empty:

    ano_opcoes = sorted(
        df_completo[
            "ano_referencia"
        ]
        .dropna()
        .unique()
        .tolist(),
        key=chave_numerica,
    )

else:

    ano_opcoes = []


# ============================================================
# MODAL DE FILTROS
# ============================================================

@st.dialog(
    "Filtros de Análise - Visão Executiva",
    width="large",
)
def modal_filtros():

    st.markdown(
        """
        <p style="
            color: #8c9ba5;
            font-size: 13px;
            margin-bottom: 20px;
        ">
        Selecione uma ou mais opções para consolidar os dados.
        Deixe em branco para considerar todas.
        </p>
        """,
        unsafe_allow_html=True,
    )

    col_u1, col_u2 = st.columns(2)

    with col_u1:

        default_ativas = [
            unidade
            for unidade in st.session_state.f_unidades
            if unidade in unidades_ativas
        ]

        f_ativas_sel = st.multiselect(
            "🏢 Unidades Ativas",
            unidades_ativas,
            default=default_ativas,
        )

    with col_u2:

        default_gerenciais = [
            unidade
            for unidade in st.session_state.f_unidades
            if unidade in unidades_gerenciais
        ]

        f_gerenciais_sel = st.multiselect(
            "📊 Unidades Gerenciais",
            unidades_gerenciais,
            default=default_gerenciais,
        )

    f_unidades_sel = (
        f_ativas_sel + f_gerenciais_sel
    )

    default_meses_fmt = [
        map_raw_para_fmt[mes]
        for mes in st.session_state.f_meses
        if mes in map_raw_para_fmt
    ]

    f_meses_sel_fmt = st.multiselect(
        "Meses de Referência",
        meses_opcoes_formatadas,
        default=default_meses_fmt,
    )

    f_anos_sel = st.multiselect(
        "Anos de Referência",
        ano_opcoes,
        default=st.session_state.f_anos,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    col_btn1, col_btn2 = st.columns(2)

    with col_btn1:

        if st.button(
            "Limpar Filtros",
            use_container_width=True,
        ):

            st.session_state.f_unidades = []
            st.session_state.f_meses = []
            st.session_state.f_anos = []

            st.rerun()

    with col_btn2:

        if st.button(
            "Aplicar Filtros",
            use_container_width=True,
            type="primary",
        ):

            st.session_state.f_unidades = (
                f_unidades_sel
            )

            st.session_state.f_meses = [
                map_fmt_para_raw[mes]
                for mes in f_meses_sel_fmt
            ]

            st.session_state.f_anos = (
                f_anos_sel
            )

            st.rerun()


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>

@keyframes smoothPageLoad {
    0% {
        opacity: 0.2;
        transform: scale(0.98);
    }

    100% {
        opacity: 1;
        transform: scale(1);
    }
}

.stApp {
    background-color: #0f141c;
    animation:
        smoothPageLoad
        0.5s
        cubic-bezier(0.16, 1, 0.3, 1)
        forwards !important;
}

@keyframes scaleInModal {

    0% {
        opacity: 0;
        transform:
            scale(0.8)
            translateY(-20px);
    }

    100% {
        opacity: 1;
        transform:
            scale(1)
            translateY(0);
    }
}

@keyframes fadeInScrim {

    0% {
        opacity: 0;
        backdrop-filter: blur(0px);
    }

    100% {
        opacity: 1;
        backdrop-filter: blur(5px);
    }
}

div[role="dialog"],
div[data-testid="stDialog"] {

    animation:
        scaleInModal
        0.6s
        cubic-bezier(0.16, 1, 0.3, 1)
        forwards !important;

    transform-origin:
        center center;
}

div[data-testid="stModalScrim"] {

    background-color:
        rgba(15, 20, 28, 0.7) !important;

    animation:
        fadeInScrim
        0.6s
        ease-out
        forwards !important;
}

.stButton > button {

    background-color: #1a222d !important;
    color: #ffffff !important;
    border: 1px solid #333d4d !important;
    border-radius: 6px !important;
    transition: all 0.3s ease;
}

.stButton > button:hover {

    border-color: #d85c27 !important;
    color: #d85c27 !important;
}

.header-container {

    display: flex;
    align-items: center;

    border-bottom:
        2px solid #d85c27;

    padding-bottom: 12px;
    margin-bottom: 20px;

    gap: 20px;
}

.logo-container {

    background-color: #ffffff;

    padding:
        6px 16px;

    border-radius: 4px;

    text-align: center;

    font-family:
        Arial,
        sans-serif;
}

.logo-main {

    color: #12161f;

    font-weight: 900;

    font-size: 18px;

    line-height: 1;
}

.logo-sub {

    color: #d85c27;

    font-size: 9px;

    font-weight: bold;

    letter-spacing: 1px;
}

.title-container {

    border-left:
        1px solid #333d4d;

    padding-left: 15px;
}

.title-main {

    color: #ffffff;

    font-size: 18px;

    font-weight: bold;

    letter-spacing: 1px;

    margin: 0;
}

.title-sub {

    color: #8c9ba5;

    font-size: 12px;

    margin: 0;
}

.card-box {

    background-color: #161c24;

    border:
        1px solid #232b36;

    border-radius: 8px;

    padding: 16px;

    min-height: 130px;

    height: auto;

    display: flex;

    flex-direction: column;

    justify-content: space-between;

    box-shadow:
        0 10px 20px rgba(0, 0, 0, 0.5),
        0 4px 8px rgba(0, 0, 0, 0.3);

    transition:
        all
        0.3s
        cubic-bezier(
            0.25,
            0.8,
            0.25,
            1
        );
}

.card-box:hover {

    transform:
        translateY(-5px);

    box-shadow:
        0 15px 30px rgba(0, 0, 0, 0.8),
        0 5px 15px
        rgba(216, 92, 39, 0.15);

    border-color: #333d4d;
}

div[data-testid="stContainer"] {

    background-color:
        #161c24 !important;

    border:
        1px solid #232b36 !important;

    border-radius:
        8px !important;

    padding:
        20px !important;

    box-shadow:
        0 15px 30px
        rgba(0, 0, 0, 0.8) !important;

    overflow:
        visible !important;

    transition:
        all
        0.3s
        cubic-bezier(
            0.25,
            0.8,
            0.25,
            1
        );
}

div[data-testid="stContainer"]:hover {

    transform:
        translateY(-4px);

    box-shadow:
        0 20px 35px
        rgba(0, 0, 0, 0.85),
        0 8px 20px
        rgba(216, 92, 39, 0.2) !important;

    border-color:
        #333d4d !important;
}

.card-header {

    display: flex;

    align-items: center;

    gap: 12px;
}

.icon-box {

    width: 32px;
    height: 32px;

    border-radius: 6px;

    display: flex;

    align-items: center;

    justify-content: center;

    font-size: 14px;
}

.icon-estoque {

    background-color: #132a24;
    color: #2ecc71;
}

.icon-critico {

    background-color: #2a1515;
    color: #e74c3c;
}

.icon-obsoleto {

    background-color: #2a2a2a;
    color: #9b59b6;
}

.icon-obra {

    background-color: #1a2a2a;
    color: #1abc9c;
}

.icon-skus {

    background-color: #1a222d;
    color: #3498db;
}

.icon-giro {

    background-color: #221a2d;
    color: #9b59b6;
}

.icon-cobertura {

    background-color: #2a2211;
    color: #e67e22;
}

.card-title {

    color: #8c9ba5;

    font-size: 11px;

    font-weight: bold;

    letter-spacing: 0.5px;
}

.card-value {

    color: #ffffff;

    font-size: 21px;

    font-weight: bold;

    text-align: center;

    font-family: monospace;

    margin-top: 8px;
}

.section-title {

    color: #ffffff;

    font-size: 14px;

    font-weight: bold;

    margin-bottom: 12px;

    letter-spacing: 0.5px;

    border-left:
        3px solid #d85c27;

    padding-left: 10px;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CABEÇALHO
# ============================================================

col_header, col_btn = st.columns([5, 1])

with col_header:

    st.markdown(
        """
        <div class="header-container">

            <div class="logo-container">

                <div class="logo-main">
                    Âmbar
                </div>

                <div class="logo-sub">
                    ENERGIA
                </div>

            </div>

            <div class="title-container">

                <div class="title-main">
                    VISÃO EXECUTIVA DE ESTOQUE
                </div>

                <div class="title-sub">
                    Valores Consolidados
                </div>

            </div>

        </div>
        """,
        unsafe_allow_html=True,
    )


with col_btn:

    st.markdown(
        "<br>",
        unsafe_allow_html=True,
    )

    filtro_ativo = bool(
        st.session_state.f_unidades
        or st.session_state.f_meses
        or st.session_state.f_anos
    )

    label_botao = (
        "⚙️ Filtros (Ativo)"
        if filtro_ativo
        else "⚙️ Filtros"
    )

    if st.button(
        label_botao,
        use_container_width=True,
    ):
        modal_filtros()


# ============================================================
# RESUMO DOS FILTROS
# ============================================================

f_unidades_atuais = (
    st.session_state.f_unidades
)

if not f_unidades_atuais:

    texto_informativo = (
        "Exibindo dados consolidados de "
        "**todas as unidades** "
        "(Ativas e Gerenciais)."
    )

else:

    sel_ativas = [
        unidade
        for unidade in f_unidades_atuais
        if unidade in unidades_ativas
    ]

    sel_gerenciais = [
        unidade
        for unidade in f_unidades_atuais
        if unidade in unidades_gerenciais
    ]

    partes = []

    if sel_ativas:

        partes.append(
            f"**{len(sel_ativas)} unidade(s) ativa(s)**"
        )

    if sel_gerenciais:

        partes.append(
            f"**{len(sel_gerenciais)} gerencial(is)**"
        )

    texto_informativo = (
        "Exibindo dados de "
        + " e ".join(partes)
        + "."
    )


st.markdown(
    f"""
    <p style="
        color: #8c9ba5;
        font-size: 14px;
        margin-top: -10px;
        margin-bottom: 20px;
    ">
        {texto_informativo}
    </p>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FILTRAGEM
# ============================================================

df_filtrado = df_completo.copy()

if st.session_state.f_unidades:

    df_filtrado = df_filtrado[
        df_filtrado[
            "unidade_almoxarifado"
        ].isin(
            st.session_state.f_unidades
        )
    ]


if st.session_state.f_meses:

    df_filtrado = df_filtrado[
        df_filtrado[
            "mes_referencia"
        ].isin(
            st.session_state.f_meses
        )
    ]


if st.session_state.f_anos:

    df_filtrado = df_filtrado[
        df_filtrado[
            "ano_referencia"
        ].isin(
            st.session_state.f_anos
        )
    ]


# ============================================================
# SNAPSHOT
# ============================================================

df_snapshot = df_filtrado.copy()

if not st.session_state.f_meses:

    if st.session_state.f_anos:

        anos_sel_num = [
            int(ano)
            for ano in st.session_state.f_anos
        ]

        df_anos_sel = df_snapshot[
            df_snapshot["tmp_ano_num"].isin(
                anos_sel_num
            )
        ]

        if not df_anos_sel.empty:

            ano_snapshot = int(
                df_anos_sel[
                    "tmp_ano_num"
                ].max()
            )

            mes_snapshot = int(
                df_anos_sel[
                    df_anos_sel["tmp_ano_num"]
                    == ano_snapshot
                ]["tmp_mes_num"].max()
            )

            df_snapshot = df_snapshot[
                (
                    df_snapshot["tmp_ano_num"]
                    == ano_snapshot
                )
                &
                (
                    df_snapshot["tmp_mes_num"]
                    == mes_snapshot
                )
            ]

    else:

        df_snapshot = df_snapshot[
            (
                df_snapshot["tmp_ano_num"]
                == max_ano_base
            )
            &
            (
                df_snapshot["tmp_mes_num"]
                == max_mes_base
            )
        ]


# ============================================================
# INDICADORES
# ============================================================

val_estoque = somar_coluna(
    df_snapshot,
    "valor_saldo_atual",
)


# ------------------------------------------------------------
# SKUs
# ------------------------------------------------------------

if (
    not df_snapshot.empty
    and "qtde_saldo_atual" in df_snapshot.columns
    and "codigo_produto" in df_snapshot.columns
):

    df_skus_ativos = df_snapshot[
        (
            df_snapshot["qtde_saldo_atual"] > 0
        )
        &
        (
            df_snapshot["codigo_produto"] != ""
        )
    ]

    val_skus = (
        df_skus_ativos[
            "codigo_produto"
        ].nunique()
    )

else:

    val_skus = 0


# ------------------------------------------------------------
# CRÍTICO
# ------------------------------------------------------------

if not df_snapshot.empty:

    val_critico = somar_coluna(
        df_snapshot[
            df_snapshot["is_critico"]
        ],
        "valor_saldo_atual",
    )

else:

    val_critico = 0.0


# ------------------------------------------------------------
# OBSOLETO
# ------------------------------------------------------------

if not df_snapshot.empty:

    val_obsoleto = somar_coluna(
        df_snapshot[
            df_snapshot["is_obsoleto"]
        ],
        "valor_saldo_atual",
    )

else:

    val_obsoleto = 0.0


# ------------------------------------------------------------
# OBRA
# ------------------------------------------------------------

if not df_snapshot.empty:

    val_obra = somar_coluna(
        df_snapshot[
            df_snapshot["is_obra"]
        ],
        "valor_saldo_atual",
    )

else:

    val_obra = 0.0


# ============================================================
# GIRO E COBERTURA
# ============================================================

giro_mensal = 0.0
giro_anual = 0.0
cobertura_meses = 0.0
cobertura_anos = 0.0


if not df_filtrado.empty:

    df_giro = df_filtrado.copy()

    # --------------------------------------------------------
    # Estoque operacional
    # Exclui crítico e obsoleto
    # --------------------------------------------------------

    df_giro["estoque_operacional"] = (
        df_giro["valor_saldo_atual"]
    ).where(
        ~(
            df_giro["is_critico"]
            |
            df_giro["is_obsoleto"]
        ),
        0.0,
    )

    # --------------------------------------------------------
    # Consumo operacional
    # --------------------------------------------------------

    df_giro["consumo_operacional"] = (
        df_giro["consumo_abs"]
    ).where(
        ~(
            df_giro["is_critico"]
            |
            df_giro["is_obsoleto"]
        ),
        0.0,
    )

    # --------------------------------------------------------
    # Agrupamento mensal
    # --------------------------------------------------------

    monthly_df = (
        df_giro
        .groupby(
            [
                "tmp_ano_num",
                "tmp_mes_num",
            ],
            as_index=False,
        )
        .agg(
            estoque_op=(
                "estoque_operacional",
                "sum",
            ),
            consumo_op=(
                "consumo_operacional",
                "sum",
            ),
        )
    )

    if not monthly_df.empty:

        estoque_medio_op = (
            monthly_df["estoque_op"].mean()
        )

        consumo_medio_mensal = (
            monthly_df["consumo_op"].mean()
        )

        if estoque_medio_op > 0:

            giro_mensal = (
                consumo_medio_mensal
                / estoque_medio_op
            )

            giro_anual = (
                giro_mensal * 12
            )

        if consumo_medio_mensal > 0:

            cobertura_meses = (
                estoque_medio_op
                / consumo_medio_mensal
            )

            cobertura_anos = (
                cobertura_meses / 12
            )


# ============================================================
# ABAS
# ============================================================

aba_geral, aba_detalhada = st.tabs(
    [
        "📈 Visão Geral",
        "📊 Análises Detalhadas & Tendência de Estoque",
    ]
)


# ============================================================
# ABA GERAL
# ============================================================

with aba_geral:

    # ========================================================
    # TENDÊNCIA
    # ========================================================

    @st.fragment
    def render_grafico_tendencia(df_f):

        if df_f.empty:
            return

        with st.container(border=True):

            col_titulo, col_filtro = st.columns(
                [3, 2]
            )

            with col_titulo:

                st.markdown(
                    """
                    <div style="
                        color: #ffffff;
                        font-size: 14px;
                        font-weight: bold;
                        margin-bottom: 5px;
                        border-left: 3px solid #d85c27;
                        padding-left: 10px;
                    ">
                        📊 TENDÊNCIA:
                        TOTAL VS CRÍTICO VS OBSOLETO VS OBRA
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col_filtro:

                unidades_disponiveis_grafico = sorted(
                    df_f[
                        "unidade_almoxarifado"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )

                filtro_unidade_chart = (
                    st.multiselect(
                        "Filtrar Unidades no Gráfico:",
                        unidades_disponiveis_grafico,
                        default=[],
                        key="local_chart_filter",
                        placeholder=(
                            "Todas as unidades filtradas"
                        ),
                    )
                )

            df_chart_base = df_f.copy()

            if filtro_unidade_chart:

                df_chart_base = df_chart_base[
                    df_chart_base[
                        "unidade_almoxarifado"
                    ].isin(
                        filtro_unidade_chart
                    )
                ]

            if df_chart_base.empty:
                st.info(
                    "Nenhum dado disponível "
                    "para as unidades selecionadas."
                )
                return

            # ------------------------------------------------
            # ESTOQUE TOTAL
            # ------------------------------------------------

            df_estoque_mes = (
                df_chart_base
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False,
                )["valor_saldo_atual"]
                .sum()
            )

            df_estoque_mes = (
                df_estoque_mes
                .sort_values(
                    [
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ]
                )
                .reset_index(drop=True)
            )

            df_estoque_mes = periodo_label(
                df_estoque_mes
            )

            # ------------------------------------------------
            # CRÍTICO
            # ------------------------------------------------

            df_critico_mes = (
                df_chart_base[
                    df_chart_base["is_critico"]
                ]
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False,
                )["valor_saldo_atual"]
                .sum()
            )

            df_critico_mes = (
                df_critico_mes
                .sort_values(
                    [
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ]
                )
            )

            df_critico_mes = periodo_label(
                df_critico_mes
            )

            # ------------------------------------------------
            # OBSOLETO
            # ------------------------------------------------

            df_obsoleto_mes = (
                df_chart_base[
                    df_chart_base["is_obsoleto"]
                ]
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False,
                )["valor_saldo_atual"]
                .sum()
            )

            df_obsoleto_mes = (
                df_obsoleto_mes
                .sort_values(
                    [
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ]
                )
            )

            df_obsoleto_mes = periodo_label(
                df_obsoleto_mes
            )

            # ------------------------------------------------
            # OBRA
            # ------------------------------------------------

            df_obra_mes = (
                df_chart_base[
                    df_chart_base["is_obra"]
                ]
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False,
                )["valor_saldo_atual"]
                .sum()
            )

            df_obra_mes = (
                df_obra_mes
                .sort_values(
                    [
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ]
                )
            )

            df_obra_mes = periodo_label(
                df_obra_mes
            )

            # ------------------------------------------------
            # LABELS
            # ------------------------------------------------

            df_estoque_mes["texto_labels"] = (
                df_estoque_mes[
                    "valor_saldo_atual"
                ].apply(
                    fmt_valor_milhoes
                )
            )

            for dataframe in [
                df_critico_mes,
                df_obsoleto_mes,
                df_obra_mes,
            ]:

                if not dataframe.empty:

                    dataframe["texto_labels"] = (
                        dataframe[
                            "valor_saldo_atual"
                        ].apply(
                            fmt_valor_milhoes
                        )
                    )

            max_y_est = (
                df_estoque_mes[
                    "valor_saldo_atual"
                ].max()
                if not df_estoque_mes.empty
                else 100
            )

            n_pontos_est = len(
                df_estoque_mes
            )

            # ------------------------------------------------
            # FIGURA
            # ------------------------------------------------

            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=df_estoque_mes["Periodo"],
                    y=df_estoque_mes[
                        "valor_saldo_atual"
                    ],
                    name="Estoque Total",
                    mode="lines+markers+text",
                    text=df_estoque_mes[
                        "texto_labels"
                    ],
                    textposition="top center",
                    textfont=dict(
                        color="white",
                        size=11,
                    ),
                    line=dict(
                        color="#e74c3c",
                        width=3,
                    ),
                    marker=dict(
                        size=8,
                        color="#e74c3c",
                        line=dict(
                            color="#ffffff",
                            width=2,
                        ),
                    ),
                    fill="tozeroy",
                    fillcolor=(
                        "rgba(231,76,60,0.08)"
                    ),
                    hoverinfo="none",
                )
            )

            if not df_critico_mes.empty:

                fig.add_trace(
                    go.Scatter(
                        x=df_critico_mes[
                            "Periodo"
                        ],
                        y=df_critico_mes[
                            "valor_saldo_atual"
                        ],
                        name="Estoque Crítico",
                        mode="lines+markers+text",
                        text=df_critico_mes[
                            "texto_labels"
                        ],
                        textposition="bottom center",
                        textfont=dict(
                            color="#f39c12",
                            size=11,
                        ),
                        line=dict(
                            color="#f39c12",
                            width=2.5,
                            dash="dash",
                        ),
                        marker=dict(
                            size=6,
                            color="#f39c12",
                            line=dict(
                                color="#ffffff",
                                width=1,
                            ),
                        ),
                        visible="legendonly",
                        hoverinfo="none",
                    )
                )

            if not df_obsoleto_mes.empty:

                fig.add_trace(
                    go.Scatter(
                        x=df_obsoleto_mes[
                            "Periodo"
                        ],
                        y=df_obsoleto_mes[
                            "valor_saldo_atual"
                        ],
                        name="Estoque Obsoleto",
                        mode="lines+markers+text",
                        text=df_obsoleto_mes[
                            "texto_labels"
                        ],
                        textposition="top center",
                        textfont=dict(
                            color="#9b59b6",
                            size=11,
                        ),
                        line=dict(
                            color="#9b59b6",
                            width=2.5,
                            dash="dot",
                        ),
                        marker=dict(
                            size=6,
                            color="#9b59b6",
                            line=dict(
                                color="#ffffff",
                                width=1,
                            ),
                        ),
                        visible="legendonly",
                        hoverinfo="none",
                    )
                )

            if not df_obra_mes.empty:

                fig.add_trace(
                    go.Scatter(
                        x=df_obra_mes[
                            "Periodo"
                        ],
                        y=df_obra_mes[
                            "valor_saldo_atual"
                        ],
                        name="Estoque Obra",
                        mode="lines+markers+text",
                        text=df_obra_mes[
                            "texto_labels"
                        ],
                        textposition="bottom center",
                        textfont=dict(
                            color="#1abc9c",
                            size=11,
                        ),
                        line=dict(
                            color="#1abc9c",
                            width=2.5,
                            dash="longdash",
                        ),
                        marker=dict(
                            size=6,
                            color="#1abc9c",
                            line=dict(
                                color="#ffffff",
                                width=1,
                            ),
                        ),
                        visible="legendonly",
                        hoverinfo="none",
                    )
                )

            # ------------------------------------------------
            # HOLOFOTE VERTICAL
            # ------------------------------------------------

            sel_state = st.session_state.get(
                "tendencia_geral",
                {},
            )

            pontos_clicados = []

            if isinstance(sel_state, dict):

                pontos_clicados = (
                    sel_state
                    .get("selection", {})
                    .get("points", [])
                )

            if pontos_clicados:

                x_hl = pontos_clicados[0].get(
                    "x"
                )

                if x_hl:

                    indices = (
                        df_estoque_mes.index[
                            df_estoque_mes[
                                "Periodo"
                            ]
                            == x_hl
                        ]
                        .tolist()
                    )

                    if indices:

                        idx = indices[0]

                        fig.add_shape(
                            type="rect",
                            x0=idx - 0.45,
                            x1=idx + 0.45,
                            y0=0,
                            y1=1,
                            yref="paper",
                            fillcolor=(
                                "rgba(216,92,39,0.18)"
                            ),
                            line=dict(
                                width=1.5,
                                color=(
                                    "rgba(216,92,39,0.6)"
                                ),
                            ),
                            layer="below",
                        )

            # ------------------------------------------------
            # LAYOUT
            # ------------------------------------------------

            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(
                    color="#8c9ba5"
                ),
                margin=dict(
                    l=10,
                    r=10,
                    t=50,
                    b=30,
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
                hovermode=False,
                showlegend=True,
            )

            fig.update_xaxes(
                showgrid=False,
                zeroline=False,
                range=[
                    -0.8,
                    n_pontos_est - 0.2,
                ],
            )

            fig.update_yaxes(
                showgrid=True,
                gridcolor="#232b36",
                zeroline=False,
                range=[
                    -max_y_est * 0.08,
                    max_y_est * 1.3,
                ],
                showticklabels=False,
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "displayModeBar": False
                },
                on_select="rerun",
                selection_mode="points",
                key="tendencia_geral",
            )

    render_grafico_tendencia(
        df_filtrado
    )

    st.markdown("<br>", unsafe_allow_html=True)


    # ========================================================
    # LINHA FINANCEIRA
    # ========================================================

    st.markdown(
        """
        <div class="section-title">
            💼 LINHA FINANCEIRA
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)


    with c1:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-estoque">
                        📦
                    </div>

                    <div class="card-title">
                        VALOR TOTAL EM ESTOQUE
                    </div>

                </div>

                <div class="card-value">
                    {fmt_brl(val_estoque)}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    with c2:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-critico">
                        ⚠️
                    </div>

                    <div class="card-title">
                        ESTOQUE CRÍTICO (1-SIM)
                    </div>

                </div>

                <div class="card-value">
                    {fmt_brl(val_critico)}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    with c3:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-obsoleto">
                        🗑️
                    </div>

                    <div class="card-title">
                        ESTOQUE OBSOLETO
                    </div>

                </div>

                <div class="card-value">
                    {fmt_brl(val_obsoleto)}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    with c4:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-obra">
                        🏗️
                    </div>

                    <div class="card-title">
                        ESTOQUE OBRA
                    </div>

                </div>

                <div class="card-value">
                    {fmt_brl(val_obra)}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    st.markdown("<br>", unsafe_allow_html=True)


    # ========================================================
    # LINHA OPERACIONAL
    # ========================================================

    st.markdown(
        """
        <div class="section-title">
            ⚙️ LINHA OPERACIONAL
        </div>
        """,
        unsafe_allow_html=True,
    )

    c5, c6, c7 = st.columns(3)


    with c5:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-skus">
                        🏷️
                    </div>

                    <div class="card-title">
                        TOTAL DE SKUs ÚNICOS
                    </div>

                </div>

                <div class="card-value">
                    {fmt_int(val_skus)}
                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    with c6:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-giro">
                        🔄
                    </div>

                    <div class="card-title">
                        GIRO DE ESTOQUE
                    </div>

                </div>

                <div style="
                    display: flex;
                    justify-content: space-around;
                    align-items: center;
                    margin-top: 8px;
                ">

                    <div style="
                        text-align: center;
                        flex: 1;
                    ">

                        <span style="
                            font-size: 10px;
                            color: #8c9ba5;
                            letter-spacing: 0.5px;
                        ">
                            MENSAL
                        </span>

                        <br>

                        <span style="
                            font-size: 20px;
                            font-weight: bold;
                            color: #ffffff;
                            font-family: monospace;
                        ">
                            {fmt_x(giro_mensal)}
                        </span>

                    </div>

                    <div style="
                        height: 35px;
                        width: 1px;
                        background-color: #232b36;
                    "></div>

                    <div style="
                        text-align: center;
                        flex: 1;
                    ">

                        <span style="
                            font-size: 10px;
                            color: #8c9ba5;
                            letter-spacing: 0.5px;
                        ">
                            ANUALIZADO
                        </span>

                        <br>

                        <span style="
                            font-size: 20px;
                            font-weight: bold;
                            color: #ffffff;
                            font-family: monospace;
                        ">
                            {fmt_x(giro_anual)}
                        </span>

                    </div>

                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    with c7:

        st.markdown(
            f"""
            <div class="card-box">

                <div class="card-header">

                    <div class="icon-box icon-cobertura">
                        ⏳
                    </div>

                    <div class="card-title">
                        COBERTURA DE ESTOQUE
                    </div>

                </div>

                <div style="
                    display: flex;
                    justify-content: space-around;
                    align-items: center;
                    margin-top: 8px;
                ">

                    <div style="
                        text-align: center;
                        flex: 1;
                    ">

                        <span style="
                            font-size: 10px;
                            color: #8c9ba5;
                            letter-spacing: 0.5px;
                        ">
                            MENSAL (MESES)
                        </span>

                        <br>

                        <span style="
                            font-size: 20px;
                            font-weight: bold;
                            color: #ffffff;
                            font-family: monospace;
                        ">
                            {fmt_mes(cobertura_meses)}
                        </span>

                    </div>

                    <div style="
                        height: 35px;
                        width: 1px;
                        background-color: #232b36;
                    "></div>

                    <div style="
                        text-align: center;
                        flex: 1;
                    ">

                        <span style="
                            font-size: 10px;
                            color: #8c9ba5;
                            letter-spacing: 0.5px;
                        ">
                            ANUALIZADO (ANOS)
                        </span>

                        <br>

                        <span style="
                            font-size: 20px;
                            font-weight: bold;
                            color: #ffffff;
                            font-family: monospace;
                        ">
                            {fmt_mes(cobertura_anos)}
                        </span>

                    </div>

                </div>

            </div>
            """,
            unsafe_allow_html=True,
        )


    # ========================================================
    # GRÁFICOS
    # ========================================================

    st.markdown(
        "<br>",
        unsafe_allow_html=True,
    )

    if not df_filtrado.empty:

        layout_transparente = dict(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(
                color="#8c9ba5"
            ),
            margin=dict(
                l=10,
                r=10,
                t=10,
                b=10,
            ),
        )

        col_g1, col_g2 = st.columns(
            [6, 4],
            gap="large",
        )


        # ====================================================
        # COMPRAS VS CONSUMO
        # ====================================================

        with col_g1:

            with st.container(border=True):

                st.markdown(
                    """
                    <div style="
                        color: #ffffff;
                        font-size: 14px;
                        font-weight: bold;
                        margin-bottom: 15px;
                        border-left: 3px solid #d85c27;
                        padding-left: 10px;
                    ">
                        📈 EVOLUÇÃO:
                        COMPRAS VS CONSUMO
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                df_tempo = (
                    df_filtrado
                    .groupby(
                        [
                            "ano_referencia",
                            "mes_referencia",
                            "tmp_ano_num",
                            "tmp_mes_num",
                        ],
                        as_index=False,
                    )[
                        [
                            "valor_entrada_compras",
                            "valor_saida_cons_interno",
                        ]
                    ]
                    .sum()
                )

                df_tempo = (
                    df_tempo
                    .sort_values(
                        [
                            "tmp_ano_num",
                            "tmp_mes_num",
                        ]
                    )
                )

                df_tempo = periodo_label(
                    df_tempo
                )

                df_tempo[
                    "valor_saida_cons_interno"
                ] = (
                    df_tempo[
                        "valor_saida_cons_interno"
                    ].abs()
                )

                fig_linha = go.Figure()

                fig_linha.add_trace(
                    go.Scatter(
                        x=df_tempo["Periodo"],
                        y=df_tempo[
                            "valor_entrada_compras"
                        ],
                        name="Compras",
                        mode="lines+markers",
                        line=dict(
                            color="#f39c12",
                            width=3,
                        ),
                    )
                )

                fig_linha.add_trace(
                    go.Scatter(
                        x=df_tempo["Periodo"],
                        y=df_tempo[
                            "valor_saida_cons_interno"
                        ],
                        name="Consumo",
                        mode="lines+markers",
                        line=dict(
                            color="#e74c3c",
                            width=3,
                        ),
                    )
                )

                fig_linha.update_layout(
                    **layout_transparente,
                    hovermode="x unified",
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.05,
                        xanchor="right",
                        x=1,
                    ),
                )

                fig_linha.update_xaxes(
                    showgrid=False,
                    zeroline=False,
                )

                fig_linha.update_yaxes(
                    showgrid=True,
                    gridcolor="#232b36",
                    zeroline=False,
                    tickprefix="R$ ",
                )

                st.plotly_chart(
                    fig_linha,
                    use_container_width=True,
                    config={
                        "displayModeBar": False
                    },
                    key="compras_consumo_geral",
                )


        # ====================================================
        # TOP 10
        # ====================================================

        with col_g2:

            with st.container(border=True):

                st.markdown(
                    """
                    <div style="
                        color: #ffffff;
                        font-size: 14px;
                        font-weight: bold;
                        margin-bottom: 15px;
                        border-left: 3px solid #d85c27;
                        padding-left: 10px;
                    ">
                        🏆 TOP 10:
                        MAIOR VALOR EM ESTOQUE
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                df_rank = (
                    df_snapshot
                    .groupby(
                        "unidade_almoxarifado",
                        as_index=False,
                    )[
                        "valor_saldo_atual"
                    ]
                    .sum()
                )

                df_rank = df_rank[
                    df_rank[
                        "valor_saldo_atual"
                    ] > 0
                ]

                df_rank = (
                    df_rank
                    .sort_values(
                        "valor_saldo_atual",
                        ascending=True,
                    )
                    .tail(10)
                )

                df_rank[
                    "texto_formatado"
                ] = (
                    df_rank[
                        "valor_saldo_atual"
                    ].apply(
                        fmt_valor_milhoes
                    )
                )

                fig_bar = px.bar(
                    df_rank,
                    x="valor_saldo_atual",
                    y="unidade_almoxarifado",
                    orientation="h",
                    color_discrete_sequence=[
                        "#e74c3c"
                    ],
                    text="texto_formatado",
                )

                fig_bar.update_layout(
                    **layout_transparente,
                    hovermode="y unified",
                )

                fig_bar.update_traces(
                    textposition="auto",
                    textfont=dict(
                        color="white"
                    ),
                )

                fig_bar.update_xaxes(
                    title="",
                    showgrid=True,
                    gridcolor="#232b36",
                    tickprefix="R$ ",
                    zeroline=False,
                )

                fig_bar.update_yaxes(
                    title="",
                    showgrid=False,
                )

                st.plotly_chart(
                    fig_bar,
                    use_container_width=True,
                    config={
                        "displayModeBar": False
                    },
                    key="top10_geral",
                )


        # ====================================================
        # EVOLUÇÃO DOS SKUs
        # ====================================================

        st.markdown(
            "<br>",
            unsafe_allow_html=True,
        )

        with st.container(border=True):

            st.markdown(
                """
                <div style="
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    margin-bottom: 15px;
                    border-left: 3px solid #d85c27;
                    padding-left: 10px;
                ">
                    📦 EVOLUÇÃO DO MIX:
                    TOTAL DE SKUs ATIVOS NO TEMPO
                </div>
                """,
                unsafe_allow_html=True,
            )

            df_sku_trend = df_filtrado[
                (
                    df_filtrado[
                        "qtde_saldo_atual"
                    ] > 0
                )
                &
                (
                    df_filtrado[
                        "codigo_produto"
                    ] != ""
                )
            ].copy()

            df_sku_tempo = (
                df_sku_trend
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False,
                )[
                    "codigo_produto"
                ]
                .nunique()
            )

            df_sku_tempo = (
                df_sku_tempo
                .sort_values(
                    [
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ]
                )
                .reset_index(drop=True)
            )

            df_sku_tempo = periodo_label(
                df_sku_tempo
            )

            textos_skus = [
                fmt_int(valor)
                for valor
                in df_sku_tempo[
                    "codigo_produto"
                ]
            ]

            max_y = (
                df_sku_tempo[
                    "codigo_produto"
                ].max()
                if not df_sku_tempo.empty
                else 100
            )

            n_pontos = len(
                df_sku_tempo
            )

            total_skus_grafico = (
                df_snapshot[
                    df_snapshot[
                        "qtde_saldo_atual"
                    ] > 0
                ]["codigo_produto"]
                .replace("", pd.NA)
                .dropna()
                .nunique()
            )

            total_formatado = fmt_int(
                total_skus_grafico
            )

            layout_sku = dict(

                plot_bgcolor="rgba(0,0,0,0)",

                paper_bgcolor="rgba(0,0,0,0)",

                font=dict(
                    color="#8c9ba5"
                ),

                margin=dict(
                    l=40,
                    r=40,
                    t=50,
                    b=10,
                ),

                annotations=[
                    dict(
                        x=1.0,
                        y=1.12,
                        xref="paper",
                        yref="paper",
                        text=(
                            "<b>Total Período:</b> "
                            f"{total_formatado}"
                        ),
                        showarrow=False,
                        font=dict(
                            color="#ffffff",
                            size=12,
                            family="monospace",
                        ),
                        bgcolor="#1a222d",
                        bordercolor="#333d4d",
                        borderwidth=1,
                        borderpad=6,
                        align="right",
                    )
                ],
            )

            fig_sku_linha = go.Figure()

            fig_sku_linha.add_trace(
                go.Scatter(
                    x=df_sku_tempo[
                        "Periodo"
                    ],
                    y=df_sku_tempo[
                        "codigo_produto"
                    ],
                    name="SKUs Ativos",
                    mode="lines+markers+text",
                    text=textos_skus,
                    textposition="top center",
                    textfont=dict(
                        color="white",
                        size=11,
                    ),
                    line=dict(
                        color="#e74c3c",
                        width=3,
                    ),
                    fill="tozeroy",
                    fillcolor=(
                        "rgba(231,76,60,0.1)"
                    ),
                    hoverinfo="none",
                )
            )

            fig_sku_linha.update_layout(
                **layout_sku,
                hovermode=False,
                showlegend=False,
            )

            fig_sku_linha.update_xaxes(
                showgrid=False,
                zeroline=False,
                range=[
                    -0.8,
                    n_pontos - 0.2,
                ],
            )

            fig_sku_linha.update_yaxes(
                showgrid=True,
                gridcolor="#232b36",
                zeroline=False,
                range=[
                    0,
                    max_y * 1.15
                    if max_y > 0
                    else 100,
                ],
                showticklabels=False,
            )

            st.plotly_chart(
                fig_sku_linha,
                use_container_width=True,
                config={
                    "displayModeBar": False
                },
                key="skus_geral",
            )

    else:

        st.info(
            "Nenhum dado encontrado "
            "para os filtros selecionados."
        )


# ============================================================
# ABA DETALHADA
# ============================================================

with aba_detalhada:

    if not df_snapshot.empty:

        st.markdown(
            """
            <div style="
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 15px;
            ">
                📋 CONSOLIDAÇÃO ANALÍTICA
                POR UNIDADE DE ALMOXARIFADO
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------
        # AGREGAÇÃO
        # ----------------------------------------------------

        df_tabela = (
            df_snapshot
            .groupby(
                "unidade_almoxarifado",
                as_index=False,
            )
            .agg(
                Valor_Estoque=(
                    "valor_saldo_atual",
                    "sum",
                ),

                Valor_Compras=(
                    "valor_entrada_compras",
                    "sum",
                ),

                Valor_Consumo=(
                    "valor_saida_cons_interno",
                    lambda x: x.abs().sum(),
                ),
            )
        )

        # ----------------------------------------------------
        # SKUs ativos por unidade
        # ----------------------------------------------------

        df_sku_unidade = (
            df_snapshot[
                (
                    df_snapshot[
                        "qtde_saldo_atual"
                    ] > 0
                )
                &
                (
                    df_snapshot[
                        "codigo_produto"
                    ] != ""
                )
            ]
            .groupby(
                "unidade_almoxarifado"
            )["codigo_produto"]
            .nunique()
            .reset_index(
                name="SKUs_Ativos"
            )
        )

        df_tabela = df_tabela.merge(
            df_sku_unidade,
            on="unidade_almoxarifado",
            how="left",
        )

        df_tabela[
            "SKUs_Ativos"
        ] = (
            df_tabela[
                "SKUs_Ativos"
            ]
            .fillna(0)
            .astype(int)
        )

        # ----------------------------------------------------
        # Ordenação
        # ----------------------------------------------------

        df_tabela = (
            df_tabela
            .sort_values(
                "Valor_Estoque",
                ascending=False,
            )
            .reset_index(drop=True)
        )

        # ----------------------------------------------------
        # DataFrame de exibição
        # ----------------------------------------------------

        df_exibicao = pd.DataFrame()

        df_exibicao[
            "Unidade de Almoxarifado"
        ] = (
            df_tabela[
                "unidade_almoxarifado"
            ]
        )

        df_exibicao[
            "Valor em Estoque"
        ] = (
            df_tabela[
                "Valor_Estoque"
            ].apply(fmt_brl)
        )

        df_exibicao[
            "Valor de Compras"
        ] = (
            df_tabela[
                "Valor_Compras"
            ].apply(fmt_brl)
        )

        df_exibicao[
            "Valor de Consumo"
        ] = (
            df_tabela[
                "Valor_Consumo"
            ].apply(fmt_brl)
        )

        df_exibicao[
            "SKUs Ativos"
        ] = (
            df_tabela[
                "SKUs_Ativos"
            ].apply(fmt_int)
        )

        # ----------------------------------------------------
        # Tabela
        # ----------------------------------------------------

        st.dataframe(
            df_exibicao,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "Nenhum dado encontrado "
            "para os filtros selecionados."
        )
