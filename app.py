import streamlit as st
from supabase import create_client

st.title("🧪 Teste de Conexão - Supabase")

# 1. Verifica se as chaves dos Segredos estão acessíveis
try:
  url = st.secrets["SUPABASE_URL"]
  key = st.secrets["SUPABASE_KEY"]
  st.success("✅ As chaves do Supabase foram encontradas nos Segredos!")

  # 2. Inicializa o cliente do Supabase
  supabase = create_client(url, key)

  # 3. Botão para testar a busca de dados na tabela principal do almoxarifado
  if st.button("🔍 Testar Leitura da Base de Dados"):
    with st.spinner("Conectando ao Supabase..."):
      # Consulta os primeiros registros da tabela de estoque
      response = (
          supabase.table("painel_estoque").select("*").limit(5).execute()
      )

      if response.data:
        st.success(
            "🎉 Conexão bem-sucedida! Dados recuperados do banco com sucesso:"
        )
        st.dataframe(response.data)
      else:
        st.warning(
            "A conexão funcionou, mas a tabela retornou vazia ou não possui"
            " registros."
        )

except Exception as e:
  st.error(f"❌ Erro na configuração ou conexão: {e}")
