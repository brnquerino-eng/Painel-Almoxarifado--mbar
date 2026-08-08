from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# Inicialização dos estados para os filtros múltiplos
if 'f_unidades' not in st.session_state:
    st.session_state.f_unidades = []
if 'f_meses' not in st.session_state:
    st.session_state.f_meses = []
if 'f_anos' not in st.session_state:
    st.session_state.f_anos = []

# 1. Conexão direta e segura com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Performance Otimizada e Estável (Conexões Controladas)
@st.cache_data()
def carregar_dados():
    try:
        with st.spinner("Carregando e normalizando base de dados em alta performance..."):
            count_res = supabase.table(table_name).select("*", count="exact", head=True).execute()
            total_rows = getattr(count_res, 'count', None)

            if not total_rows or total_rows == 0:
                total_rows = 460000  # Fallback de segurança

            batch_size = 1000
            ranges = [(i, min(i + batch_size - 1, total_rows - 1)) for i in range(0, total_rows, batch_size)]

            all_data = []

            def fetch_range(start_r, end_r):
                res = supabase.table(table_name).select(
                    "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno, unidade_almoxarifado, mes_referencia, ano_referencia, codigo_produto, qtde_saldo_atual"
                ).order("id").range(start_r, end_r).execute()
                return res.data if res.data else []

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(fetch_range, s, e) for s, e in ranges]
                for future in futures:
                    data = future.result()
                    if data:
                        all_data.extend(data)

            if not all_data:
                return pd.DataFrame()

            df = pd.DataFrame(all_data)

            if "unidade_almoxarifado" in df.columns:
                df["unidade_almoxarifado"] = df["unidade_almoxarifado"].astype(str).str.strip().str.upper()

            def limpar_valor(val):
                if pd.isna(val) or val is None:
                    return ""
                s_val = str(val).strip()
                if s_val.endswith('.0'):
                    s_val = s_val[:-2]
                return s_val

            for col in ["mes_referencia", "ano_referencia", "codigo_produto"]:
                if col in df.columns:
                    df[col] = df[col].apply(limpar_valor)

            for col in ["valor_saldo_atual", "valor_entrada_compras", "valor_saida_cons_interno", "qtde_saldo_atual"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            return df
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return pd.DataFrame()

df_completo = carregar_dados()

unidades_opcoes = sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else []

unidades_gerenciais = [u for u in unidades_opcoes if "GERENCIAL" in u]
unidades_ativas = [u for u in unidades_opcoes if "GERENCIAL" not in u]

def _chave_numerica(val):
    try:
        return (0, int(val))
    except (ValueError, TypeError):
        return (1, str(val))

# Dicionário de Mapeamento de Meses para Exibição Executiva
dict_meses_nome = {
    "1": "01 - Janeiro", "01": "01 - Janeiro",
    "2": "02 - Fevereiro", "02": "02 - Fevereiro",
    "3": "03 - Março", "03": "03 - Março",
    "4": "04 - Abril", "04": "04 - Abril",
    "5": "05 - Maio", "05": "05 - Maio",
    "6": "06 - Junho", "06": "06 - Junho",
    "7": "07 - Julho", "07": "07 - Julho",
    "8": "08 - Agosto", "08": "08 - Agosto",
    "9": "09 - Setembro", "09": "09 - Setembro",
    "10": "10 - Outubro", "10": "10 - Outubro",
    "11": "11 - Novembro", "11": "11 - Novembro",
    "12": "12 - Dezembro", "12": "12 - Dezembro"
}

raw_meses = sorted(df_completo["mes_referencia"].dropna().unique().tolist(), key=_chave_numerica) if not df_completo.empty else []
map_raw_para_fmt = {m: dict_meses_nome.get(str(m).strip(), f"{str(m).strip().zfill(2)} - Mês {m}") for m in raw_meses}
map_fmt_para_raw = {v: k for k, v in map_raw_para_fmt.items()}
meses_opcoes_formatadas = list(map_raw_para_fmt.values())

ano_opcoes = sorted(df_completo["ano_referencia"].dropna().unique().tolist(), key=_chave_numerica) if not df_completo.empty else []

# 3. Definição da Modal com Seleção Múltipla
@st.dialog("Filtros de Análise - Visão Executiva", width="large")
def modal_filtros():
    st.markdown("<p style='color: #8c9ba5; font-size: 13px; margin-bottom: 20px;'>Selecione uma ou mais opções para consolidar os dados (deixe em branco para considerar todas):</p>", unsafe_allow_html=True)

    col_u1, col_u2 = st.columns(2)

    with col_u1:
        default_ativas = [u for u in st.session_state.f_unidades if u in unidades_ativas]
        f_ativas_sel = st.multiselect("🏢 Unidades Ativas:", unidades_ativas, default=default_ativas)

    with col_u2:
        default_gerenciais = [u for u in st.session_state.f_unidades if u in unidades_gerenciais]
        f_gerenciais_sel = st.multiselect("📊 Unidades Gerenciais:", unidades_gerenciais, default=default_gerenciais)

    f_unidades_sel = f_ativas_sel + f_gerenciais_sel

    default_meses_fmt = [map_raw_para_fmt[m] for m in st.session_state.f_meses if m in map_raw_para_fmt]
    f_meses_sel_fmt = st.multiselect("Meses de Referência:", meses_opcoes_formatadas, default=default_meses_fmt)

    f_anos_sel = st.multiselect("Anos de Referência:", ano_opcoes, default=st.session_state.f_anos)

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("Limpar Filtros", use_container_width=True):
            st.session_state.f_unidades = []
            st.session_state.f_meses = []
            st.session_state.f_anos = []
            st.rerun()
    with col_btn2:
        if st.button("Aplicar Filtros", use_container_width=True, type="primary"):
            st.session_state.f_unidades = f_unidades_sel
            st.session_state.f_meses = [map_fmt_para_raw[f] for f in f_meses_sel_fmt]
            st.session_state.f_anos = f_anos_sel
            st.rerun()

# 4. Estilização CSS Avançada
st.markdown("""
<style>
    @keyframes smoothPageLoad {
        0% { opacity: 0.2; transform: scale(0.98); }
        100% { opacity: 1; transform: scale(1); }
    }
    .stApp {
        background-color: #0f141c;
        animation: smoothPageLoad 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }
    @keyframes scaleInModal {
        0% { opacity: 0; transform: scale(0.8) translateY(-20px); }
        100% { opacity: 1; transform: scale(1) translateY(0); }
    }
    @keyframes fadeInScrim {
        0% { opacity: 0; backdrop-filter: blur(0px); }
        100% { opacity: 1; backdrop-filter: blur(5px); }
    }
    div[role="dialog"], div[data-testid="stDialog"] {
        animation: scaleInModal 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
        transform-origin: center center;
    }
    div[data-testid="stModalScrim"] {
        background-color: rgba(15, 20, 28, 0.7) !important;
        animation: fadeInScrim 0.6s ease-out forwards !important;
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
    .card-box {
        background-color: #161c24;
        border: 1px solid #232b36;
        border-radius: 8px;
        padding: 20px;
        height: 120px;
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
    .icon-estoque { background-color: #132a24; color: #2ecc71; }
    .icon-compras { background-color: #2a2211; color: #f39c12; }
    .icon-consumo { background-color: #2a1515; color: #e74c3c; }
    .icon-skus { background-color: #1a222d; color: #3498db; }
    .card-title {
        color: #8c9ba5;
        font-size: 12px;
        font-weight: bold;
        letter-spacing: 0.5px;
    }
    .card-value {
        color: #ffffff;
        font-size: 26px;
        font-weight: bold;
        text-align: center;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# 5. Renderização do Cabeçalho com o Botão de Filtro
col_header, col_btn = st.columns([5, 1])

with col_header:
    st.markdown(f"""
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
    """, unsafe_allow_html=True)

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    filtro_ativo = bool(st.session_state.f_unidades or st.session_state.f_meses or st.session_state.f_anos)
    label_botao = "⚙️ Filtros (Ativo)" if filtro_ativo else "⚙️ Filtros"

    if st.button(label_botao, use_container_width=True):
        modal_filtros()

# 5.1 Renderização do Resumo Inteligente de Quantidades
f_unidades_atuais = st.session_state.get('f_unidades', [])

if not f_unidades_atuais:
    texto_informativo = "Exibindo dados consolidados de **todas as unidades** (Ativas e Gerenciais)."
else:
    sel_ativas = [u for u in f_unidades_atuais if u in unidades_ativas]
    sel_gerenciais = [u for u in f_unidades_atuais if u in unidades_gerenciais]

    partes = []
    if sel_ativas:
        partes.append(f"**{len(sel_ativas)} unidade(s) ativa(s)**")
    if sel_gerenciais:
        partes.append(f"**{len(sel_gerenciais)} gerencial(is)**")

    texto_informativo = "Exibindo dados de " + " e ".join(partes) + "."

st.markdown(f"<p style='color: #8c9ba5; font-size: 14px; margin-top: -10px; margin-bottom: 20px;'>{texto_informativo}</p>", unsafe_allow_html=True)

# 6. Filtragem Rigorosa e Precisa
df_filtrado = df_completo.copy()

if st.session_state.f_unidades:
    df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(st.session_state.f_unidades)]
if st.session_state.f_meses:
    df_filtrado = df_filtrado[df_filtrado["mes_referencia"].isin(st.session_state.f_meses)]
if st.session_state.f_anos:
    df_filtrado = df_filtrado[df_filtrado["ano_referencia"].isin(st.session_state.f_anos)]

# 7. Somas e Contagens Dinâmicas baseadas na quantidade física
def somar_coluna(dataframe, coluna):
    if coluna not in dataframe.columns or dataframe.empty:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

val_estoque = somar_coluna(df_filtrado, "valor_saldo_atual")
val_compras = somar_coluna(df_filtrado, "valor_entrada_compras")
val_consumo = somar_coluna(df_filtrado, "valor_saida_cons_interno")

if "qtde_saldo_atual" in df_filtrado.columns and "codigo_produto" in df_filtrado.columns:
    df_skus_ativos = df_filtrado[
        (df_filtrado["qtde_saldo_atual"] > 0) & (df_filtrado["codigo_produto"] != "")
    ]
    val_skus = df_skus_ativos["codigo_produto"].nunique()
else:
    val_skus = 0

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def fmt_int(val):
    return f"{val:,}".replace(',', '.')

# ==========================================
# 8. SISTEMA DE ABAS NATIVO
# ==========================================
aba_geral, aba_detalhada = st.tabs(["📈 Visão Geral", "📊 Análises Detalhadas & Tendência de Estoque"])

with aba_geral:
    # 8.1 Cards Executivos
    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-estoque">📦</div>
                <div class="card-title">VALOR TOTAL EM ESTOQUE</div>
            </div>
            <div class="card-value">{fmt_brl(val_estoque)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-compras">🛒</div>
                <div class="card-title">VALOR TOTAL DE COMPRA</div>
            </div>
            <div class="card-value">{fmt_brl(val_compras)}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    c3, c4 = st.columns(2)

    with c3:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-consumo">📉</div>
                <div class="card-title">VALOR TOTAL DE CONSUMO</div>
            </div>
            <div class="card-value">{fmt_brl(val_consumo)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-skus">🏷️</div>
                <div class="card-title">TOTAL DE SKUs ÚNICOS</div>
            </div>
            <div class="card-value">{fmt_int(val_skus)}</div>
        </div>
        """, unsafe_allow_html=True)

    # 9. GRÁFICOS INTERATIVOS
    st.markdown("<br><br>", unsafe_allow_html=True)

    if not df_filtrado.empty:
        layout_transparente = dict(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#8c9ba5'),
            margin=dict(l=10, r=10, t=10, b=10)
        )

        col_g1, col_g2 = st.columns([6, 4], gap="large")

        with col_g1:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📈 EVOLUÇÃO: COMPRAS VS CONSUMO</div>", unsafe_allow_html=True)

                df_trend = df_filtrado.copy()
                df_trend['ano_num'] = pd.to_numeric(df_trend['ano_referencia'], errors='coerce').fillna(0)
                df_trend['mes_num'] = pd.to_numeric(df_trend['mes_referencia'], errors='coerce').fillna(0)

                df_tempo = df_trend.groupby(['ano_referencia', 'mes_referencia', 'ano_num', 'mes_num'])[['valor_entrada_compras', 'valor_saida_cons_interno']].sum().reset_index()
                df_tempo = df_tempo.sort_values(['ano_num', 'mes_num'])
                df_tempo['Periodo'] = df_tempo['mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_tempo['ano_referencia'].astype(str)

                df_tempo['valor_saida_cons_interno'] = df_tempo['valor_saida_cons_interno'].abs()

                fig_linha = go.Figure()
                fig_linha.add_trace(go.Scatter(x=df_tempo['Periodo'], y=df_tempo['valor_entrada_compras'],
                                              name='Compras', mode='lines+markers', line=dict(color='#f39c12', width=3)))
                fig_linha.add_trace(go.Scatter(x=df_tempo['Periodo'], y=df_tempo['valor_saida_cons_interno'],
                                              name='Consumo', mode='lines+markers', line=dict(color='#e74c3c', width=3)))

                fig_linha.update_layout(**layout_transparente, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1))
                fig_linha.update_xaxes(showgrid=False, zeroline=False)
                fig_linha.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, tickprefix="R$ ")

                st.plotly_chart(fig_linha, use_container_width=True, config={'displayModeBar': False})

        with col_g2:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #e74c3c; padding-left: 10px;'>🏆 TOP 10: MAIOR VALOR EM ESTOQUE</div>", unsafe_allow_html=True)

                df_rank = df_filtrado.groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                df_rank = df_rank[df_rank['valor_saldo_atual'] > 0]
                df_rank = df_rank.sort_values('valor_saldo_atual', ascending=True).tail(10)

                df_rank['texto_formatado'] = df_rank['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e6:.1f}M".replace('.', ','))

                fig_bar = px.bar(df_rank, x='valor_saldo_atual', y='unidade_almoxarifado', orientation='h',
                                 color_discrete_sequence=['#e74c3c'], text='texto_formatado')

                fig_bar.update_layout(**layout_transparente, hovermode="y unified")
                fig_bar.update_traces(textposition='auto', textfont=dict(color='white'))
                fig_bar.update_xaxes(title="", showgrid=True, gridcolor='#232b36', tickprefix="R$ ", zeroline=False)
                fig_bar.update_yaxes(title="", showgrid=False)

                st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

        # 10. EVOLUÇÃO TEMPORAL DE SKUS ATIVOS
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #e74c3c; padding-left: 10px;'>📦 EVOLUÇÃO DO MIX: TOTAL DE SKUs ATIVOS NO TEMPO</div>", unsafe_allow_html=True)

            df_sku_trend = df_filtrado[
                (df_filtrado["qtde_saldo_atual"] > 0) & (df_filtrado["codigo_produto"] != "")
            ].copy()
            df_sku_trend['ano_num'] = pd.to_numeric(df_sku_trend['ano_referencia'], errors='coerce').fillna(0)
            df_sku_trend['mes_num'] = pd.to_numeric(df_sku_trend['mes_referencia'], errors='coerce').fillna(0)

            df_sku_tempo = df_sku_trend.groupby(['ano_referencia', 'mes_referencia', 'ano_num', 'mes_num'])['codigo_produto'].nunique().reset_index()
            df_sku_tempo = df_sku_tempo.sort_values(['ano_num', 'mes_num'])
            df_sku_tempo['Periodo'] = df_sku_tempo['mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_sku_tempo['ano_referencia'].astype(str)

            textos_skus = [f"{val:,}".replace(',', '.') for val in df_sku_tempo['codigo_produto']]
            max_y = df_sku_tempo['codigo_produto'].max() if not df_sku_tempo.empty else 100
            n_pontos = len(df_sku_tempo)

            total_skus_grafico = df_sku_trend['codigo_produto'].nunique()
            total_formatado = f"{total_skus_grafico:,}".replace(',', '.')

            layout_sku = dict(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#8c9ba5'),
                margin=dict(l=40, r=40, t=50, b=10),
                annotations=[
                    dict(
                        x=1.0,
                        y=1.12,
                        xref="paper",
                        yref="paper",
                        text=f"<b>Total Período:</b> {total_formatado}",
                        showarrow=False,
                        font=dict(color="#ffffff", size=12, family="monospace"),
                        bgcolor="#1a222d",
                        bordercolor="#333d4d",
                        borderwidth=1,
                        borderpad=6,
                        align="right"
                    )
                ]
            )

            fig_sku_linha = go.Figure()
            fig_sku_linha.add_trace(go.Scatter(
                x=df_sku_tempo['Periodo'],
                y=df_sku_tempo['codigo_produto'],
                customdata=textos_skus,
                name='SKUs Ativos',
                mode='lines+markers+text',
                text=textos_skus,
                textposition='top center',
                textfont=dict(color='white', size=11),
                line=dict(color='#e74c3c', width=3),
                fill='tozeroy',
                fillcolor='rgba(231, 76, 60, 0.1)',
                hovertemplate='<b>Período:</b> %{x}<br><b>SKUs Ativos:</b> %{customdata}<extra></extra>'
            ))

            fig_sku_linha.update_layout(**layout_sku, hovermode="x unified", showlegend=False)
            fig_sku_linha.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, n_pontos - 0.2])
            fig_sku_linha.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[0, max_y * 1.15], showticklabels=False)

            st.plotly_chart(fig_sku_linha, use_container_width=True, config={'displayModeBar': False})

    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")

