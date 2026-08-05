import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Configuração inicial da página
st.set_page_config(
    page_title="Painel de Almoxarifado - Âmbar Energia",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS para deixar o painel com cara de sistema executivo
st.markdown("""
    <style>
        .main { background-color: #0e1117; }
        .stMetric {
            background-color: #161b22;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #30363d;
        }
    </style>
""", unsafe_allow_html=True)

# Inicializa conexão com Supabase usando as chaves seguras (Secrets)
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("⚠️ Erro ao acessar as credenciais. Verifique se os Secrets estão configurados corretamente no Streamlit Cloud.")
        return None

supabase: Client = init_supabase()

# Função para buscar os dados no banco
@st.cache_data(ttl=300) # Atualiza o cache a cada 5 minutos
def load_data():
    if not supabase:
        return pd.DataFrame()
    try:
        # ATENÇÃO: Confirme se o nome da sua tabela no banco Supabase é 'painel_estoque'
        response = supabase.table("painel_estoque").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"⚠️ Erro ao carregar os dados: {e}")
        return pd.DataFrame()

# Título do Painel
st.title("📦 Painel de Almoxarifado - Âmbar Energia")
st.markdown("Gestão integrada e inteligência de inventário.")

with st.spinner("Carregando base de dados do inventário..."):
    df = load_data()

if df.empty:
    st.warning("⚠️ Nenhum dado encontrado. Verifique se a tabela no Supabase tem registros ou se o nome da tabela está correto no código.")
else:
    # Tratamento das colunas numéricas (Quantidades e Valores)
    colunas_numericas = ['qtde', 'preco_medio', 'valor']
    for col in colunas_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    # Configurando a Barra Lateral (Sidebar)
    st.sidebar.header("🔍 Filtros de Consulta")

    # Identificação dinâmica das colunas (evita erros se os nomes mudarem no banco)
    unidade_col = next((col for col in ['unidade_almoxarifado', 'unidade', 'localizacao'] if col in df.columns), None)
    familia_col = next((col for col in ['familia', 'categoria', 'aplicacao'] if col in df.columns), None)
    codigo_col = next((col for col in ['codigo_produto', 'codigo'] if col in df.columns), None)

    # Filtro de Unidades
    unidade_selecionada = "Todas"
    if unidade_col:
        lista_unidades = ["Todas"] + sorted(df[unidade_col].dropna().astype(str).unique().tolist())
        unidade_selecionada = st.sidebar.selectbox("Unidade", lista_unidades)

    # Filtro de Família/Categoria
    familia_selecionada = "Todas"
    if familia_col:
        lista_familias = ["Todas"] + sorted(df[familia_col].dropna().astype(str).unique().tolist())
        familia_selecionada = st.sidebar.selectbox("Família / Categoria", lista_familias)

    # Busca livre
    busca_livre = st.sidebar.text_input("Buscar por Código ou Nome do item", "")

    # Aplicando os filtros no conjunto de dados
    df_filtrado = df.copy()
    
    if unidade_selecionada != "Todas" and unidade_col:
        df_filtrado = df_filtrado[df_filtrado[unidade_col].astype(str) == unidade_selecionada]
    
    if familia_selecionada != "Todas" and familia_col:
        df_filtrado = df_filtrado[df_filtrado[familia_col].astype(str) == familia_selecionada]

    if busca_livre:
        busca_lower = busca_livre.lower()
        mask = pd.Series([False] * len(df_filtrado), index=df_filtrado.index)
        for col in df_filtrado.columns:
            mask = mask | df_filtrado[col].astype(str).str.lower().str.contains(busca_lower, na=False)
        df_filtrado = df_filtrado[mask]

    # Calculando e exibindo os KPIs
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    total_registros = len(df_filtrado)
    total_skus = df_filtrado[codigo_col].nunique() if codigo_col else total_registros
    qtde_total = df_filtrado['qtde'].sum() if 'qtde' in df_filtrado.columns else 0.0
    valor_total = df_filtrado['valor'].sum() if 'valor' in df_filtrado.columns else 0.0

    # Função charmosa para formatar os números para o nosso padrão BRL
    def formata_brl(valor):
        return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    col1.metric("Registros Filtrados", formata_brl(total_registros).split(',')[0]) 
    col2.metric("Total de SKUs", formata_brl(total_skus).split(',')[0])
    col3.metric("Quantidade Total", formata_brl(qtde_total))
    col4.metric("Valor Total (R$)", f"R$ {formata_brl(valor_total)}")
    
    st.markdown("---")

    # Separando a visualização em abas organizadas
    aba1, aba2 = st.tabs(["📋 Tabela de Inventário", "📊 Análise Gráfica"])

    with aba1:
        st.dataframe(df_filtrado, use_container_width=True, height=500)
        
        # Botão de Exportação CSV
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar dados da consulta (.CSV)",
            data=csv,
            file_name="estoque_ambar_energia.csv",
            mime="text/csv"
        )

    with aba2:
        st.subheader("Top 10: Valor Total por Categoria/Família")
        if familia_col and 'valor' in df_filtrado.columns:
            # Agrupando os maiores valores para o gráfico
            df_grafico = df_filtrado.groupby(familia_col)['valor'].sum().reset_index()
            df_grafico = df_grafico.sort_values(by='valor', ascending=False).head(10)
            
            # Gráfico de barras simples e eficiente
            st.bar_chart(df_grafico.set_index(familia_col)['valor'])
        else:
            st.info("As colunas de família ou valor não foram identificadas na base para gerar o gráfico.")
