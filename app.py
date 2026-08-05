import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Painel de Almoxarifado", layout="wide")

st.title("📦 Painel de Almoxarifado - Âmbar Energia")

SUPABASE_URL = "https://qkeyubnipkysowpaczwf.supabase.co"
SUPABASE_KEY = "sb_publishable_eOqm6_U_dX-bS4Zla0bB6Q_kL5eHG52"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


@st.cache_data(ttl=600)
def carregar_dados_completos():
  response = supabase.table("painel_estoque").select("*").execute()
  return pd.DataFrame(response.data)


with st.spinner("Carregando dados completos do estoque consolidado..."):
  df = carregar_dados_completos()

if not df.empty:
  st.success(
      f"Base carregada com sucesso! Total de registros: {len(df)} linhas."
  )
  st.dataframe(df, use_container_width=True)
else:
  st.warning(
      "A tabela retornou vazia. Verifique se os dados foram enviados para o"
      " Supabase."
  )
