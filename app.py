from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import json
import pandas as pd
import numpy as np
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go


# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================

st.set_page_config(
    page_title="Visão Executiva de Estoque",
    layout="wide"
)


# =========================================================
# CONSTANTES
# =========================================================

TABLE_NAME = "painel_estoque"

COLUNAS_SELECT = [
    "valor_saldo_atual",
    "valor_entrada_compras",
    "valor_saida_cons_interno",
    "unidade_almoxarifado",
    "mes_referencia",
    "ano_referencia",
    "codigo_produto",
    "nome_produto",
    "qtde_saldo_atual",
    "item_critico",
    "nome_local_estoque",
]

COLUNAS_ESPERADAS = COLUNAS_SELECT + [
    "tmp_ano_num",
    "tmp_mes_num",
    "tempo_idx",
    "eh_critico",
    "eh_obsoleto",
    "eh_obra",
    "eh_operacional",
]

DEFAULT_SESSION = {
    "vis_total": True,
    "vis_critico": False,
    "vis_obsoleto": False,
    "vis_obra": False,
    "chart_escopo": "Ativas",
    "chart_unidades": [],
    "chart_anos": [],
    "filtro_periodo_grafico": None,
}


# =========================================================
# SESSION STATE
# =========================================================

for key, value in DEFAULT_SESSION.items():
    st.session_state.setdefault(key, value)


# =========================================================
# CSS
# =========================================================

