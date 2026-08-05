import streamlit as st

st.title("Teste de Ícone Simples")

if 'cor_atual' not in st.session_state:
    st.session_state.cor_atual = "gray"

def alternar_cor():
    if st.session_state.cor_atual == "gray":
        st.session_state.cor_atual = "orange"
    else:
        st.session_state.cor_atual = "gray"

st.button("Mudar Cor", on_click=alternar_cor)

# Aplica filtro CSS: cinza total (grayscale) ou cor normal da caixa
estilo_filtro = "filter: grayscale(100%) opacity(0.5);" if st.session_state.cor_atual == "gray" else "filter: none;"

st.markdown(
    f'<p style="font-size: 100px; {estilo_filtro}">📦</p>', 
    unsafe_allow_html=True
)
