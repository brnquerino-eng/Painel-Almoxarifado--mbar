import streamlit as st

# 1. Configuração da aba do navegador
st.set_page_config(
    page_title="Almoxarifado | Âmbar",
    page_icon="⚡",
    layout="centered"
)

# 2. Títulos e identificação
st.title("📦 Painel de Almoxarifado")
st.subheader("Âmbar Energia")
st.divider() # Linha sutil para separar o cabeçalho do conteúdo

# 3. Nosso primeiro card
st.metric(label="Total de Itens no Estoque", value="347")
