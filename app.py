import streamlit as st

st.title("Teste de Ícone Simples")

if 'cor_atual' not in st.session_state:
    st.session_state.cor_atual = "gray"

st.markdown(
    f'<p style="font-size: 100px; color: {st.session_state.cor_atual};">📦</p>', 
    unsafe_allow_html=True
)

if st.button("Mudar Cor"):
    if st.session_state.cor_atual == "gray":
        st.session_state.cor_atual = "#FF7A00"
    else:
        st.session_state.cor_atual = "gray"