with aba_detalhada:
    st.markdown("<div style='color: #ffffff; font-size: 16px; font-weight: bold; margin-bottom: 20px;'>📊 TENDÊNCIA DE ESTOQUE TOTAL NO TEMPO</div>", unsafe_allow_html=True)
    
    if not df_filtrado.empty:
        # Gráfico de Barras: Valor Total em Estoque por Mês/Ano (Com colunas mais finas, bordas e sem títulos/números poluindo)
        df_estoque_trend = df_filtrado.copy()
        df_estoque_trend['ano_num'] = pd.to_numeric(df_estoque_trend['ano_referencia'], errors='coerce').fillna(0)
        df_estoque_trend['mes_num'] = pd.to_numeric(df_estoque_trend['mes_referencia'], errors='coerce').fillna(0)

        df_estoque_mes = df_estoque_trend.groupby(['ano_referencia', 'mes_referencia', 'ano_num', 'mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_estoque_mes = df_estoque_mes.sort_values(['ano_num', 'mes_num'])
        df_estoque_mes['Periodo'] = df_estoque_mes['mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_estoque_mes['ano_referencia'].astype(str)

        # Customdata para exibir o valor formatado bonitinho no hover
        def fmt_hover_brl(val):
            return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        df_estoque_mes['hover_valor'] = df_estoque_mes['valor_saldo_atual'].apply(fmt_hover_brl)

        layout_barra_estoque = dict(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#8c9ba5'),
            margin=dict(l=40, r=40, t=40, b=10)
        )

        fig_bar_estoque = go.Figure(go.Bar(
            x=df_estoque_mes['Periodo'],
            y=df_estoque_mes['valor_saldo_atual'],
            customdata=df_estoque_mes['hover_valor'],
            marker=dict(
                color='#e74c3c',
                line=dict(color='#ff6b5b', width=2)  # Borda clara e elegante nas barras
            ),
            width=0.45,  # Colunas mais finas e elegantes
            hovertemplate='<b>Período:</b> %{x}<br><b>Estoque Total:</b> %{customdata}<extra></extra>'
        ))

        fig_bar_estoque.update_layout(**layout_barra_estoque, hovermode="x unified", showlegend=False)
        fig_bar_estoque.update_xaxes(title="", showgrid=False, zeroline=False)  # Remove o nome "Periodo"
        fig_bar_estoque.update_yaxes(title="", showgrid=True, gridcolor='#232b36', zeroline=False, tickprefix="R$ ")  # Remove o nome "valor_saldo_atual"

        st.plotly_chart(fig_bar_estoque, use_container_width=True, config={'displayModeBar': False})

        st.markdown("<br><hr style='border-color: #232b36;'><br>", unsafe_allow_html=True)
        st.markdown("<div style='color: #ffffff; font-size: 16px; font-weight: bold; margin-bottom: 15px;'>📋 CONSOLIDAÇÃO ANALÍTICA POR UNIDADE DE ALMOXARIFADO</div>", unsafe_allow_html=True)
        
        # Tabela Dinâmica por Unidade
        df_tabela = df_filtrado.groupby('unidade_almoxarifado').agg(
            Valor_Estoque=('valor_saldo_atual', 'sum'),
            Valor_Compras=('valor_entrada_compras', 'sum'),
            Valor_Consumo=('valor_saida_cons_interno', lambda x: x.abs().sum()),
            SKUs_Ativos=('codigo_produto', lambda x: x[df_filtrado.loc[x.index, 'qtde_saldo_atual'] > 0].nunique())
        ).reset_index()

        df_tabela = df_tabela.sort_values(by='Valor_Estoque', ascending=False)

        df_exibicao = pd.DataFrame()
        df_exibicao['Unidade de Almoxarifado'] = df_tabela['unidade_almoxarifado']
        df_exibicao['Valor em Estoque'] = df_tabela['Valor_Estoque'].apply(fmt_brl)
        df_exibicao['Valor de Compras'] = df_tabela['Valor_Compras'].apply(fmt_brl)
        df_exibicao['Valor de Consumo'] = df_tabela['Valor_Consumo'].apply(fmt_brl)
        df_exibicao['SKUs Ativos'] = df_tabela['SKUs_Ativos'].apply(fmt_int)

        st.dataframe(
            df_exibicao,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")
