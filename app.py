import streamlit as st

# 1. Configuração básica da página
st.set_page_config(
    page_title="Visão Executiva de Estoque",
    page_icon="📦",
    layout="wide"
)

# 2. Estilização CSS para ficar idêntico ao Blitz (Fundo escuro, linha laranja, cartão)
st.markdown("""
    <style>
        /* Fundo geral da tela */
        .stApp {
            background-color: #11151c; 
        }
        
        /* Cabeçalho superior com a linha laranja */
        .header-container {
            display: flex;
            align-items: center;
            padding-bottom: 15px;
            border-bottom: 2px solid #ff7a00;
            margin-bottom: 30px;
            margin-top: -40px;
        }
        
        /* Caixinha branca do Logo Âmbar */
        .logo-box {
            background-color: white;
            padding: 10px 20px;
            border-radius: 6px;
            margin-right: 25px;
            text-align: center;
            font-family: sans-serif;
            min-width: 120px;
        }
        .logo-ambar {
            color: #001f3f;
            font-size: 22px;
            font-weight: 900;
            margin: 0;
            line-height: 1.1;
        }
        .logo-energia {
            color: #ff7a00;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            margin: 0;
        }
        
        /* Título e Subtítulo */
        .title-box {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .main-title {
            color: #ffffff;
            font-size: 22px;
            font-weight: 800;
            margin: 0;
            letter-spacing: 0.5px;
        }
        .sub-title {
            color: #8b949e;
            font-size: 14px;
            margin: 0;
            margin-top: 2px;
        }
        
        /* Cartão de Métrica Escuro */
        .metric-card {
            background-color: #1a1f26; 
            border: 1px solid #2d3748;
            border-radius: 8px;
            padding: 20px 25px;
            width: 420px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .metric-title {
            color: #8b949e;
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
            text-transform: uppercase;
        }
        .metric-value {
            color: #ffffff;
            font-size: 28px;
            font-weight: bold;
            margin: 0;
            font-family: monospace;
        }
    </style>
""", unsafe_allow_html=True)

# 3. Desenhando o Cabeçalho na tela
st.markdown("""
    <div class="header-container">
        <div class="logo-box">
            <p class="logo-ambar">Âmbar</p>
            <p class="logo-energia">ENERGIA</p>
        </div>
        <div class="title-box">
            <p class="main-title">VISÃO EXECUTIVA DE ESTOQUE</p>
            <p class="sub-title">Valores Consolidados</p>
        </div>
    </div>
""", unsafe_allow_html=True)

# 4. Desenhando o Cartão de Valor Total em Estoque
st.markdown("""
    <div class="metric-card">
        <div class="metric-title">
            <span>📦</span> VALOR TOTAL EM ESTOQUE
        </div>
        <p class="metric-value">R$ 0,00</p>
    </div>
""", unsafe_allow_html=True)
