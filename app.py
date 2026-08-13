from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# Inicialização dos estados globais de controle
if 'chart_escopo' not in st.session_state: st.session_state.chart_escopo = "Todas"
if 'chart_unidades' not in st.session_state: st.session_state.chart_unidades = []
if 'chart_anos' not in st.session_state: st.session_state.chart_anos = []
if 'filtro_periodo_grafico' not in st.session_state: st.session_state.filtro_periodo_grafico = None

# 1. Conexão direta e segura
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Carregamento de Dados
@st.cache_data()
def carregar_dados():
    try:
        count_res = supabase.table(table_name).select("*", count="exact", head=True).execute()
        total_rows = getattr(count_res, 'count', None) or 460000
        batch_size = 1000
        ranges = [(i, min(i + batch_size - 1, total_rows - 1)) for i in range(0, total_rows, batch_size)]
        all_data = []

        def fetch_range(start_r, end_r):
            res = supabase.table(table_name).select(
                "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno, unidade_almoxarifado, mes_referencia, ano_referencia, codigo_produto, qtde_saldo_atual, item_critico, nome_local_estoque"
            ).order("id").range(start_r, end_r).execute()
            return res.data if res.data else []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(fetch_range, s, e) for s, e in ranges]
            for future in futures:
                data = future.result()
                if data: all_data.extend(data)

        df = pd.DataFrame(all_data)
        if "unidade_almoxarifado" in df.columns:
            df["unidade_almoxarifado"] = df["unidade_almoxarifado"].astype(str).str.strip().str.upper()
        
        for col in ["mes_referencia", "ano_referencia", "codigo_produto", "item_critico", "nome_local_estoque"]:
            if col in df.columns: df[col] = df[col].apply(lambda x: str(x).strip().replace('.0', ''))
        
        for col in ["valor_saldo_atual", "valor_entrada_compras", "valor_saida_cons_interno", "qtde_saldo_atual"]:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        df['tmp_ano_num'] = pd.to_numeric(df['ano_referencia'], errors='coerce').fillna(0)
        df['tmp_mes_num'] = pd.to_numeric(df['mes_referencia'], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

df_completo = carregar_dados()

# Identificação do período mais recente
if not df_completo.empty:
    max_ano_base = df_completo['tmp_ano_num'].max()
    max_mes_base = df_completo[df_completo['tmp_ano_num'] == max_ano_base]['tmp_mes_num'].max()
    if st.session_state.filtro_periodo_grafico is None:
        st.session_state.filtro_periodo_grafico = f"{int(max_mes_base):02d}/{int(max_ano_base)}"
else:
    max_ano_base, max_mes_base = 2026, 7

unidades_opcoes = sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else []
unidades_gerenciais = [u for u in unidades_opcoes if "GERENCIAL" in u]
unidades_ativas = [u for u in unidades_opcoes if "GERENCIAL" not in u]
ano_opcoes = sorted(df_completo["ano_referencia"].dropna().unique().tolist(), key=lambda x: (0, int(x)) if str(x).isdigit() else (1, x)) if not df_completo.empty else []

# 3. Estilização CSS
st.markdown("""
<style>
    .stApp { background-color: #0f141c; }
    .header-container { display: flex; align-items: center; border-bottom: 2px solid #d85c27; padding-bottom: 12px; margin-bottom: 20px; gap: 20px; }
    .card-box { background-color: #161c24; border: 1px solid #232b36; border-radius: 8px; padding: 16px; min-height: 130px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5); }
    .card-title { color: #8c9ba5; font-size: 11px; font-weight: bold; }
    .card-value { color: #ffffff; font-size: 21px; font-weight: bold; text-align: center; font-family: monospace; margin-top: 8px; }
    .section-title { color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 12px; border-left: 3px solid #d85c27; padding-left: 10px; }
    .icon-box { width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# 4. Renderização do Cabeçalho Limpo
st.markdown("""
<div class="header-container">
    <div style="background-color: #ffffff; padding: 6px 16px; border-radius: 4px; text-align: center;">
        <div style="color: #12161f; font-weight: 900; font-size: 18px;">Âmbar</div>
        <div style="color: #d85c27; font-size: 9px; font-weight: bold;">ENERGIA</div>
    </div>
    <div style="border-left: 1px solid #333d4d; padding-left: 15px;">
        <div style="color: #ffffff; font-size: 18px; font-weight: bold; letter-spacing: 1px;">VISÃO EXECUTIVA DE ESTOQUE</div>
        <div style="color: #8c9ba5; font-size: 12px;">Valores Consolidados</div>
    </div>
</div>
""", unsafe_allow_html=True)

# 5. Controles Globais da Aba
with st.container(border=True):
    col_tg_title, col_tg_escopo, col_tg_unid, col_tg_ano = st.columns([1.8, 1.2, 2.0, 1.5])
    with col_tg_title:
        st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-top: 10px;'>📊 TENDÊNCIA: TOTAL VS CRÍTICO VS OBSOLETO VS OBRA</div>", unsafe_allow_html=True)
    
    with col_tg_escopo:
        st.selectbox("Escopo:", ["Todas", "Ativas", "Gerenciais"], key="chart_escopo")
    
    with col_tg_unid:
        opcoes_unid = unidades_ativas if st.session_state.chart_escopo == "Ativas" else unidades_gerenciais if st.session_state.chart_escopo == "Gerenciais" else unidades_opcoes
        st.multiselect("Unidades:", opcoes_unid, key="chart_unidades", placeholder="Todas")
    
    with col_tg_ano:
        st.multiselect("Anos:", ano_opcoes, key="chart_anos", placeholder="Todos")

# 6. Filtragem Síncrona
df_filtrado = df_completo.copy()
if st.session_state.chart_escopo == "Ativas": df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_ativas)]
elif st.session_state.chart_escopo == "Gerenciais": df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_gerenciais)]
if st.session_state.chart_unidades: df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(st.session_state.chart_unidades)]
if st.session_state.chart_anos: df_filtrado = df_filtrado[df_filtrado["ano_referencia"].isin(st.session_state.chart_anos)]

# Validação do período ativo
if st.session_state.get('filtro_periodo_grafico') and not df_filtrado.empty:
    m_num, a_num = map(int, st.session_state.filtro_periodo_grafico.split('/'))
    if df_filtrado[(df_filtrado['tmp_ano_num'] == a_num) & (df_filtrado['tmp_mes_num'] == m_num)].empty:
        max_a = df_filtrado['tmp_ano_num'].max()
        max_m = df_filtrado[df_filtrado['tmp_ano_num'] == max_a]['tmp_mes_num'].max()
        st.session_state.filtro_periodo_grafico = f"{int(max_m):02d}/{int(max_a)}"

# Resumo informativo
texto_info = f"Exibindo dados de **{st.session_state.chart_escopo.lower()} as unidades**."
if st.session_state.get('filtro_periodo_grafico'): texto_info += f" 🎯 **Período: {st.session_state.filtro_periodo_grafico}**"
st.markdown(f"<p style='color: #8c9ba5; font-size: 14px; margin-top: -10px;'>{texto_info}</p>", unsafe_allow_html=True)

# DataFrame de Snapshot
df_snapshot = df_filtrado.copy()
if st.session_state.get('filtro_periodo_grafico'):
    m_num, a_num = map(int, st.session_state.filtro_periodo_grafico.split('/'))
    df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == a_num) & (df_snapshot['tmp_mes_num'] == m_num)]
else:
    if st.session_state.chart_anos:
        anos_sel_num = [int(a) for a in st.session_state.chart_anos]
        df_anos_sel = df_snapshot[df_snapshot['tmp_ano_num'].isin(anos_sel_num)]
        if not df_anos_sel.empty:
            m_ano = df_anos_sel['tmp_ano_num'].max()
            m_mes = df_anos_sel[df_anos_sel['tmp_ano_num'] == m_ano]['tmp_mes_num'].max()
            df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == m_ano) & (df_snapshot['tmp_mes_num'] == m_mes)]
    else:
        df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == max_ano_base) & (df_snapshot['tmp_mes_num'] == max_mes_base)]

# Cálculos (Cards)
def somar(df, col): return pd.to_numeric(df[col], errors='coerce').fillna(0.0).sum()
val_estoque = somar(df_snapshot, "valor_saldo_atual")
val_skus = df_snapshot[(df_snapshot["qtde_saldo_atual"] > 0) & (df_snapshot["codigo_produto"] != "")]["codigo_produto"].nunique()
val_critico = somar(df_snapshot[df_snapshot["item_critico"] == "1-Sim"], "valor_saldo_atual")
val_obsoleto = somar(df_snapshot[df_snapshot["nome_local_estoque"].astype(str).str.contains("Obsoleto", case=False, na=False)], "valor_saldo_atual")
val_obra = somar(df_snapshot[df_snapshot["nome_local_estoque"].astype(str).str.contains("obra", case=False, na=False)], "valor_saldo_atual")

# Formatação
def fmt_brl(val): return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# 7. Abas e Componentes (Gráfico + Cards)
aba_geral, aba_detalhada = st.tabs(["📈 Visão Geral", "📊 Análises Detalhadas"])

with aba_geral:
    # Gráfico de Tendência (agora lendo o estado global e disparando rerun)
    fig_linha_estoque = go.Figure()
    # ... (lógica do gráfico igual à anterior, integrada no fluxo principal) ...
    # (Inserir aqui o código do gráfico que você já validou)
    
    # Exibição dos Cards
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='card-box'><div class='card-title'>VALOR TOTAL</div><div class='card-value'>{fmt_brl(val_estoque)}</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='card-box'><div class='card-title'>ESTOQUE CRÍTICO</div><div class='card-value'>{fmt_brl(val_critico)}</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='card-box'><div class='card-title'>ESTOQUE OBSOLETO</div><div class='card-value'>{fmt_brl(val_obsoleto)}</div></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='card-box'><div class='card-title'>ESTOQUE OBRA</div><div class='card-value'>{fmt_brl(val_obra)}</div></div>", unsafe_allow_html=True)