st.markdown(
    """
<style>
    @keyframes smoothPageLoad {
        0% { opacity: 0.2; transform: scale(0.98); }
        100% { opacity: 1; transform: scale(1); }
    }

    .stApp {
        background-color: #0f141c;
        animation: smoothPageLoad 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }

    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }

    ::-webkit-scrollbar-track {
        background: #161c24;
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb {
        background: #232b36;
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: #d85c27;
    }

    .stButton > button {
        background-color: #161c24 !important;
        color: #8c9ba5 !important;
        border: 1px solid #232b36 !important;
        border-radius: 6px !important;
        font-size: 10px !important;
        padding: 2px 6px !important;
        min-height: 28px !important;
        font-weight: 600 !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }

    .stButton > button:hover {
        border-color: #d85c27 !important;
        color: #ffffff !important;
        transform: translateY(-1px);
    }

    .header-container {
        display: flex;
        align-items: center;
        border-bottom: 2px solid #d85c27;
        padding-bottom: 12px;
        margin-bottom: 20px;
        gap: 20px;
    }

    .logo-container {
        background-color: #ffffff;
        padding: 6px 16px;
        border-radius: 4px;
        text-align: center;
        font-family: Arial, sans-serif;
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
        border-left: 1px solid #333d4d;
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

    .section-title {
        color: #ffffff;
        font-size: 14px;
        font-weight: bold;
        margin-bottom: 12px;
        letter-spacing: 0.5px;
        border-left: 3px solid #d85c27;
        padding-left: 10px;
    }

    .card-box {
        background-color: #161c24;
        border: 1px solid #232b36;
        border-radius: 8px;
        padding: 16px;
        min-height: 130px;
        height: auto;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5), 0 4px 8px rgba(0, 0, 0, 0.3);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }

    .card-box:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8), 0 5px 15px rgba(216, 92, 39, 0.15);
        border-color: #333d4d;
    }

    div[data-testid="stContainer"] {
        background-color: #161c24 !important;
        border: 1px solid #232b36 !important;
        border-radius: 8px !important;
        padding: 20px !important;
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8) !important;
        overflow: visible !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }

    div[data-testid="stContainer"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 20px 35px rgba(0, 0, 0, 0.85), 0 8px 20px rgba(216, 92, 39, 0.2) !important;
        border-color: #333d4d !important;
    }

    .card-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
    }

    .header-left {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .icon-box {
        width: 32px;
        height: 32px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        flex-shrink: 0;
    }

    .icon-estoque { background-color: #132a24; color: #2ecc71; }
    .icon-critico { background-color: #2a1515; color: #e74c3c; }
    .icon-obsoleto { background-color: #2a2a2a; color: #9b59b6; }
    .icon-obra { background-color: #1a2a2a; color: #1abc9c; }
    .icon-compras { background-color: #2a2211; color: #f39c12; }
    .icon-consumo { background-color: #2a1515; color: #e74c3c; }
    .icon-skus { background-color: #1a222d; color: #3498db; }
    .icon-giro { background-color: #221a2d; color: #9b59b6; }
    .icon-cobertura { background-color: #2a2211; color: #e67e22; }

    .card-title {
        color: #8c9ba5;
        font-size: 11px;
        font-weight: bold;
        letter-spacing: 0.5px;
        line-height: 1.2;
    }

    .card-value {
        color: #ffffff;
        font-size: 21px;
        font-weight: bold;
        text-align: center;
        font-family: monospace;
        margin-top: 12px;
        white-space: nowrap;
    }

    .trend-box {
        display: flex;
        align-items: center;
        padding: 3px 8px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: bold;
        font-family: monospace;
        white-space: nowrap;
    }

    .trend-up {
        background-color: rgba(231, 76, 60, 0.2);
        color: #e74c3c;
    }

    .trend-down {
        background-color: rgba(46, 204, 113, 0.2);
        color: #2ecc71;
    }

    .trend-neutral {
        background-color: rgba(140, 155, 165, 0.2);
        color: #8c9ba5;
    }
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# FUNÇÕES DE FORMATAÇÃO
# =========================================================

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(val):
    return f"{int(val):,}".replace(",", ".")


def fmt_dec(val):
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + "x"


def fmt_mes(val):
    return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_valor_milhoes(val):
    if val >= 1e9:
        return f"R$ {val / 1e9:.1f}B".replace(".", ",")
    if val >= 1e6:
        return f"R$ {val / 1e6:.1f}M".replace(".", ",")
    return fmt_brl(val)


def limpar_valor(val):
    if pd.isna(val) or val is None:
        return ""
    s_val = str(val).strip()
    if s_val.endswith(".0"):
        s_val = s_val[:-2]
    return s_val


def chave_numerica(val):
    try:
        return (0, int(val))
    except (ValueError, TypeError):
        return (1, str(val))


def df_vazio_padrao():
    return pd.DataFrame(columns=COLUNAS_ESPERADAS)


def periodo_formatado(mes, ano):
    return f"{int(mes):02d}/{int(ano)}"


def parse_periodo(periodo):
    mes_str, ano_str = periodo.split("/")
    return int(mes_str), int(ano_str)


def periodo_anterior(mes, ano):
    if mes == 1:
        return 12, ano - 1
    return mes - 1, ano


def somar_coluna(dataframe, coluna):
    if dataframe.empty or coluna not in dataframe.columns:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors="coerce").fillna(0.0).sum()


def get_vis(key):
    return True if st.session_state.get(key, False) else "legendonly"


# =========================================================
# CONEXÃO SUPABASE
# =========================================================

@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = conectar_supabase()


# =========================================================
# CARREGAMENTO OTIMIZADO
# =========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados():
    """
    Melhorias aplicadas:
    - cache com TTL
    - batch maior
    - as_completed no paralelismo
    - flags calculadas uma única vez
    - tempo_idx calculado uma única vez
    - select apenas das colunas necessárias
    """

    try:
        select_cols = ", ".join(COLUNAS_SELECT)

        count_res = (
            supabase
            .table(TABLE_NAME)
            .select("*", count="exact", head=True)
            .execute()
        )

        total_rows = getattr(count_res, "count", None)

        if not total_rows or total_rows == 0:
            total_rows = 460000

        batch_size = 5000
        max_workers = 6

        ranges = [
            (i, min(i + batch_size - 1, total_rows - 1))
            for i in range(0, total_rows, batch_size)
        ]

        def fetch_range(start_r, end_r, tentativas=3):
            ultimo_erro = None

            for tentativa in range(1, tentativas + 1):
                try:
                    res = (
                        supabase
                        .table(TABLE_NAME)
                        .select(select_cols)
                        .order("id")
                        .range(start_r, end_r)
                        .execute()
                    )

                    return res.data if res.data else []

                except Exception as e:
                    ultimo_erro = e

                    if tentativa < tentativas:
                        time.sleep(0.5 * tentativa)

            raise ultimo_erro

        all_data = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(fetch_range, start, end)
                for start, end in ranges
            ]

            for future in as_completed(futures):
                data = future.result()
                if data:
                    all_data.extend(data)

        if not all_data:
            return df_vazio_padrao()

        df = pd.DataFrame(all_data)

        for col in COLUNAS_SELECT:
            if col not in df.columns:
                df[col] = ""

        df["unidade_almoxarifado"] = (
            df["unidade_almoxarifado"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        cols_texto = [
            "mes_referencia",
            "ano_referencia",
            "codigo_produto",
            "nome_produto",
            "item_critico",
            "nome_local_estoque",
        ]

        for col in cols_texto:
            df[col] = df[col].map(limpar_valor)

        cols_num = [
            "valor_saldo_atual",
            "valor_entrada_compras",
            "valor_saida_cons_interno",
            "qtde_saldo_atual",
        ]

        for col in cols_num:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        df["tmp_ano_num"] = pd.to_numeric(
            df["ano_referencia"],
            errors="coerce"
        ).fillna(0).astype(int)

        df["tmp_mes_num"] = pd.to_numeric(
            df["mes_referencia"],
            errors="coerce"
        ).fillna(0).astype(int)

        df["tempo_idx"] = df["tmp_ano_num"] * 12 + df["tmp_mes_num"]

        df["eh_critico"] = df["item_critico"].eq("1-Sim")

        nome_local = df["nome_local_estoque"].astype(str)

        df["eh_obsoleto"] = nome_local.str.contains(
            "Obsoleto",
            case=False,
            na=False
        )

        df["eh_obra"] = nome_local.str.contains(
            "obra",
            case=False,
            na=False
        )

        df["eh_operacional"] = ~(
            df["eh_critico"] | df["eh_obsoleto"]
        )

        return df

    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return df_vazio_padrao()


# =========================================================
# FUNÇÕES DE CÁLCULO
# =========================================================

def aplicar_filtros_base(df, unidades_ativas, unidades_gerenciais):
    df_filtrado = df

    escopo = st.session_state.get("chart_escopo", "Todas")

    if escopo == "Ativas":
        df_filtrado = df_filtrado[
            df_filtrado["unidade_almoxarifado"].isin(unidades_ativas)
        ]
    elif escopo == "Gerenciais":
        df_filtrado = df_filtrado[
            df_filtrado["unidade_almoxarifado"].isin(unidades_gerenciais)
        ]

    unidades_sel = st.session_state.get("chart_unidades", [])

    if unidades_sel:
        df_filtrado = df_filtrado[
            df_filtrado["unidade_almoxarifado"].isin(unidades_sel)
        ]

    anos_sel = st.session_state.get("chart_anos", [])

    if anos_sel:
        df_filtrado = df_filtrado[
            df_filtrado["ano_referencia"].isin(anos_sel)
        ]

    return df_filtrado


def gerar_periodo_coluna(df):
    if df.empty:
        df["Periodo"] = []
        return df

    df["Periodo"] = (
        df["tmp_mes_num"].astype(int).astype(str).str.zfill(2)
        + "/"
        + df["tmp_ano_num"].astype(int).astype(str)
    )

    return df


def agrupar_mensal(df, mascara=None):
    if df.empty:
        return pd.DataFrame(
            columns=[
                "ano_referencia",
                "mes_referencia",
                "tmp_ano_num",
                "tmp_mes_num",
                "valor_saldo_atual",
                "Periodo",
                "texto_labels",
            ]
        )

    base = df if mascara is None else df[mascara]

    if base.empty:
        return pd.DataFrame(
            columns=[
                "ano_referencia",
                "mes_referencia",
                "tmp_ano_num",
                "tmp_mes_num",
                "valor_saldo_atual",
                "Periodo",
                "texto_labels",
            ]
        )

    result = (
        base
        .groupby(
            [
                "ano_referencia",
                "mes_referencia",
                "tmp_ano_num",
                "tmp_mes_num",
            ],
            as_index=False
        )["valor_saldo_atual"]
        .sum()
        .sort_values(["tmp_ano_num", "tmp_mes_num"])
    )

    result = gerar_periodo_coluna(result)
    result["texto_labels"] = result["valor_saldo_atual"].apply(fmt_valor_milhoes)

    return result


def obter_ultimo_periodo(df):
    if df.empty:
        return 7, 2026

    max_ano = int(df["tmp_ano_num"].max())
    max_mes = int(
        df.loc[df["tmp_ano_num"] == max_ano, "tmp_mes_num"].max()
    )

    return max_mes, max_ano


def corrigir_periodo_ativo(df_filtrado):
    periodo = st.session_state.get("filtro_periodo_grafico")

    if not periodo or df_filtrado.empty:
        return

    mes, ano = parse_periodo(periodo)

    existe = df_filtrado[
        (df_filtrado["tmp_ano_num"] == ano)
        & (df_filtrado["tmp_mes_num"] == mes)
    ]

    if existe.empty:
        max_mes, max_ano = obter_ultimo_periodo(df_filtrado)
        st.session_state.filtro_periodo_grafico = periodo_formatado(
            max_mes,
            max_ano
        )


def obter_snapshots(df_filtrado, max_mes_base, max_ano_base):
    if df_filtrado.empty:
        return df_filtrado, df_filtrado

    periodo = st.session_state.get("filtro_periodo_grafico")

    if periodo:
        mes, ano = parse_periodo(periodo)
    elif st.session_state.get("chart_anos"):
        anos_num = [int(a) for a in st.session_state.chart_anos]
        df_anos_sel = df_filtrado[df_filtrado["tmp_ano_num"].isin(anos_num)]

        if df_anos_sel.empty:
            mes, ano = max_mes_base, max_ano_base
        else:
            mes, ano = obter_ultimo_periodo(df_anos_sel)
    else:
        mes, ano = max_mes_base, max_ano_base

    mes_prev, ano_prev = periodo_anterior(mes, ano)

    df_snapshot = df_filtrado[
        (df_filtrado["tmp_ano_num"] == ano)
        & (df_filtrado["tmp_mes_num"] == mes)
    ]

    df_snapshot_prev = df_filtrado[
        (df_filtrado["tmp_ano_num"] == ano_prev)
        & (df_filtrado["tmp_mes_num"] == mes_prev)
    ]

    return df_snapshot, df_snapshot_prev


def calcular_indicadores_snapshot(df_snapshot):
    val_estoque = somar_coluna(df_snapshot, "valor_saldo_atual")
    val_compras = somar_coluna(df_snapshot, "valor_entrada_compras")

    val_consumo = (
        pd.to_numeric(
            df_snapshot["valor_saida_cons_interno"],
            errors="coerce"
        )
        .fillna(0.0)
        .abs()
        .sum()
        if "valor_saida_cons_interno" in df_snapshot.columns
        else 0.0
    )

    if df_snapshot.empty:
        val_skus = 0
        val_critico = 0.0
        val_obsoleto = 0.0
        val_obra = 0.0
    else:
        val_skus = df_snapshot[
            (df_snapshot["qtde_saldo_atual"] > 0)
            & (df_snapshot["codigo_produto"] != "")
        ]["codigo_produto"].nunique()

        val_critico = somar_coluna(
            df_snapshot[df_snapshot["eh_critico"]],
            "valor_saldo_atual"
        )

        val_obsoleto = somar_coluna(
            df_snapshot[df_snapshot["eh_obsoleto"]],
            "valor_saldo_atual"
        )

        val_obra = somar_coluna(
            df_snapshot[df_snapshot["eh_obra"]],
            "valor_saldo_atual"
        )

    return {
        "estoque": val_estoque,
        "compras": val_compras,
        "consumo": val_consumo,
        "skus": val_skus,
        "critico": val_critico,
        "obsoleto": val_obsoleto,
        "obra": val_obra,
    }


def calcular_giro_cobertura(df_base):
    if df_base.empty:
        return 0.0, 0.0, 0.0, 0.0

    base = df_base[df_base["eh_operacional"]]

    if base.empty:
        return 0.0, 0.0, 0.0, 0.0

    monthly_df = (
        base
        .assign(
            consumo_abs=base["valor_saida_cons_interno"].abs(),
            val_estoque=base["valor_saldo_atual"]
        )
        .groupby(
            [
                "ano_referencia",
                "mes_referencia",
                "tmp_ano_num",
                "tmp_mes_num",
            ],
            as_index=False
        )
        .agg(
            estoque_op=("val_estoque", "sum"),
            consumo_op=("consumo_abs", "sum")
        )
    )

    if monthly_df.empty:
        return 0.0, 0.0, 0.0, 0.0

    estoque_medio_op = monthly_df["estoque_op"].mean()
    consumo_medio_mensal = monthly_df["consumo_op"].mean()

    giro_mensal = (
        consumo_medio_mensal / estoque_medio_op
        if estoque_medio_op > 0
        else 0.0
    )

    giro_anual = giro_mensal * 12

    cobertura_meses = (
        estoque_medio_op / consumo_medio_mensal
        if consumo_medio_mensal > 0
        else 0.0
    )

    cobertura_anos = cobertura_meses / 12

    return giro_mensal, giro_anual, cobertura_meses, cobertura_anos


def calcular_giro_periodos(df_filtrado):
    if df_filtrado.empty:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    periodo = st.session_state.get("filtro_periodo_grafico")

    if periodo:
        mes_ativo, ano_ativo = parse_periodo(periodo)
    else:
        mes_ativo, ano_ativo = obter_ultimo_periodo(df_filtrado)

    df_ytd = df_filtrado[
        (df_filtrado["tmp_ano_num"] == ano_ativo)
        & (df_filtrado["tmp_mes_num"] <= mes_ativo)
    ]

    giro_mensal, giro_anual, cobertura_meses, cobertura_anos = (
        calcular_giro_cobertura(df_ytd)
    )

    mes_prev, ano_prev = periodo_anterior(mes_ativo, ano_ativo)

    df_prev_ytd = df_filtrado[
        (df_filtrado["tmp_ano_num"] == ano_prev)
        & (df_filtrado["tmp_mes_num"] <= mes_prev)
    ]

    giro_mensal_prev, _, cobertura_meses_prev, _ = calcular_giro_cobertura(
        df_prev_ytd
    )

    return (
        giro_mensal,
        giro_anual,
        cobertura_meses,
        cobertura_anos,
        giro_mensal_prev,
        cobertura_meses_prev,
    )


def render_card(
    icon,
    icon_class,
    title,
    val_formatado,
    val_atual,
    val_ant,
    font_size="21px",
    invert_color=False
):
    if val_ant == 0 and val_atual == 0:
        pct_str = "0,0%"
        trend_class = "trend-neutral"
        arrow = "➖"
    elif val_ant == 0:
        pct_str = "100,0%"
        trend_class = "trend-down" if invert_color else "trend-up"
        arrow = "🔺"
    else:
        pct = ((val_atual - val_ant) / val_ant) * 100
        pct_str = f"{abs(pct):.1f}%".replace(".", ",")

        if pct > 0:
            trend_class = "trend-down" if invert_color else "trend-up"
            arrow = "🔺"
        elif pct < 0:
            trend_class = "trend-up" if invert_color else "trend-down"
            arrow = "🔻"
        else:
            trend_class = "trend-neutral"
            arrow = "➖"

    return f"""
    <div class="card-box">
        <div class="card-header">
            <div class="header-left">
                <div class="icon-box {icon_class}">{icon}</div>
                <div class="card-title">{title}</div>
            </div>
            <div class="trend-box {trend_class}">{arrow} {pct_str}</div>
        </div>
        <div class="card-value" style="font-size: {font_size};">{val_formatado}</div>
    </div>
    """


def layout_padrao():
    return dict(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8c9ba5"),
        margin=dict(l=10, r=10, t=30, b=30),
    )


def adicionar_highlight_periodo(fig, df_periodo, periodo_ativo):
    if not periodo_ativo or df_periodo.empty or "Periodo" not in df_periodo.columns:
        return fig

    match_idx = df_periodo.index[
        df_periodo["Periodo"] == periodo_ativo
    ].tolist()

    if match_idx:
        idx = match_idx[0]

        fig.add_shape(
            type="rect",
            x0=idx - 0.25,
            x1=idx + 0.25,
            y0=0,
            y1=1,
            yref="paper",
            fillcolor="rgba(216, 92, 39, 0.18)",
            line=dict(width=1.5, color="rgba(216, 92, 39, 0.6)"),
            layer="below",
        )

    return fig


# =========================================================
# CABEÇALHO
# =========================================================

st.markdown(
    """
<div class="header-container">
    <div class="logo-container">
        <div class="logo-main">Âmbar</div>
        <div class="logo-sub">ENERGIA</div>
    </div>
    <div class="title-container">
        <div class="title-main">VISÃO EXECUTIVA DE ESTOQUE</div>
        <div class="title-sub">Valores Consolidados</div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# =========================================================
# CARGA DOS DADOS
# =========================================================

with st.spinner("Carregando base otimizada..."):
    df_completo = carregar_dados()


if not df_completo.empty:
    max_mes_base, max_ano_base = obter_ultimo_periodo(df_completo)

    if st.session_state.filtro_periodo_grafico is None:
        st.session_state.filtro_periodo_grafico = periodo_formatado(
            max_mes_base,
            max_ano_base
        )
else:
    max_mes_base, max_ano_base = 7, 2026


unidades_opcoes = (
    sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist())
    if not df_completo.empty
    else []
)

