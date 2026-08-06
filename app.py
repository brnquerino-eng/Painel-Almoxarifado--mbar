import pandas as pd
import streamlit as st
from supabase import create_client

# Configuração da página para ocupar a tela toda
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# 1. Conexão direta e segura com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Performance: Busca apenas as colunas necessárias para a soma
@st.cache_data(ttl=300)
def carregar_dados():
    try:
        response = supabase.table(table_name).select(
            "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno"
        ).execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

df = carregar_dados()

# 3. Tratamento de Dados e Somas
def somar_coluna(dataframe, coluna):
    if coluna not in dataframe.columns or dataframe.empty:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

val_estoque = somar_coluna(df, "valor_saldo_atual")
val_compras = somar_coluna(df, "valor_entrada_compras")
val_consumo = somar_coluna(df, "valor_saida_cons_interno")

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# 4. Estilização CSS para réplica exata do Painel
st.markdown("""
<style>
    /* Fundo geral escuro */
    .stApp {
        background-color: #0f141c;
    }
    
    /* Topo: Logo e Título */
    .header-container {
        display: flex;
        align-items: center;
        border-bottom: 2px solid #d85c27;
        padding-bottom: 12px;
        margin-bottom: 30px;
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
    
    /* Cores dos Ícones */
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

# 5. Renderização do Cabeçalho
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

# 6. Renderização dos Cards na Grade (Linha 1 e Linha 2)
col1, col2 = st.columns(2)

with col1:
    st.markdown(f"""
    <div class="card-box">
        <div class="card-header">
            <div class="icon-box icon-estoque">📦</div>
            <div class="card-title">VALOR TOTAL EM ESTOQUE</div>
        </div>
        <div class="card-value">{fmt_brl(val_estoque)}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
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

col3, _ = st.columns(2)

with col3:
    st.markdown(f"""
    <div class="card-box">
        <div class="card-header">
            <div class="icon-box icon-consumo">📉</div>
            <div class="card-title">VALOR TOTAL DE CONSUMO</div>
        </div>
        <div class="card-value">{fmt_brl(val_consumo)}</div>
    </div>
    """, unsafe_allow_html=True)
