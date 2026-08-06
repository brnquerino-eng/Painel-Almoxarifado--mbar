import pandas as pd
import streamlit as st
from supabase import create_client

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# Inicialização dos estados para os filtros
if 'f_unidade' not in st.session_state:
    st.session_state.f_unidade = "Todas"
if 'f_mes' not in st.session_state:
    st.session_state.f_mes = "Todos"
if 'f_ano' not in st.session_state:
    st.session_state.f_ano = "Todos"

# 1. Conexão direta e segura com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Performance com Paginação: Busca em blocos de 1000 para contornar o limite do Supabase
@st.cache_data(ttl=300)
def carregar_dados():
    try:
        all_data = []
        batch_size = 1000
        start = 0
        
        with st.spinner("Carregando base de dados completa do Supabase..."):
            while True:
                response = supabase.table(table_name).select(
                    "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno, unidade_almoxarifado, mes_referencia, ano_referencia"
                ).range(start, start + batch_size - 1).execute()
                
                if not response.data:
                    break
                    
                all_data.extend(response.data)
                
                if len(response.data) < batch_size:
                    break
                    
                start += batch_size
                
        return pd.DataFrame(all_data) if all_data else pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return pd.DataFrame()

df_completo = carregar_dados()

# Opções dinâmicas para os selects baseadas na base completa
unidades_opcoes = ["Todas"] + sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else ["Todas"]
mes_opcoes = ["Todos"] + sorted(df_completo["mes_referencia"].dropna().unique().tolist()) if not df_completo.empty else ["Todos"]
ano_opcoes = ["Todos"] + sorted(df_completo["ano_referencia"].dropna().unique().tolist()) if not df_completo.empty else ["Todos"]

# 3. Definição da Modal (Tela a parte para os Filtros)
@st.dialog("Filtros de Análise - Visão Executiva", width="large")
def modal_filtros():
    st.markdown("<p style='color: #8c9ba5; font-size: 13px; margin-bottom: 20px;'>Selecione os parâmetros desejados para refinar a consolidação dos dados:</p>", unsafe_allow_html=True)
    
    idx_unidade = unidades_opcoes.index(st.session_state.f_unidade) if st.session_state.f_unidade in unidades_opcoes else 0
    idx_mes = mes_opcoes.index(st.session_state.f_mes) if st.session_state.f_mes in mes_opcoes else 0
    idx_ano = ano_opcoes.index(st.session_state.f_ano) if st.session_state.f_ano in ano_opcoes else 0

    f_unidade_sel = st.selectbox("Unidade de Almoxarifado:", unidades_opcoes, index=idx_unidade)
    f_mes_sel = st.selectbox("Mês de Referência:", mes_opcoes, index=idx_mes)
    f_ano_sel = st.selectbox("Ano de Referência:", ano_opcoes, index=idx_ano)
    
    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("Limpar Filtros", use_container_width=True):
            st.session_state.f_unidade = "Todas"
            st.session_state.f_mes = "Todos"
            st.session_state.f_ano = "Todos"
            st.rerun()
    with col_btn2:
        if st.button("Aplicar Filtros", use_container_width=True, type="primary"):
            st.session_state.f_unidade = f_unidade_sel
            st.session_state.f_mes = f_mes_sel
            st.session_state.f_ano = f_ano_sel
            st.rerun()

