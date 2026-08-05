import streamlit as st

# 1. Configuração da página (agora em modo 'wide' para caber o painel)
st.set_page_config(
    page_title="Visão Executiva | Âmbar",
    page_icon="⚡",
    layout="wide"
)

# 2. CSS Customizado (Apenas para o visual dos cards e da linha)
st.markdown("""
<style>
    /* Linha laranja da Âmbar */
    .orange-divider {
        border-top: 2px solid #FF7A00;
        margin-top: 5px;
        margin-bottom: 25px;
    }
    
    /* Estilo dos Cards */
    .dash-card {
        background-color: #1A1F26; /* Fundo escuro do card */
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid #2D333B;
    }
    
    .card-header {
        display: flex;
        align-items: center;
        gap: 15px;
        margin-bottom: 15px;
    }
    
    .icon-box {
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 18px;
    }
    
    /* Cores dos ícones */
    .icon-green { background-color: rgba(0, 255, 127, 0.1); color: #48C774; }
    .icon-orange { background-color: rgba(255, 122, 0, 0.1); color: #FF7A00; }
    .icon-red { background-color: rgba(255, 99, 71, 0.1); color: #FF6347; }
    
    .card-title {
        color: #A0AEC0;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 1px;
    }
    
    .card-value {
        color: white;
        font-size: 32px;
        font-weight: bold;
        text-align: center;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# 3. CABEÇALHO (Logo, Títulos e Botões)
col_logo, col_titulo, col_espaco, col_filtros, col_atualizar = st.columns([1, 4, 2, 1, 1])

with col_logo:
    # Simulando o logo branco em HTML para não precisar de arquivo de imagem agora
    st.markdown("""
    <div style="background-color: white; padding: 10px; border-radius: 6px; text-align: center; height: 100%;">
        <strong style="color: #002B49; font-size: 22px; line-height: 1;">Âmbar</strong><br>
        <span style="color: #FF7A00; font-size: 11px; font-weight: bold; letter-spacing: 1px;">ENERGIA</span>
    </div>
    """, unsafe_allow_html=True)

with col_titulo:
    st.markdown("<h3 style='margin:0; padding-top:5px; color: white;'>VISÃO EXECUTIVA DE ESTOQUE</h3>", unsafe_allow_html=True)
    st.markdown("<span style='color: #A0AEC0; font-size: 14px;'>Valores Consolidados</span>", unsafe_allow_html=True)

with col_filtros:
    st.button("⚙️ Filtros", use_container_width=True)

with col_atualizar:
    st.button("🔄 Atualizar", use_container_width=True)

# 4. LINHA SEPARADORA
st.markdown("<div class='orange-divider'></div>", unsafe_allow_html=True)

# 5. CARDS DE MÉTRICAS (Usando as classes CSS que criamos acima)
col_esq, col_dir = st.columns(2)

with col_esq:
    st.markdown("""
    <div class="dash-card">
        <div class="card-header">
            <div class="icon-box icon-green">📦</div>
            <div class="card-title">VALOR TOTAL EM ESTOQUE</div>
        </div>
        <div class="card-value">R$ 0,00</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="dash-card">
        <div class="card-header">
            <div class="icon-box icon-red">📉</div>
            <div class="card-title">VALOR TOTAL DE CONSUMO</div>
        </div>
        <div class="card-value">R$ 0,00</div>
    </div>
    """, unsafe_allow_html=True)

with col_dir:
    st.markdown("""
    <div class="dash-card">
        <div class="card-header">
            <div class="icon-box icon-orange">🛒</div>
            <div class="card-title">VALOR TOTAL DE COMPRA</div>
        </div>
        <div class="card-value">R$ 0,00</div>
    </div>
    """, unsafe_allow_html=True)
