import pandas as pd
import streamlit as st
from supabase import create_client

# Configuração da página
st.set_page_config(page_title="Painel Executivo - Almoxarifado", layout="wide")

st.title("📊 Painel Executivo - Gestão de Estoque & Operação")
st.markdown("---")

# 1. Conexão direta com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()

# 2. Nome da tabela fixado no código (Zero interação necessária)
table_name = "painel_estoque"

# 3. Consulta de Dados
@st.cache_data(ttl=300)
def carregar_dados(tabela):
    try:
        response = supabase.table(tabela).select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

df = carregar_dados(table_name)

if df.empty:
    st.error(f"⚠️ Nenhum dado retornado da tabela '{table_name}'. Verifique a conexão com o banco.")
    st.stop()

# 4. Mapeamento das Colunas Principais
COL_UNIDADE = "unidade_almoxarifado"
COL_FAMILIA = "familia"
COL_CATEGORIA = "categoria"

COL_ESTOQUE_VALOR = "valor_saldo_atual"
COL_COMPRAS_VALOR = "valor_entrada_compras"
COL_CONSUMO_VALOR = "valor_saida_cons_interno"

# 5. Filtros Dinâmicos na Barra Lateral
st.sidebar.subheader("🔍 Filtros Dinâmicos")

df_filtrado = df.copy()

if COL_UNIDADE in df.columns:
    unidades_unicas = sorted(df[COL_UNIDADE].dropna().astype(str).unique().tolist())
    unidades_selecionadas = st.sidebar.multiselect("Filtrar Unidades", unidades_unicas, default=unidades_unicas)
    if unidades_selecionadas:
        df_filtrado = df_filtrado[df_filtrado[COL_UNIDADE].astype(str).isin(unidades_selecionadas)]

if COL_FAMILIA in df.columns:
    familias_unicas = sorted(df[COL_FAMILIA].dropna().astype(str).unique().tolist())
    familias_selecionadas = st.sidebar.multiselect("Filtrar Família", familias_unicas, default=familias_unicas)
    if familias_selecionadas:
        df_filtrado = df_filtrado[df_filtrado[COL_FAMILIA].astype(str).isin(familias_selecionadas)]

if COL_CATEGORIA in df.columns:
    categorias_unicas = sorted(df[COL_CATEGORIA].dropna().astype(str).unique().tolist())
    categorias_selecionadas = st.sidebar.multiselect("Filtrar Categoria", categorias_unicas, default=categorias_unicas)
    if categorias_selecionadas:
        df_filtrado = df_filtrado[df_filtrado[COL_CATEGORIA].astype(str).isin(categorias_selecionadas)]

# 6. Tratamento e Soma Segura
def somar_coluna(dataframe, coluna):
    if coluna not in dataframe.columns or dataframe.empty:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

val_estoque = somar_coluna(df_filtrado, COL_ESTOQUE_VALOR)
val_compras = somar_coluna(df_filtrado, COL_COMPRAS_VALOR)
val_consumo = somar_coluna(df_filtrado, COL_CONSUMO_VALOR)

# Formatador de Moeda
def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# 7. Renderização dos KPIs Principais
st.subheader("💰 Indicadores Financeiros Principais")
k1, k2, k3, k4 = st.columns(4)

with k1:
    total_unds = df_filtrado[COL_UNIDADE].nunique() if COL_UNIDADE in df_filtrado.columns else 0
    st.metric("UNIDADES NA VISÃO", total_unds)
with k2:
    st.metric("VALOR TOTAL ESTOQUE", fmt_brl(val_estoque))
with k3:
    st.metric("TOTAL DE COMPRAS", fmt_brl(val_compras))
with k4:
    st.metric("TOTAL DE CONSUMO INTERNO", fmt_brl(val_consumo))

st.markdown("---")

# 8. Tabela de Dados Detalhada
st.subheader("📋 Base de Dados Completa")
st.dataframe(df_filtrado, use_container_width=True)
