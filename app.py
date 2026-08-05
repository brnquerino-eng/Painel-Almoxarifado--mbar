import streamlit as st

# 1. Configuração da página
st.set_page_config(
    page_title="Visão Executiva | Âmbar",
    page_icon="⚡",
    layout="wide"
)

# 2. CSS Customizado (Ajustado para fontes corporativas e alinhamento dos ícones)
st.markdown("""
<style>
    /* Linha laranja */
    .orange-divider {
        border-top: 2px solid #FF7A00;
        margin-top: 5px;
        margin-bottom: 25px;
    }
    
    /* Estilo dos Cards */
    .dash-card {
        background-color: #1A1F26;
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
    
    /* Ajuste para centralizar perfeitamente o ícone SVG */
    .icon-box {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 38px;
        height: 38px;
        border-radius: 8px;
    }
    
    /* Cores de fundo e do traço dos ícones */
    .icon-green { background-color: rgba(72, 199, 116, 0.1); color: #48C774; }
    .icon-orange { background-color: rgba(255, 122, 0, 0.1); color: #FF7A00; }
    .icon-red { background-color: rgba(255, 99, 71, 0.1); color: #FF6347; }
    
    .card-title {
        color: #A0AEC0;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    
    /* Fonte mais limpa e executiva para os números */
    .card-value {
        color: white;
        font-size: 34px;
        font-weight: 600;
        text-align: center;
        font-family: 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# 3. CABEÇALHO
col_logo, col_titulo, col_espaco, col_filtros, col_atualizar = st.columns([1, 4, 2, 1, 1])

with col_logo:
    st.markdown("""
    <div style="background-color: white; padding: 10px; border-radius: 6px; text-align: center; height: 100%;">
        <strong style="color: #002B49; font-size: 22px; line-height: 1;">Âmbar</strong><br>
        <span style="color: #FF7A00; font-size: 11px; font-weight: bold; letter-spacing: 1px;">ENERGIA</span>
    </div>
    """, unsafe_allow_html=True)

with col_titulo:
    st.markdown("<h3 style='margin:0; padding-top:5px; color: white; font-family: sans-serif;'>VISÃO EXECUTIVA DE ESTOQUE</h3>", unsafe_allow_html=True)
    st.markdown("<span style='color: #A0AEC0; font-size: 14px;'>Valores Consolidados</span>", unsafe_allow_html=True)

with col_filtros:
    st.button("⚙️ Filtros", use_container_width=True)

with col_atualizar:
    st.button("🔄 Atualizar", use_container_width=True)

# 4. LINHA SEPARADORA
st.markdown("<div class='orange-divider'></div>", unsafe_allow_html=True)

# 5. CARDS DE MÉTRICAS (Agora com Ícones Vetoriais SVG)
col_esq, col_dir = st.columns(2)

with col_esq:
    st.markdown("""
    <div class="dash-card">
        <div class="card-header">
            <div class="icon-box icon-green">
                <!-- Ícone de Cubo (Estoque) -->
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
            </div>
            <div class="card-title">VALOR TOTAL EM ESTOQUE</div>
        </div>
        <div class="card-value">R$ 0,00</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="dash-card">
        <div class="card-header">
            <div class="icon-box icon-red">
                <!-- Ícone de Gráfico de Linha (Consumo) -->
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"></polyline><polyline points="16 17 22 17 22 11"></polyline></svg>
            </div>
            <div class="card-title">VALOR TOTAL DE CONSUMO</div>
        </div>
        <div class="card-value">R$ 0,00</div>
    </div>
    """, unsafe_allow_html=True)

with col_dir:
    st.markdown("""
    <div class="dash-card">
        <div class="card-header">
            <div class="icon-box icon-orange">
                <!-- Ícone de Carrinho (Compras) -->
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
            </div>
            <div class="card-title">VALOR TOTAL DE COMPRA</div>
        </div>
        <div class="card-value">R$ 0,00</div>
    </div>
    """, unsafe_allow_html=True)
