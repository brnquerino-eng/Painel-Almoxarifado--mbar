import pandas as pd
import streamlit as st
from supabase import create_client

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# 1. Conexão direta com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Consulta de Dados Otimizada (Traz apenas o que vai somar)
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

# 3. Tratamento e Soma Segura
def somar_coluna(dataframe, coluna):
    if coluna not in dataframe.columns or dataframe.empty:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

val_estoque = somar_coluna(df, "valor_saldo_atual")
val_compras = somar_coluna(df, "valor_entrada_compras")
val_consumo = somar_coluna(df, "valor_saida_cons_interno")

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# 4. Layout 
st.markdown("### VISÃO EXECUTIVA DE ESTOQUE")
st.markdown("Valores Consolidados")
st.markdown("---")

# Linha 1: Estoque e Compras
col1, col2 = st.columns(2)

with col1:
    st.metric("VALOR TOTAL EM ESTOQUE", fmt_brl(val_estoque))

with col2:
    st.metric("VALOR TOTAL DE COMPRA", fmt_brl(val_compras))

# Linha 2: Consumo
col3, col4 = st.columns(2)

with col3:
    st.metric("VALOR TOTAL DE CONSUMO", fmt_brl(val_consumo))
