import streamlit as st

st.title("Teste de Ícone Simples")

# 1. Inicializa a cor se ainda não existir
if 'cor_atual' not in st.session_state:
    st.session_state.cor_atual = "gray"

# 2. Função que altera a cor ANTES de redesenhar a tela
def alternar_cor():
    if st.session_state.cor_atual == "gray":
        st.session_state.cor_atual = "#FF7A00"
    else:
        st.session_state.cor_atual = "gray"

# 3. Botão com evento on_click
st.button("Mudar Cor", on_click=alternar_cor)

# 4. Exibe o ícone com a cor já atualizada
st.markdown(
    f'<p style="font-size: 100px; color: {st.session_state.cor_atual};">📦</p>', 
    unsafe_allow_html=True
)
