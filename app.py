import pandas as pd
import streamlit as st
from supabase import create_client

# Configuração da página
st.set_page_config(
    page_title="Painel de Almoxarifado - Âmbar", page_icon="📦", layout="wide"
)

# Título do Painel
st.title("📦 Painel de Almoxarifado - Gestão de Unidades")
st.markdown(
    "Painel executivo para monitoramento de estoque das unidades de"
    " almoxarifado."
)

# Configuração de Conexão com o Supabase
try:
  SUPABASE_URL = st.secrets["SUPABASE_URL"]
  SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
  supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
  supabase = None


# Função para carregar os dados do Supabase
@st.cache_data(ttl=600)
def carregar_dados():
  if supabase is not None:
    try:
      response = supabase.table("estoque").select("*").execute()
      return pd.DataFrame(response.data)
    except Exception as e:
      st.error(f"Erro ao carregar dados do Supabase: {e}")
      return pd.DataFrame()
  else:
    # Dados de demonstração caso o Supabase não esteja conectado ainda
    return pd.DataFrame({
        "Unidade": ["Unidade 01", "Unidade 02", "Unidade 01", "Unidade 03"],
        "Item": ["Cabo Flexível", "Disjuntor 40A", "Luva de PVC", "Conector"],
        "Categoria": ["Elétrica", "Elétrica", "Hidráulica", "Elétrica"],
        "Quantidade": [150, 45, 300, 120],
        "Valor_Unitario": [12.50, 45.00, 8.20, 15.00],
    })


df = carregar_dados()

if not df.empty:
  # Sidebar para Filtros
  st.sidebar.header("Filtros")

  if "Unidade" in df.columns:
    unidades_disponiveis = ["Todas"] + list(df["Unidade"].unique())
    unidade_selecionada = st.sidebar.selectbox(
        "Selecione a Unidade", unidades_disponiveis
    )
    if unidade_selecionada != "Todas":
      df = df[df["Unidade"] == unidade_selecionada]

  if "Categoria" in df.columns:
    categorias_disponiveis = ["Todas"] + list(df["Categoria"].unique())
    categoria_selecionada = st.sidebar.selectbox(
        "Selecione a Categoria", categorias_disponiveis
    )
    if categoria_selecionada != "Todas":
      df = df[df["Categoria"] == categoria_selecionada]

  # Métricas / KPIs
  st.markdown("---")
  col1, col2, col3 = st.columns(3)

  total_itens = len(df)
  quantidade_total = (
      df["Quantidade"].sum() if "Quantidade" in df.columns else 0
  )
  if "Quantidade" in df.columns and "Valor_Unitario" in df.columns:
    valor_total = (df["Quantidade"] * df["Valor_Unitario"]).sum()
  else:
    valor_total = 0

  col1.metric("Total de Registros", f"{total_itens:,}")
  col2.metric("Quantidade Total em Estoque", f"{quantidade_total:,.0f}")
  col3.metric("Valor Total Estimado", f"R$ {valor_total:,.2f}")

  st.markdown("---")

  # Tabela Detalhada
  st.subheader("📋 Detalhamento do Estoque")
  st.dataframe(df, use_container_width=True)

else:
  st.info(
      "Nenhum dado encontrado. Verifique a conexão com a tabela 'estoque' no"
      " Supabase."
  )