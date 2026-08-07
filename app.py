from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# Inicialização dos estados
if 'f_unidades' not in st.session_state: st.session_state.f_unidades = []
if 'f_meses' not in st.session_state: st.session_state.f_meses = []
if 'f_anos' not in st.session_state: st.session_state.f_anos = []

@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

@st.cache_data()
def carregar_dados():
    # ... (Lógica de dados permanece idêntica)
    try:
        res = supabase.table(table_name).select("*").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

df_completo = carregar_dados()
unidades_opcoes = sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else []
unidades_gerenciais = [u for u in unidades_opcoes if "GERENCIAL" in u]
unidades_ativas = [u for u in unidades_opcoes if "GERENCIAL" not in u]
mes_opcoes = sorted(df_completo["mes_referencia"].dropna().unique().tolist(), key=lambda x: str(x)) if not df_completo.empty else []
ano_opcoes = sorted(df_completo["ano_referencia"].dropna().unique().tolist(), key=lambda x: str(x)) if not df_completo.empty else []

@st.dialog("Filtros de Análise", width="large")
def modal_filtros():
    # ... (Modal permanece igual)
    f_ativas_sel = st.multiselect("🏢 Unidades Ativas:", unidades_ativas, default=[u for u in st.session_state.f_unidades if u in unidades_ativas])
    f_gerenciais_sel = st.multiselect("📊 Unidades Gerenciais:", unidades_gerenciais, default=[u for u in st.session_state.f_unidades if u in unidades_gerenciais])
    f_meses_sel = st.multiselect("Meses:", mes_opcoes, default=st.session_state.f_meses)
    f_anos_sel = st.multiselect("Anos:", ano_opcoes, default=st.session_state.f_anos)
    if st.button("Aplicar Filtros", type="primary"):
        st.session_state.f_unidades = f_ativas_sel + f_gerenciais_sel
        st.session_state.f_meses = f_meses_sel
        st.session_state.f_anos = f_anos_sel
        st.rerun()

# 4. CSS FORÇADO (O PULO DO GATO)
st.markdown("""
<style>
    /* Estilo para os cards */
    .card-box {
        background-color: #161c24;
        border: 1px solid #232b36;
        border-radius: 8px;
        padding: 20px;
        height: 120px;
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5);
    }
    
    /* CSS FORÇADO PARA OS CONTAINERS COM BORDER=TRUE */
    div[data-testid="stContainer"] {
        background-color: #161c24 !important;
        border: 1px solid #232b36 !important;
        border-radius: 8px !important;
        padding: 20px !important;
        /* Sombra pesada para criar elevação */
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8) !important;
        /* Libera a sombra que estava sendo cortada */
        overflow: visible !important;
        margin-bottom: 20px !important;
    }
</style>
""", unsafe_allow_html=True)

# ... (Renderização Cabeçalho e Cards permanece igual)
st.markdown("### Visão Geral")
col_header, col_btn = st.columns([5, 1])
if col_btn.button("⚙️ Filtros"): modal_filtros()

# 9. GRÁFICOS (USANDO CONTAINER NATIVO FORÇADO)
st.markdown("<br>", unsafe_allow_html=True)
if not df_completo.empty:
    col_g1, col_g2 = st.columns([6, 4], gap="large")
    
    with col_g1:
        # Usamos o container nativo, mas o CSS acima vai "hackear" a aparência dele
        with st.container(border=True):
            st.markdown("📈 EVOLUÇÃO: COMPRAS VS CONSUMO")
            # ... (Lógica do gráfico permanece igual)
            fig_linha = go.Figure()
            # [Lógica do Plotly]
            st.plotly_chart(fig_linha, use_container_width=True, config={'displayModeBar': False})

    with col_g2:
        with st.container(border=True):
            st.markdown("🏆 TOP 10: MAIOR VALOR EM ESTOQUE")
            # ... (Lógica do gráfico permanece igual)
            fig_bar = px.bar(...)
            st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})