# 4. Estilização CSS (Design idêntico ao painel executivo original)
st.markdown("""
<style>
    .stApp {
        background-color: #0f141c;
    }
    .stButton > button {
        background-color: #1a222d !important;
        color: #ffffff !important;
        border: 1px solid #333d4d !important;
        border-radius: 6px !important;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        border-color: #d85c27 !important;
        color: #d85c27 !important;
    }
    .header-container {
        display: flex;
        align-items: center;
        border-bottom: 2px solid #d85c27;
        padding-bottom: 12px;
        margin-bottom: 20px;
        gap: 20px;
    }
    .logo-container {
        background-color: #ffffff;
        padding: 6px 16px;
        border-radius: 4px;
        text-align: center;
        font-family: Arial, sans-serif;
    }
    .logo-main {
        color: #12161f;
        font-weight: 900;
        font-size: 18px;
        line-height: 1;
    }
    .logo-sub {
        color: #d85c27;
        font-size: 9px;
        font-weight: bold;
        letter-spacing: 1px;
    }
    .title-container {
        border-left: 1px solid #333d4d;
        padding-left: 15px;
    }
    .title-main {
        color: #ffffff;
        font-size: 18px;
        font-weight: bold;
        letter-spacing: 1px;
        margin: 0;
    }
    .title-sub {
        color: #8c9ba5;
        font-size: 12px;
        margin: 0;
    }
    .card-box {
        background-color: #161c24;
        border: 1px solid #232b36;
        border-radius: 8px;
        padding: 20px;
        height: 120px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .card-header {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .icon-box {
        width: 32px;
        height: 32px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
    }
    .icon-estoque { background-color: #132a24; color: #2ecc71; }
    .icon-compras { background-color: #2a2211; color: #f39c12; }
    .icon-consumo { background-color: #2a1515; color: #e74c3c; }
    .card-title {
        color: #8c9ba5;
        font-size: 12px;
        font-weight: bold;
        letter-spacing: 0.5px;
    }
    .card-value {
        color: #ffffff;
        font-size: 26px;
        font-weight: bold;
        text-align: center;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# 5. Renderização do Cabeçalho com o Botão de Filtro
col_header, col_btn = st.columns([5, 1])

with col_header:
    st.markdown(f"""
    <div class="header-container">
        <div class="logo-container">
            <div class="logo-main">Âmbar</div>
            <div class="logo-sub">ENERGIA</div>
        </div>
        <div class="title-container">
            <div class="title-main">VISÃO EXECUTIVA DE ESTOQUE</div>
            <div class="title-sub">Valores Consolidados</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    filtro_ativo = (st.session_state.f_unidade != "Todas") or (st.session_state.f_mes != "Todos") or (st.session_state.f_ano != "Todos")
    label_botao = "⚙️ Filtros (Ativo)" if filtro_ativo else "⚙️ Filtros"
    
    if st.button(label_botao, use_container_width=True):
        modal_filtros()

# 6. Filtragem do DataFrame com base nos estados salvos
df_filtrado = df_completo.copy()

if st.session_state.f_unidade != "Todas":
    df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"] == st.session_state.f_unidade]
if st.session_state.f_mes != "Todos":
    df_filtrado = df_filtrado[df_filtrado["mes_referencia"] == st.session_state.f_mes]
if st.session_state.f_ano != "Todos":
    df_filtrado = df_filtrado[df_filtrado["ano_referencia"] == st.session_state.f_ano]

# 7. Somas Dinâmicas
def somar_coluna(dataframe, coluna):
    if coluna not in dataframe.columns or dataframe.empty:
        return 0.0
    return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

val_estoque = somar_coluna(df_filtrado, "valor_saldo_atual")
val_compras = somar_coluna(df_filtrado, "valor_entrada_compras")
val_consumo = somar_coluna(df_filtrado, "valor_saida_cons_interno")

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# 8. Cards Executivos
c1, c2 = st.columns(2)

with c1:
    st.markdown(f"""
    <div class="card-box">
        <div class="card-header">
            <div class="icon-box icon-estoque">📦</div>
            <div class="card-title">VALOR TOTAL EM ESTOQUE</div>
        </div>
        <div class="card-value">{fmt_brl(val_estoque)}</div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="card-box">
        <div class="card-header">
            <div class="icon-box icon-compras">🛒</div>
            <div class="card-title">VALOR TOTAL DE COMPRA</div>
        </div>
        <div class="card-value">{fmt_brl(val_compras)}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

c3, _ = st.columns(2)

with c3:
    st.markdown(f"""
    <div class="card-box">
        <div class="card-header">
            <div class="icon-box icon-consumo">📉</div>
            <div class="card-title">VALOR TOTAL DE CONSUMO</div>
        </div>
        <div class="card-value">{fmt_brl(val_consumo)}</div>
    </div>
    """, unsafe_allow_html=True)
