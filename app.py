import streamlit as st

st.title("Teste de Ícone Simples")

# 1. Inicializa a cor se ela ainda não existir no "sistema"
if 'cor_atual' not in st.session_state:
    st.session_state.cor_atual = "gray" # Começa cinza

# 2. Mostra o ícone usando HTML para definir a cor
# Estamos usando um f-string para colocar a cor_atual direto no style
st.markdown(
    f'<p style="font-size: 100px; color: {st.session_state.cor_atual};">📦</p>', 
    unsafe_allow_html=True
)

# 3. Cria o botão
if st.button("Mudar Cor"):
    # Se estiver cinza, muda para laranja. Se não, volta para cinza.
    if st.session_state.cor_atual == "gray":
        st.session_state.cor_atual = "#FF7A00" # Laranja Âmbar
    else:
        st.session_state.cor_atual = "gray"
        
    # Recarrega a tela imediatamente para mostrar a nova cor
    st.rerun()