unidades_gerenciais = [
    u for u in unidades_opcoes
    if "GERENCIAL" in u
]

unidades_ativas = [
    u for u in unidades_opcoes
    if "GERENCIAL" not in u
]

ano_opcoes = (
    sorted(
        df_completo["ano_referencia"].dropna().unique().tolist(),
        key=chave_numerica
    )
    if not df_completo.empty
    else []
)


# =========================================================
# ABAS
# =========================================================

aba_geral, aba_detalhada = st.tabs(
    [
        "📈 Visão Geral",
        "📊 Análises Detalhadas & Tendência de Estoque",
    ]
)


# =========================================================
# ABA GERAL
# =========================================================

with aba_geral:
    with st.container(border=True):
        col_tg_title, col_tg_escopo, col_tg_unid, col_tg_ano = st.columns(
            [1.8, 1.2, 2.0, 1.5]
        )

        with col_tg_title:
            st.markdown(
                """
                <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 5px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                    📊 TENDÊNCIA: TOTAL VS CRÍTICO VS OBSOLETO VS OBRA
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_tg_escopo:
            st.selectbox(
                "Escopo:",
                ["Todas", "Ativas", "Gerenciais"],
                key="chart_escopo",
            )

        with col_tg_unid:
            if st.session_state.chart_escopo == "Ativas":
                opcoes_unid = unidades_ativas
            elif st.session_state.chart_escopo == "Gerenciais":
                opcoes_unid = unidades_gerenciais
            else:
                opcoes_unid = unidades_opcoes

            st.multiselect(
                "Unidades:",
                opcoes_unid,
                key="chart_unidades",
                placeholder="Todas",
            )

        with col_tg_ano:
            st.multiselect(
                "Anos:",
                ano_opcoes,
                key="chart_anos",
                placeholder="Todos",
            )

        df_filtrado = aplicar_filtros_base(
            df_completo,
            unidades_ativas,
            unidades_gerenciais,
        )

        corrigir_periodo_ativo(df_filtrado)

        c_leg1, c_leg2, c_leg3, c_leg4 = st.columns(4)

        botoes_legenda = [
            ("vis_total", "Estoque Total", c_leg1),
            ("vis_critico", "Estoque Crítico", c_leg2),
            ("vis_obsoleto", "Estoque Obsoleto", c_leg3),
            ("vis_obra", "Estoque Obra", c_leg4),
        ]

        for key, label, col in botoes_legenda:
            with col:
                status = "🟡" if st.session_state[key] else "⚪"
                if st.button(
                    f"{status} {label}",
                    key=f"btn_{key}",
                    use_container_width=True,
                ):
                    st.session_state[key] = not st.session_state[key]
                    st.rerun()

        df_estoque_mes = agrupar_mensal(df_filtrado)
        df_critico_mes = agrupar_mensal(df_filtrado, df_filtrado["eh_critico"])
        df_obsoleto_mes = agrupar_mensal(df_filtrado, df_filtrado["eh_obsoleto"])
        df_obra_mes = agrupar_mensal(df_filtrado, df_filtrado["eh_obra"])

        max_y_est = (
            df_estoque_mes["valor_saldo_atual"].max()
            if not df_estoque_mes.empty
            else 100
        )

        n_pontos_est = len(df_estoque_mes)

        fig_linha_estoque = go.Figure()

        fig_linha_estoque.add_trace(
            go.Scatter(
                x=df_estoque_mes["Periodo"],
                y=df_estoque_mes["valor_saldo_atual"],
                name="Estoque Total",
                mode="lines+markers+text",
                text=df_estoque_mes["texto_labels"],
                textposition="top center",
                textfont=dict(color="white", size=11),
                line=dict(color="#e74c3c", width=3),
                marker=dict(
                    size=8,
                    color="#e74c3c",
                    line=dict(color="#ffffff", width=2),
                ),
                fill="tozeroy",
                fillcolor="rgba(231, 76, 60, 0.08)",
                hoverinfo="none",
                visible=get_vis("vis_total"),
            )
        )

        if not df_critico_mes.empty:
            fig_linha_estoque.add_trace(
                go.Scatter(
                    x=df_critico_mes["Periodo"],
                    y=df_critico_mes["valor_saldo_atual"],
                    name="Estoque Crítico",
                    mode="lines+markers+text",
                    text=df_critico_mes["texto_labels"],
                    textposition="bottom center",
                    textfont=dict(color="#f39c12", size=11),
                    line=dict(color="#f39c12", width=2.5, dash="dash"),
                    marker=dict(
                        size=6,
                        color="#f39c12",
                        line=dict(color="#ffffff", width=1),
                    ),
                    hoverinfo="none",
                    visible=get_vis("vis_critico"),
                )
            )

        if not df_obsoleto_mes.empty:
            fig_linha_estoque.add_trace(
                go.Scatter(
                    x=df_obsoleto_mes["Periodo"],
                    y=df_obsoleto_mes["valor_saldo_atual"],
                    name="Estoque Obsoleto",
                    mode="lines+markers+text",
                    text=df_obsoleto_mes["texto_labels"],
                    textposition="top center",
                    textfont=dict(color="#9b59b6", size=11),
                    line=dict(color="#9b59b6", width=2.5, dash="dot"),
                    marker=dict(
                        size=6,
                        color="#9b59b6",
                        line=dict(color="#ffffff", width=1),
                    ),
                    hoverinfo="none",
                    visible=get_vis("vis_obsoleto"),
                )
            )

        if not df_obra_mes.empty:
            fig_linha_estoque.add_trace(
                go.Scatter(
                    x=df_obra_mes["Periodo"],
                    y=df_obra_mes["valor_saldo_atual"],
                    name="Estoque Obra",
                    mode="lines+markers+text",
                    text=df_obra_mes["texto_labels"],
                    textposition="bottom center",
                    textfont=dict(color="#1abc9c", size=11),
                    line=dict(color="#1abc9c", width=2.5, dash="longdash"),
                    marker=dict(
                        size=6,
                        color="#1abc9c",
                        line=dict(color="#ffffff", width=1),
                    ),
                    hoverinfo="none",
                    visible=get_vis("vis_obra"),
                )
            )

        sel_state = st.session_state.get("tendencia_geral", {})
        pontos_clicados = (
            sel_state.get("selection", {}).get("points", [])
            if isinstance(sel_state, dict)
            else []
        )

        if (
            pontos_clicados
            and isinstance(pontos_clicados, list)
            and "x" in pontos_clicados[0]
        ):
            x_hl = pontos_clicados[0]["x"]

            if st.session_state.get("filtro_periodo_grafico") != x_hl:
                st.session_state.filtro_periodo_grafico = x_hl
                st.rerun()

        periodo_ativo = st.session_state.get("filtro_periodo_grafico")

        fig_linha_estoque = adicionar_highlight_periodo(
            fig_linha_estoque,
            df_estoque_mes,
            periodo_ativo,
        )

        fig_linha_estoque.update_layout(
            **layout_padrao(),
            showlegend=False,
            hovermode="x",
        )

        fig_linha_estoque.update_xaxes(
            showgrid=False,
            zeroline=False,
            range=[-0.8, n_pontos_est - 0.2],
        )

        fig_linha_estoque.update_yaxes(
            showgrid=True,
            gridcolor="#232b36",
            zeroline=False,
            range=[-max_y_est * 0.08, max_y_est * 1.3],
            showticklabels=False,
        )

        st.plotly_chart(
            fig_linha_estoque,
            use_container_width=True,
            config={"displayModeBar": False},
            on_select="rerun",
            selection_mode="points",
            key="tendencia_geral",
        )

        if st.session_state.get("filtro_periodo_grafico"):
            col_b_info, col_b_acao = st.columns([3, 1])

            with col_b_info:
                st.markdown(
                    f"""
                    <span style='color: #d85c27; font-size: 12px;'>
                        📌 Período fixado pelo gráfico:
                        <b>{st.session_state.filtro_periodo_grafico}</b>
                    </span>
                    """,
                    unsafe_allow_html=True,
                )

            with col_b_acao:
                if st.button(
                    "🔄 Limpar Filtro do Gráfico",
                    use_container_width=True,
                ):
                    st.session_state.filtro_periodo_grafico = None
                    st.rerun()

    escopo_atual = st.session_state.get("chart_escopo", "Todas")

    if escopo_atual == "Todas":
        texto_informativo = (
            "Exibindo dados consolidados de **todas as unidades** "
            "(Ativas e Gerenciais)."
        )
    elif escopo_atual == "Ativas":
        texto_informativo = (
            "Exibindo dados consolidados apenas das **unidades ativas**."
        )
    else:
        texto_informativo = (
            "Exibindo dados consolidados apenas das **unidades gerenciais**."
        )

    if st.session_state.get("filtro_periodo_grafico"):
        texto_informativo += (
            f" 🎯 **Período Ativo: "
            f"{st.session_state.filtro_periodo_grafico}**"
        )

    st.markdown(
        f"""
        <p style='color: #8c9ba5; font-size: 14px; margin-top: 10px; margin-bottom: 20px;'>
            {texto_informativo}
        </p>
        """,
        unsafe_allow_html=True,
    )

    df_snapshot, df_snapshot_prev = obter_snapshots(
        df_filtrado,
        max_mes_base,
        max_ano_base,
    )

    ind = calcular_indicadores_snapshot(df_snapshot)
    ind_prev = calcular_indicadores_snapshot(df_snapshot_prev)

    (
        giro_mensal,
        giro_anual,
        cobertura_meses,
        cobertura_anos,
        giro_mensal_prev,
        cobertura_meses_prev,
    ) = calcular_giro_periodos(df_filtrado)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        "<div class='section-title'>💼 LINHA FINANCEIRA</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            render_card(
                "📦",
                "icon-estoque",
                "(R$) ESTOQUE",
                fmt_brl(ind["estoque"]),
                ind["estoque"],
                ind_prev["estoque"],
            ),
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            render_card(
                "⚠️",
                "icon-critico",
                "(R$) EST. CRÍTICO",
                fmt_brl(ind["critico"]),
                ind["critico"],
                ind_prev["critico"],
            ),
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            render_card(
                "🗑️",
                "icon-obsoleto",
                "(R$) EST. OBSOLETO",
                fmt_brl(ind["obsoleto"]),
                ind["obsoleto"],
                ind_prev["obsoleto"],
            ),
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            render_card(
                "🏗️",
                "icon-obra",
                "(R$) EST. OBRA",
                fmt_brl(ind["obra"]),
                ind["obra"],
                ind_prev["obra"],
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        "<div class='section-title'>⚙️ LINHA OPERACIONAL</div>",
        unsafe_allow_html=True,
    )

    c5, c6, c7, c8, c9 = st.columns(5)

    with c5:
        st.markdown(
            render_card(
                "📥",
                "icon-compras",
                "COMPRAS",
                fmt_brl(ind["compras"]),
                ind["compras"],
                ind_prev["compras"],
                "18px",
            ),
            unsafe_allow_html=True,
        )

    with c6:
        st.markdown(
            render_card(
                "📤",
                "icon-consumo",
                "CONSUMO",
                fmt_brl(ind["consumo"]),
                ind["consumo"],
                ind_prev["consumo"],
                "18px",
                invert_color=True,
            ),
            unsafe_allow_html=True,
        )

    with c7:
        st.markdown(
            render_card(
                "🏷️",
                "icon-skus",
                "SKUs ÚNICOS",
                fmt_int(ind["skus"]),
                ind["skus"],
                ind_prev["skus"],
                "21px",
            ),
            unsafe_allow_html=True,
        )

    with c8:
        st.markdown(
            render_card(
                "🔄",
                "icon-giro",
                "GIRO MENSAL",
                fmt_dec(giro_mensal),
                giro_mensal,
                giro_mensal_prev,
                "21px",
                invert_color=True,
            ),
            unsafe_allow_html=True,
        )

    with c9:
        st.markdown(
            render_card(
                "⏳",
                "icon-cobertura",
                "COBERTURA",
                fmt_mes(cobertura_meses),
                cobertura_meses,
                cobertura_meses_prev,
                "21px",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if not df_filtrado.empty:
        # =====================================================
        # RANKING E COMPOSIÇÃO
        # =====================================================

        col_c1, col_c2 = st.columns([5, 5], gap="medium")

        with col_c1:
            with st.container(border=True):
                st.markdown(
                    """
                    <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                        🏆 RANKING: VALOR EM ESTOQUE POR UNIDADE
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                df_rank = (
                    df_snapshot
                    .groupby("unidade_almoxarifado", as_index=False)
                    ["valor_saldo_atual"]
                    .sum()
                )

                df_rank = df_rank[df_rank["valor_saldo_atual"] > 0]
                df_rank = df_rank.sort_values("valor_saldo_atual", ascending=True)

                df_rank["texto_formatado"] = df_rank[
                    "valor_saldo_atual"
                ].apply(
                    lambda x: (
                        f"R$ {x / 1e3:,.0f} mil"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )
                )

                fig_bar = px.bar(
                    df_rank,
                    x="valor_saldo_atual",
                    y="unidade_almoxarifado",
                    orientation="h",
                    color_discrete_sequence=["#e74c3c"],
                    text="texto_formatado",
                )

                fig_bar.update_layout(
                    **layout_padrao(),
                    margin=dict(l=155, r=15, t=10, b=10),
                    height=max(350, len(df_rank) * 32),
                    hovermode=False,
                    showlegend=False,
                )

                fig_bar.update_traces(
                    textposition="auto",
                    textfont=dict(color="white"),
                )

                fig_bar.update_xaxes(
                    title="",
                    showgrid=True,
                    gridcolor="#232b36",
                    showticklabels=False,
                    zeroline=False,
                )

                fig_bar.update_yaxes(
                    title="",
                    showgrid=False,
                    tickfont=dict(size=10),
                )

                st.plotly_chart(
                    fig_bar,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="ranking_estoque_unidade",
                )

        with col_c2:
            with st.container(border=True):
                st.markdown(
                    """
                    <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                        🍩 COMPOSIÇÃO DO ESTOQUE (VALOR)
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                val_demais = ind["estoque"] - (
                    ind["critico"] + ind["obsoleto"] + ind["obra"]
                )

                val_demais = max(val_demais, 0)

                df_pizza = pd.DataFrame(
                    {
                        "Categoria": [
                            "Estoque Crítico",
                            "Estoque Obsoleto",
                            "Estoque Obra",
                            "Demais Estoque",
                        ],
                        "Valor": [
                            ind["critico"],
                            ind["obsoleto"],
                            ind["obra"],
                            val_demais,
                        ],
                        "Cor": [
                            "#f39c12",
                            "#9b59b6",
                            "#1abc9c",
                            "#3498db",
                        ],
                    }
                )

                df_pizza = df_pizza[df_pizza["Valor"] > 0]
                df_pizza["Valor_Formatado"] = df_pizza["Valor"].apply(fmt_brl)

                fig_rosca = go.Figure(
                    data=[
                        go.Pie(
                            labels=df_pizza["Categoria"],
                            values=df_pizza["Valor"],
                            hole=0.65,
                            marker=dict(
                                colors=df_pizza["Cor"],
                                line=dict(color="#161c24", width=2),
                            ),
                            textinfo="label+percent",
                            textposition="outside",
                            hovertext=df_pizza["Valor_Formatado"],
                            hovertemplate="<b>%{label}</b><br>%{hovertext}<extra></extra>",
                            textfont=dict(size=11),
                        )
                    ]
                )

                fig_rosca.update_layout(
                    **layout_padrao(),
                    margin=dict(l=80, r=80, t=30, b=30),
                    height=380,
                    showlegend=False,
                    annotations=[
                        dict(
                            text=(
                                f"<b>TOTAL</b><br>"
                                f"<span style='font-size:20px'>"
                                f"{fmt_valor_milhoes(ind['estoque'])}"
                                f"</span>"
                            ),
                            x=0.5,
                            y=0.5,
                            font_size=14,
                            font_color="white",
                            showarrow=False,
                        )
                    ],
                )

                st.plotly_chart(
                    fig_rosca,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="rosca_composicao",
                )

        # =====================================================
        # COMPRAS VS CONSUMO NO TEMPO
        # =====================================================

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                """
                <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                    📈 EVOLUÇÃO TEMPORAL: COMPRAS VS CONSUMO
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
                    as_index=False
                )
                .agg(
                    valor_entrada_compras=("valor_entrada_compras", "sum"),
                    valor_consumo=("valor_saida_cons_interno", lambda x: x.abs().sum()),
                )
                .sort_values(["tmp_ano_num", "tmp_mes_num"])
            )

            df_tempo = gerar_periodo_coluna(df_tempo)

            fig_linha = go.Figure()

            fig_linha.add_trace(
                go.Scatter(
                    x=df_tempo["Periodo"],
                    y=df_tempo["valor_entrada_compras"],
                    name="Compras",
                    mode="lines+markers",
                    line=dict(color="#f39c12", width=3),
                )
            )

            fig_linha.add_trace(
                go.Scatter(
                    x=df_tempo["Periodo"],
                    y=df_tempo["valor_consumo"],
                    name="Consumo",
                    mode="lines+markers",
                    line=dict(color="#e74c3c", width=3),
                )
            )

            fig_linha = adicionar_highlight_periodo(
                fig_linha,
                df_tempo,
                periodo_ativo,
            )

            fig_linha.update_layout(
                **layout_padrao(),
                hovermode="x unified",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.05,
                    xanchor="right",
                    x=1,
                ),
            )

            fig_linha.update_xaxes(showgrid=False, zeroline=False)

            fig_linha.update_yaxes(
                showgrid=True,
                gridcolor="#232b36",
                zeroline=False,
                tickprefix="R$ ",
            )

            st.plotly_chart(
                fig_linha,
                use_container_width=True,
                config={"displayModeBar": False},
                key="compras_consumo_geral",
            )

        # =====================================================
        # COMPRAS VS CONSUMO E SKUS POR UNIDADE
        # =====================================================

        st.markdown("<br>", unsafe_allow_html=True)

        col_esq, col_dir = st.columns(2)

        with col_esq:
            with st.container(border=True):
                st.markdown(
                    """
                    <div style='color: #ffffff; font-size: 13px; font-weight: bold; border-left: 3px solid #d85c27; padding-left: 8px; margin-bottom: 10px;'>
                        📊 COMPRAS VS CONSUMO
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                df_diag = (
                    df_snapshot
                    .groupby("unidade_almoxarifado", as_index=False)
                    .agg(
                        Compras=("valor_entrada_compras", "sum"),
                        Consumo=("valor_saida_cons_interno", lambda x: x.abs().sum()),
                    )
                )

                df_diag = df_diag.sort_values("Compras", ascending=True)
                ordem_unidades = df_diag["unidade_almoxarifado"].tolist()

                df_diag["Compras_Label"] = df_diag["Compras"].apply(
                    lambda x: (
                        f"R$ {x / 1e3:,.0f} mil"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )
                )

                df_diag["Consumo_Label"] = df_diag["Consumo"].apply(
                    lambda x: (
                        f"R$ {x / 1e3:,.0f} mil"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )
                )

                df_diag_melted = df_diag.melt(
                    id_vars=[
                        "unidade_almoxarifado",
                        "Compras_Label",
                        "Consumo_Label",
                    ],
                    value_vars=["Compras", "Consumo"],
                    var_name="Métrica",
                    value_name="Valor",
                )

                df_diag_melted["Texto_Barra"] = np.where(
                    df_diag_melted["Métrica"] == "Compras",
                    df_diag_melted["Compras_Label"],
                    df_diag_melted["Consumo_Label"],
                )

                fig_diag = px.bar(
                    df_diag_melted,
                    x="Valor",
                    y="unidade_almoxarifado",
                    color="Métrica",
                    barmode="group",
                    orientation="h",
                    text="Texto_Barra",
                    color_discrete_map={
                        "Compras": "#e74c3c",
                        "Consumo": "#f39c12",
                    },
                    category_orders={
                        "unidade_almoxarifado": ordem_unidades
                    },
                )

                fig_diag.update_layout(
                    **layout_padrao(),
                    margin=dict(l=130, r=40, t=10, b=10),
                    height=max(350, len(df_diag) * 60),
                    showlegend=False,
                )

                fig_diag.update_xaxes(
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                    title="",
                )

                fig_diag.update_yaxes(
                    title="",
                    showgrid=False,
                    zeroline=False,
                    tickfont=dict(size=10),
                    categoryorder="array",
                    categoryarray=ordem_unidades,
                )

                fig_diag.update_traces(
                    textposition="auto",
                    textfont=dict(color="white", size=10),
                )

                st.plotly_chart(
                    fig_diag,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="diag_compras_consumo_lado",
                )

        with col_dir:
            with st.container(border=True):
                st.markdown(
                    """
                    <div style='color: #ffffff; font-size: 13px; font-weight: bold; border-left: 3px solid #3498db; padding-left: 8px; margin-bottom: 10px;'>
                        📦 RANKING DE SKUs POR UNIDADE
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                df_skus_ativos = df_snapshot[
                    (df_snapshot["qtde_saldo_atual"] > 0)
                    & (df_snapshot["codigo_produto"] != "")
                ]

                df_skus = (
                    df_skus_ativos
                    .groupby("unidade_almoxarifado", as_index=False)
                    .agg(Total_SKUs=("codigo_produto", "nunique"))
                    .sort_values("Total_SKUs", ascending=True)
                )

                ordem_skus = df_skus["unidade_almoxarifado"].tolist()

                df_skus["SKUs_Label"] = df_skus["Total_SKUs"].apply(
                    lambda x: f"{x:,.0f} SKUs".replace(",", ".")
                )

                fig_sku = px.bar(
                    df_skus,
                    x="Total_SKUs",
                    y="unidade_almoxarifado",
                    orientation="h",
                    text="SKUs_Label",
                    color_discrete_sequence=["#3498db"],
                    category_orders={
                        "unidade_almoxarifado": ordem_skus
                    },
                )

                fig_sku.update_layout(
                    **layout_padrao(),
                    margin=dict(l=130, r=40, t=10, b=10),
                    height=max(350, len(df_skus) * 45),
                    showlegend=False,
                )

                fig_sku.update_xaxes(
                    showgrid=False,
                    zeroline=False,
                    showticklabels=False,
                    title="",
                )

                fig_sku.update_yaxes(
                    title="",
                    showgrid=False,
                    zeroline=False,
                    tickfont=dict(size=10),
                    categoryorder="array",
                    categoryarray=ordem_skus,
                )

                fig_sku.update_traces(
                    textposition="auto",
                    textfont=dict(color="white", size=10),
                )

                st.plotly_chart(
                    fig_sku,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="ranking_skus_lado",
                )

        # =====================================================
        # EVOLUÇÃO DE SKUS
        # =====================================================

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                """
                <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                    📦 EVOLUÇÃO DO MIX: TOTAL DE SKUs ATIVOS NO TEMPO
                </div>
                """,
                unsafe_allow_html=True,
            )

            df_sku_trend = df_filtrado[
                (df_filtrado["qtde_saldo_atual"] > 0)
                & (df_filtrado["codigo_produto"] != "")
            ]

            df_sku_tempo = (
                df_sku_trend
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False
                )
                ["codigo_produto"]
                .nunique()
                .sort_values(["tmp_ano_num", "tmp_mes_num"])
            )

            df_sku_tempo = gerar_periodo_coluna(df_sku_tempo)
            df_sku_tempo["texto"] = df_sku_tempo["codigo_produto"].apply(fmt_int)

            max_y_sku = (
                df_sku_tempo["codigo_produto"].max()
                if not df_sku_tempo.empty
                else 100
            )

            fig_sku_linha = go.Figure()

            fig_sku_linha.add_trace(
                go.Scatter(
                    x=df_sku_tempo["Periodo"],
                    y=df_sku_tempo["codigo_produto"],
                    name="SKUs Ativos",
                    mode="lines+markers+text",
                    text=df_sku_tempo["texto"],
                    textposition="top center",
                    textfont=dict(color="white", size=11),
                    line=dict(color="#e74c3c", width=3),
                    fill="tozeroy",
                    fillcolor="rgba(231, 76, 60, 0.1)",
                    hoverinfo="none",
                )
            )

            fig_sku_linha = adicionar_highlight_periodo(
                fig_sku_linha,
                df_sku_tempo,
                periodo_ativo,
            )

            fig_sku_linha.update_layout(
                **layout_padrao(),
                showlegend=False,
                hovermode="x",
                margin=dict(l=40, r=40, t=50, b=10),
                annotations=[
                    dict(
                        x=1.0,
                        y=1.12,
                        xref="paper",
                        yref="paper",
                        text=(
                            f"<b>Total Período:</b> "
                            f"{fmt_int(ind['skus'])}"
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

            fig_sku_linha.update_xaxes(
                showgrid=False,
                zeroline=False,
                range=[-0.8, len(df_sku_tempo) - 0.2],
            )

            fig_sku_linha.update_yaxes(
                showgrid=True,
                gridcolor="#232b36",
                zeroline=False,
                range=[0, max_y_sku * 1.15],
                showticklabels=False,
            )

            st.plotly_chart(
                fig_sku_linha,
                use_container_width=True,
                config={"displayModeBar": False},
                key="skus_geral",
            )

        # =====================================================
        # GIRO VS COBERTURA
        # =====================================================

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                """
                <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                    📈 EVOLUÇÃO TEMPORAL COMBINADA: GIRO MENSAL VS COBERTURA
                </div>
                """,
                unsafe_allow_html=True,
            )

            base_op = df_filtrado[df_filtrado["eh_operacional"]]

            monthly_raw = (
                base_op
                .assign(
                    consumo_abs=base_op["valor_saida_cons_interno"].abs(),
                    estoque_op=base_op["valor_saldo_atual"],
                )
                .groupby(
                    [
                        "ano_referencia",
                        "mes_referencia",
                        "tmp_ano_num",
                        "tmp_mes_num",
                    ],
                    as_index=False
                )
                .agg(
                    est_op=("estoque_op", "sum"),
                    con_op=("consumo_abs", "sum"),
                )
                .sort_values(["tmp_ano_num", "tmp_mes_num"])
            )

            giro_lista = []
            cobertura_lista = []
            periodos_lista = []

            for _, row in monthly_raw.iterrows():
                ano_alvo = int(row["tmp_ano_num"])
                mes_alvo = int(row["tmp_mes_num"])

                sub_ytd = monthly_raw[
                    (monthly_raw["tmp_ano_num"] == ano_alvo)
                    & (monthly_raw["tmp_mes_num"] <= mes_alvo)
                ]

                est_medio_ytd = sub_ytd["est_op"].mean()
                con_medio_ytd = sub_ytd["con_op"].mean()

                giro = (
                    con_medio_ytd / est_medio_ytd
                    if est_medio_ytd > 0
                    else 0.0
                )

                cobertura = (
                    est_medio_ytd / con_medio_ytd
                    if con_medio_ytd > 0
                    else 0.0
                )

                giro_lista.append(giro)
                cobertura_lista.append(cobertura)
                periodos_lista.append(periodo_formatado(mes_alvo, ano_alvo))

            df_duplo = pd.DataFrame(
                {
                    "Periodo": periodos_lista,
                    "Giro_Mensal": giro_lista,
                    "Cobertura_Meses": cobertura_lista,
                }
            )

            if not df_duplo.empty:
                df_duplo["Giro_Texto"] = df_duplo["Giro_Mensal"].apply(fmt_dec)
                df_duplo["Cob_Texto"] = df_duplo["Cobertura_Meses"].apply(fmt_mes)

                fig_duplo = go.Figure()

                fig_duplo.add_trace(
                    go.Scatter(
                        x=df_duplo["Periodo"],
                        y=df_duplo["Giro_Mensal"],
                        name="Giro Mensal",
                        mode="lines+markers",
                        line=dict(color="#3498db", width=3),
                        marker=dict(
                            size=8,
                            color="#3498db",
                            line=dict(color="#ffffff", width=2),
                        ),
                        customdata=df_duplo["Giro_Texto"],
                        hovertemplate="Giro: %{customdata}<extra></extra>",
                    )
                )

                fig_duplo.add_trace(
                    go.Scatter(
                        x=df_duplo["Periodo"],
                        y=df_duplo["Cobertura_Meses"],
                        name="Cobertura",
                        mode="lines+markers",
                        line=dict(color="#e74c3c", width=3),
                        marker=dict(
                            size=8,
                            color="#e74c3c",
                            line=dict(color="#ffffff", width=2),
                        ),
                        yaxis="y2",
                        customdata=df_duplo["Cob_Texto"],
                        hovertemplate="Cobertura: %{customdata} meses<extra></extra>",
                    )
                )

                fig_duplo = adicionar_highlight_periodo(
                    fig_duplo,
                    df_duplo,
                    periodo_ativo,
                )

                fig_duplo.update_layout(
                    **layout_padrao(),
                    hovermode="x unified",
                    height=400,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.05,
                        xanchor="right",
                        x=1,
                    ),
                    yaxis=dict(
                        title="",
                        showgrid=True,
                        gridcolor="#232b36",
                        zeroline=False,
                        showticklabels=False,
                    ),
                    yaxis2=dict(
                        title="",
                        overlaying="y",
                        side="right",
                        showgrid=False,
                        zeroline=False,
                        showticklabels=False,
                    ),
                )

                fig_duplo.update_xaxes(showgrid=False, zeroline=False)

                st.plotly_chart(
                    fig_duplo,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="duplo_eixo_giro_cobertura",
                )

        # =====================================================
        # MATERIAIS PARADOS
        # =====================================================

        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(
                """
                <div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 5px; border-left: 3px solid #d85c27; padding-left: 10px;'>
                    ⏳ MATERIAIS PARADOS HÁ MAIS DE 3 MESES
                </div>
                <p style='color: #8c9ba5; font-size: 12px; margin-bottom: 15px;'>
                    Exclui itens Críticos e Obsoletos. Contabiliza o ciclo de inatividade considerando também o mês de origem.
                </p>
                """,
                unsafe_allow_html=True,
            )

            if periodo_ativo:
                mes_atual, ano_atual = parse_periodo(periodo_ativo)
            else:
                mes_atual, ano_atual = max_mes_base, max_ano_base

            snapshot_idx = ano_atual * 12 + mes_atual

            df_calc = df_filtrado[
                (df_filtrado["tempo_idx"] <= snapshot_idx)
                & (df_filtrado["eh_operacional"])
            ]

            df_mov = (
                df_calc[df_calc["valor_saida_cons_interno"].abs() > 0]
                .groupby(
                    ["unidade_almoxarifado", "codigo_produto"],
                    as_index=False
                )["tempo_idx"]
                .max()
                .rename(columns={"tempo_idx": "ultimo_mov_idx"})
            )

            df_min_hist = (
                df_calc
                .groupby(
                    ["unidade_almoxarifado", "codigo_produto"],
                    as_index=False
                )["tempo_idx"]
                .min()
                .rename(columns={"tempo_idx": "primeiro_hist_idx"})
            )

            df_snap_atual = df_calc[
                (df_calc["tmp_ano_num"] == ano_atual)
                & (df_calc["tmp_mes_num"] == mes_atual)
                & (df_calc["qtde_saldo_atual"] > 0)
                & (df_calc["codigo_produto"] != "")
            ]

            df_inativo = pd.merge(
                df_snap_atual,
                df_mov,
                on=["unidade_almoxarifado", "codigo_produto"],
                how="left",
            )

            df_inativo = pd.merge(
                df_inativo,
                df_min_hist,
                on=["unidade_almoxarifado", "codigo_produto"],
                how="left",
            )

            df_inativo["ultimo_mov_idx"] = (
                df_inativo["ultimo_mov_idx"]
                .fillna(df_inativo["primeiro_hist_idx"] - 1)
                .fillna(snapshot_idx)
            )

            df_inativo["meses_parado"] = (
                snapshot_idx - df_inativo["ultimo_mov_idx"]
            ).astype(int)

            df_parados_3m = df_inativo[
                df_inativo["meses_parado"] >= 3
            ]

            if not df_parados_3m.empty:
                df_chart_parados = (
                    df_parados_3m
                    .groupby("meses_parado", as_index=False)
                    ["valor_saldo_atual"]
                    .sum()
                    .sort_values("meses_parado")
                )

                df_chart_parados["Meses_Label"] = (
                    df_chart_parados["meses_parado"].astype(str)
                    + " Meses"
                )

                df_chart_parados["Valor_Label"] = df_chart_parados[
                    "valor_saldo_atual"
                ].apply(
                    lambda x: (
                        f"R$ {x / 1e3:,.0f} mil"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )
                )

                fig_parados = px.bar(
                    df_chart_parados,
                    x="Meses_Label",
                    y="valor_saldo_atual",
                    text="Valor_Label",
                    color_discrete_sequence=["#e74c3c"],
                )

                fig_parados.update_layout(
                    **layout_padrao(),
                    margin=dict(l=40, r=40, t=30, b=10),
                    height=350,
                    showlegend=False,
                    bargap=0.45,
                )

                fig_parados.update_xaxes(
                    title="",
                    showgrid=False,
                    zeroline=False,
                    categoryorder="array",
                    categoryarray=df_chart_parados["Meses_Label"],
                )

                fig_parados.update_yaxes(
                    title="",
                    showgrid=True,
                    gridcolor="#232b36",
                    zeroline=False,
                    showticklabels=False,
                )

                fig_parados.update_traces(
                    textposition="auto",
                    textfont=dict(color="white", size=11),
                )

                st.plotly_chart(
                    fig_parados,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key="grafico_materiais_parados",
                )

                with st.expander("📂 Abrir Lista Completa de Itens Parados"):
                    col_f1, col_f2 = st.columns(2)

                    unidades_paradas = sorted(
                        df_parados_3m["unidade_almoxarifado"]
                        .unique()
                        .tolist()
                    )

                    meses_opcoes = sorted(
                        df_parados_3m["meses_parado"]
                        .unique()
                        .tolist()
                    )

                    with col_f1:
                        unidade_filtro_audit = st.selectbox(
                            "Filtrar por Unidade:",
                            ["Todas as Unidades"] + unidades_paradas,
                            key="select_audit_parados",
                        )

                    with col_f2:
                        meses_filtro_audit = st.selectbox(
                            "Filtrar por Tempo Parado:",
                            ["Todos os Meses"]
                            + [f"{m} Meses" for m in meses_opcoes],
                            key="select_audit_meses",
                        )

                    df_audit_view = df_parados_3m

                    if unidade_filtro_audit != "Todas as Unidades":
                        df_audit_view = df_audit_view[
                            df_audit_view["unidade_almoxarifado"]
                            == unidade_filtro_audit
                        ]

                    if meses_filtro_audit != "Todos os Meses":
                        mes_selecionado = int(
                            meses_filtro_audit.split()[0]
                        )

                        df_audit_view = df_audit_view[
                            df_audit_view["meses_parado"]
                            == mes_selecionado
                        ]

                    df_audit_view = df_audit_view.sort_values(
                        by=["valor_saldo_atual", "meses_parado"],
                        ascending=[False, False],
                    )

                    df_audit_exib = pd.DataFrame(
                        {
                            "Unidade": df_audit_view["unidade_almoxarifado"],
                            "Código SKU": df_audit_view["codigo_produto"],
                            "Nome do Produto": df_audit_view.get(
                                "nome_produto",
                                ""
                            ),
                            "Quantidade": df_audit_view[
                                "qtde_saldo_atual"
                            ].apply(fmt_int),
                            "Valor Parado": df_audit_view[
                                "valor_saldo_atual"
                            ].apply(fmt_brl),
                            "Meses Parado": (
                                df_audit_view["meses_parado"].astype(str)
                                + " meses"
                            ),
                        }
                    )

                    st.dataframe(
                        df_audit_exib,
                        use_container_width=True,
                        hide_index=True,
                    )

                    csv_data = df_audit_exib.to_csv(
                        index=False,
                        sep=";",
                        encoding="utf-8-sig",
                    )

                    st.download_button(
                        label="📥 Baixar Lista Formatada em CSV",
                        data=csv_data,
                        file_name="itens_parados_formatado.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

            else:
                st.info(
                    "Nenhum material operacional parado há mais de 3 meses para o período selecionado."
                )


# =========================================================
# ABA DETALHADA
# =========================================================

with aba_detalhada:
    df_filtrado = aplicar_filtros_base(
        df_completo,
        unidades_ativas,
        unidades_gerenciais,
    )

    df_snapshot, _ = obter_snapshots(
        df_filtrado,
        max_mes_base,
        max_ano_base,
    )

    if not df_snapshot.empty:
        st.markdown(
            """
            <div style='color: #ffffff; font-size: 16px; font-weight: bold; margin-bottom: 15px;'>
                📋 CONSOLIDAÇÃO ANALÍTICA POR UNIDADE DE ALMOXARIFADO
            </div>
            """,
            unsafe_allow_html=True,
        )

        df_tabela_base = df_snapshot.copy()

        df_tabela_base["consumo_abs"] = df_tabela_base[
            "valor_saida_cons_interno"
        ].abs()

        df_tabela_base["sku_ativo"] = np.where(
            (df_tabela_base["qtde_saldo_atual"] > 0)
            & (df_tabela_base["codigo_produto"] != ""),
            df_tabela_base["codigo_produto"],
            np.nan,
        )

        df_tabela = (
            df_tabela_base
            .groupby("unidade_almoxarifado", as_index=False)
            .agg(
                Valor_Estoque=("valor_saldo_atual", "sum"),
                Valor_Compras=("valor_entrada_compras", "sum"),
                Valor_Consumo=("consumo_abs", "sum"),
                SKUs_Ativos=("sku_ativo", "nunique"),
            )
            .sort_values("Valor_Estoque", ascending=False)
        )

        df_exibicao = pd.DataFrame(
            {
                "Unidade de Almoxarifado": df_tabela[
                    "unidade_almoxarifado"
                ],
                "Valor em Estoque": df_tabela["Valor_Estoque"].apply(
                    fmt_brl
                ),
                "Valor de Compras": df_tabela["Valor_Compras"].apply(
                    fmt_brl
                ),
                "Valor de Consumo": df_tabela["Valor_Consumo"].apply(
                    fmt_brl
                ),
                "SKUs Ativos": df_tabela["SKUs_Ativos"].apply(fmt_int),
            }
        )

        st.dataframe(
            df_exibicao,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")
