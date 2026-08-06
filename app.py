import pandas as pd
import streamlit as st
from supabase import create_client

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# Inicialização dos estados para o painel de filtros
if 'show_filters' not in st.session_state:
    st.session_state.show_filters = False

# 1. Conexão direta e segura com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Performance: Busca das colunas financeiras + colunas de filtro
# Ajuste os nomes "unidade_almoxarifado", "mes_referencia" e "ano_referencia" conforme seu banco
@st.cache_data(ttl=300)
def carregar_dados():
    try:
        response = supabase.table(table_name).select(
            "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno, unidade_almoxarifado, mes_referencia, ano_referencia"
        ).execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

df_completo = carregar_dados()

# 3. Estilização CSS (Design fiel + customização do botão do Streamlit)
st.markdown("""
<style>
    /* Fundo geral escuro */
    .stApp {
        background-color: #0f141c;
    }
    
    /* Customização dos botões nativos do Streamlit para combinar com o tema */
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

    /* Container de Filtros */
    .filter-panel {
        background-color: #161c24;
        border: 1px solid #232b36;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 25px;
    }
    
    /* Topo: Logo e Título */
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
    
    /* Estilo dos Cards Escuros */
    .card-box {
        background-color: #161c24;
        border: 1px solid #232b36;
        border-radius: 8px;
        padding: 20px;
        height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
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

# 4. Renderização do Cabeçalho com o Botão de Filtro
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
    st.markdown("<br>", unsafe_allow_html=True) # Alinhamento vertical
    if st.button("⚙️ Filtros", use_container_width=True):
        st.session_state.show_filters = not st.session_state.show_filters

# 5. Lógica e UI do Painel Retrátil de Filtros
df_filtrado = df_completo.copy()

if st.session_state.show_filters:
    with st.container():
        st.markdown('<div class="filter-panel">', unsafe_allow_html=True)
        st.markdown("<h4 style='color: white;'>Filtros de Análise</h4>", unsafe_allow_html=True)
        
        f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])
        
        # Puxando dinamicamente as opções (com validação caso o df esteja vazio)
        unidades_opcoes = ["Todas"] + sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else ["Todas"]
        mes_opcoes = ["Todos"] + sorted(df_completo["mes_referencia"].dropna().unique().tolist()) if not df_completo.empty else ["Todos"]
        ano_opcoes = ["Todos"] + sorted(df_completo["ano_referencia"].dropna().unique().tolist()) if not df_completo.empty else ["Todos"]

        with f_col1:
            unidade_selecionada = st.selectbox("Unidade:", unidades_opcoes)
        with f_col2:
            mes_selecionado = st.selectbox("Mês:", mes_opcoes)
        with f_col3:
            ano_selecionado = st.selectbox("Ano:", ano_opcoes)
        with f_col4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Aplicar", use_container_width=True):
                st.session_state.show_filters = False # Fecha o painel após aplicar
                st.rerun()
                
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Aplicação dos filtros no DataFrame
        if unidade_selecionada != "Todas":
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"] == unidade_selecionada]
        if mes_selecionado != "Todos":
            df_filtrado = df_filtrado[df_filtrado["mes_referencia"] == mes_selecionado]
        if ano_selecionado != "Todos":
            df_filtrado = df_filtrado[df_filtrado["ano_referencia"] == ano_selecionado]

# 6. Tratamento de Dados e Somas Dinâmicas
def somar_coluna(dataframe, coluna):
    if coluna not in dataframe.columns or dataframe.empty:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

val_estoque = somar_coluna(df_filtrado, "valor_saldo_atual")
val_compras = somar_coluna(df_filtrado, "valor_entrada_compras")
val_consumo = somar_coluna(df_filtrado, "valor_saida_cons_interno")

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# 7. Renderização dos Cards na Grade
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

c3, _ = st.columns(2)

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
