import streamlit as st
import pandas as pd
from supabase import create_client, Client

# 1. Configuração simples da página
st.set_page_config(
    page_title="Painel de Estoque",
    page_icon="📦",
    layout="wide"
)

# 2. Conexão com o Supabase
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

# 3. Busca de Dados
@st.cache_data(ttl=300)
def load_data():
    response = supabase.table("painel_estoque").select("*").execute()
    if response.data:
        return pd.DataFrame(response.data)
    return pd.DataFrame()

# 4. Tela Básica
st.title("📦 Teste de Conexão - Almoxarifado")

with st.spinner("Conectando ao banco de dados..."):
    df = load_data()

if not df.empty:
    st.success("Conexão bem-sucedida! Dados carregados:")
    st.dataframe(df)
else:
    st.warning("Nenhum dado encontrado ou tabela vazia.")
