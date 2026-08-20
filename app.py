from concurrent.futures import ThreadPoolExecutor
import time
import io
import pandas as pd
import numpy as np
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

# Inicialização dos estados globais de visibilidade da legenda (Memória Eterna)
if 'vis_total' not in st.session_state:
    st.session_state.vis_total = True
if 'vis_critico' not in st.session_state:
    st.session_state.vis_critico = False
if 'vis_obsoleto' not in st.session_state:
    st.session_state.vis_obsoleto = False
if 'vis_obra' not in st.session_state:
    st.session_state.vis_obra = False

# Inicialização dos estados globais de controle do painel
if 'chart_escopo' not in st.session_state:
    st.session_state.chart_escopo = "Ativa"
if 'chart_unidades' not in st.session_state:
    st.session_state.chart_unidades = []
if 'chart_anos' not in st.session_state:
    st.session_state.chart_anos = []
if 'filtro_periodo_grafico' not in st.session_state:
    st.session_state.filtro_periodo_grafico = None

# Colunas esperadas para blindagem contra falhas de conexão
COLUNAS_ESPERADAS = [
    "valor_saldo_atual", "valor_entrada_compras", "valor_saida_cons_interno",
    "unidade_almoxarifado", "mes_referencia", "ano_referencia",
    "codigo_produto", "nome_produto", "qtde_saldo_atual", "item_critico", "nome_local_estoque",
    "tmp_ano_num", "tmp_mes_num",
]

def _df_vazio_padrao():
    return pd.DataFrame(columns=COLUNAS_ESPERADAS)

# 1. Conexão direta e segura com o Supabase
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# 2. Performance Otimizada e Estável com Retry Progressivo (Aba Geral)
@st.cache_data()
def carregar_dados():
    try:
        with st.spinner("Carregando e normalizando base de dados em alta performance..."):
            count_res = supabase.table(table_name).select("*", count="exact", head=True).execute()
            total_rows = getattr(count_res, 'count', None)

            if not total_rows or total_rows == 0:
                total_rows = 460000

            batch_size = 1000
            ranges = [(i, min(i + batch_size - 1, total_rows - 1)) for i in range(0, total_rows, batch_size)]
            all_data = []

            def fetch_range(start_r, end_r, tentativas=3):
                ultimo_erro = None
                for tentativa in range(1, tentativas + 1):
                    try:
                        res = supabase.table(table_name).select(
                            "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno, unidade_almoxarifado, mes_referencia, ano_referencia, codigo_produto, nome_produto, qtde_saldo_atual, item_critico, nome_local_estoque"
                        ).order("id").range(start_r, end_r).execute()
                        return res.data if res.data else []
                    except Exception as e:
                        ultimo_erro = e
                        if tentativa < tentativas:
                            time.sleep(0.5 * tentativa)
                raise ultimo_erro

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(fetch_range, s, e) for s, e in ranges]
                for future in futures:
                    data = future.result()
                    if data:
                        all_data.extend(data)

            if not all_data:
                return _df_vazio_padrao()

            df = pd.DataFrame(all_data)
            df = df.replace({np.nan: None})

            if "unidade_almoxarifado" in df.columns:
                df["unidade_almoxarifado"] = df["unidade_almoxarifado"].astype(str).str.strip().str.upper()

            def limpar_valor(val):
                if pd.isna(val) or val is None:
                    return ""
                s_val = str(val).strip()
                if s_val.endswith('.0'):
                    s_val = s_val[:-2]
                return s_val

            for col in ["mes_referencia", "ano_referencia", "codigo_produto", "nome_produto", "item_critico", "nome_local_estoque"]:
                if col in df.columns:
                    df[col] = df[col].apply(limpar_valor)

            for col in ["valor_saldo_atual", "valor_entrada_compras", "valor_saida_cons_interno", "qtde_saldo_atual"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            df['tmp_ano_num'] = pd.to_numeric(df['ano_referencia'], errors='coerce').fillna(0)
            df['tmp_mes_num'] = pd.to_numeric(df['mes_referencia'], errors='coerce').fillna(0)

            return df
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return _df_vazio_padrao()

@st.cache_data()
def carregar_dados_inventario():
    try:
        with st.spinner("Carregando base real de inventários..."):
            res = supabase.table("painel_inventario").select("*").execute()
            if not res.data:
                return pd.DataFrame()
            
            df_inv = pd.DataFrame(res.data)
            df_inv = df_inv.replace({np.nan: None})
            
            cols_numericas = [
                "saldo_anterior_val", "inventario_val", "diferenca_val", 
                "saldo_anterior_consolidado", "inventario_consolidado", "diferenca_consolidada",
                "valor_unitario"
            ]
            for col in cols_numericas:
                if col in df_inv.columns:
                    df_inv[col] = pd.to_numeric(df_inv[col], errors='coerce').fillna(0.0)
            
            return df_inv
    except Exception as e:
        st.error(f"Erro ao carregar dados da tabela painel_inventario: {e}")
        return pd.DataFrame()

df_completo = carregar_dados()
df_inventario = carregar_dados_inventario()

# Função unificada e blindada para identificar itens obsoletos (Apenas Nome do Local)
def is_obsoleto_mask(df_in):
    if df_in.empty:
        return pd.Series(False, index=df_in.index)
    col_local = df_in.get("nome_local_estoque", pd.Series("", index=df_in.index))
    return col_local.astype(str).str.contains("Obsoleto", case=False, na=False)

# Identificação segura dos limites globais
if not df_completo.empty:
    max_ano_base = int(df_completo['tmp_ano_num'].max())
    max_mes_base = int(df_completo[df_completo['tmp_ano_num'] == max_ano_base]['tmp_mes_num'].max())
else:
    max_ano_base, max_mes_base = 2026, 1

unidades_opcoes = sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else []
unidades_gerenciais = [u for u in unidades_opcoes if "GERENCIAL" in u]
unidades_ativas = [u for u in unidades_opcoes if "GERENCIAL" not in u]

def _chave_numerica(val):
    try:
        return (0, int(val))
    except (ValueError, TypeError):
        return (1, str(val))

ano_opcoes = sorted(df_completo["ano_referencia"].dropna().unique().tolist(), key=_chave_numerica) if not df_completo.empty else []

# 3. Estilização CSS Avançada
st.markdown("""
<style>
    @keyframes smoothPageLoad {
        0% { opacity: 0.2; transform: scale(0.98); }
        100% { opacity: 1; transform: scale(1); }
    }
    .stApp {
        background-color: #0f141c;
        animation: smoothPageLoad 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #161c24; border-radius: 4px; }
    ::-webkit-scrollbar-thumb { background: #232b36; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #d85c27; }
    div[data-baseweb="select"] { min-height: 28px !important; font-size: 11px !important; }
    div[data-testid="stMultiSelect"] span[data-baseweb="tag"] { font-size: 10px !important; min-height: 18px !important; padding: 0px 4px !important; }
    .stButton > button { background-color: #161c24 !important; color: #8c9ba5 !important; border: 1px solid #232b36 !important; border-radius: 6px !important; font-size: 10px !important; padding: 2px 4px !important; min-height: 24px !important; font-weight: 600 !important; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
    .stButton > button:hover { border-color: #d85c27 !important; color: #ffffff !important; transform: translateY(-1px); }
    .stButton > button[kind="primary"] { background-color: #1a222d !important; border: 1px solid #d85c27 !important; color: #ffffff !important; }
    .header-container { display: flex; align-items: center; border-bottom: 2px solid #d85c27; padding-bottom: 12px; margin-bottom: 20px; gap: 20px; }
    .logo-container { background-color: #ffffff; padding: 6px 16px; border-radius: 4px; text-align: center; font-family: Arial, sans-serif; }
    .logo-main { color: #12161f; font-weight: 900; font-size: 18px; line-height: 1; }
    .logo-sub { color: #d85c27; font-size: 9px; font-weight: bold; letter-spacing: 1px; }
    .title-container { border-left: 1px solid #333d4d; padding-left: 15px; }
    .title-main { color: #ffffff; font-size: 18px; font-weight: bold; letter-spacing: 1px; margin: 0; }
    .title-sub { color: #8c9ba5; font-size: 12px; margin: 0; }
    .card-box { background-color: #161c24; border: 1px solid #232b36; border-radius: 8px; padding: 16px; min-height: 130px; height: auto; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5), 0 4px 8px rgba(0, 0, 0, 0.3); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
    .card-box:hover { transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8), 0 5px 15px rgba(216, 92, 39, 0.15); border-color: #333d4d; }
    div[data-testid="stContainer"] { background-color: #161c24 !important; border: 1px solid #232b36 !important; border-radius: 8px !important; padding: 15px !important; box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8) !important; overflow: visible !important; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
    div[data-testid="stContainer"]:hover { transform: translateY(-4px); box-shadow: 0 20px 35px rgba(0, 0, 0, 0.85), 0 8px 20px rgba(216, 92, 39, 0.2) !important; border-color: #333d4d !important; }
    .card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
    .header-left { display: flex; align-items: center; gap: 8px; }
    .icon-box { width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
    .icon-estoque { background-color: #132a24; color: #2ecc71; }
    .icon-critico { background-color: #2a1515; color: #e74c3c; }
    .icon-obsoleto { background-color: #2a2a2a; color: #9b59b6; }
    .icon-obra { background-color: #1a2a2a; color: #1abc9c; }
    .icon-compras { background-color: #2a2211; color: #f39c12; }
    .icon-consumo { background-color: #2a1515; color: #e74c3c; }
    .icon-skus { background-color: #1a222d; color: #3498db; }
    .icon-giro { background-color: #221a2d; color: #9b59b6; }
    .icon-cobertura { background-color: #2a2211; color: #e67e22; }
    .card-title { color: #8c9ba5; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; line-height: 1.2; }
    .card-value { color: #ffffff; font-size: 21px; font-weight: bold; text-align: center; font-family: monospace; margin-top: 12px; white-space: nowrap; }
    .section-title { color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 12px; letter-spacing: 0.5px; border-left: 3px solid #d85c27; padding-left: 10px; }
    .trend-box { display: flex; align-items: center; padding: 3px 8px; border-radius: 5px; font-size: 11px; font-weight: bold; font-family: monospace; white-space: nowrap; }
    .trend-up { background-color: rgba(231, 76, 60, 0.2); color: #e74c3c; }
    .trend-down { background-color: rgba(46, 204, 113, 0.2); color: #2ecc71; }
    .trend-neutral { background-color: rgba(140, 155, 165, 0.2); color: #8c9ba5; }
</style>
""", unsafe_allow_html=True)

# 4. Renderização do Cabeçalho Limpo
st.markdown(f"""
<div class="header-container">
    <div class="logo-container">
        <div class="logo-main">Âmbar</div>
        <div class="logo-sub">ENERGIA</div>
    </div>
    <div class="title-container">
        <div class="title-main">VISÃO EXECUTIVA DE ESTOQUE</div>
        <div class="title-sub">Valores Consolidados e Gestão de Inventários</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Funções Globais de Formatação
def fmt_brl(val): return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
def fmt_int(val): return f"{val:,}".replace(',', '.')
def fmt_dec(val): return f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "x"
def fmt_mes(val): return f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def render_card(icon, icon_class, title, val_formatado, val_atual, val_ant, font_size="21px", invert_color=False):
    if val_ant == 0 and val_atual == 0:
        pct_str, trend_class, arrow = "0,0%", "trend-neutral", "➖"
    elif val_ant == 0 or val_ant == val_atual: 
        pct_str, trend_class, arrow = "0,0%", "trend-neutral", "➖"
    else:
        pct = ((val_atual - val_ant) / val_ant) * 100
        pct_str = f"{abs(pct):.1f}%".replace('.', ',')
        if pct > 0:
            trend_class = "trend-down" if invert_color else "trend-up"
            arrow = "🔺"
        elif pct < 0:
            trend_class = "trend-up" if invert_color else "trend-down"
            arrow = "🔻"
        else:
            trend_class, arrow = "trend-neutral", "➖"

    return f"""
    <div class="card-box">
        <div class="card-header">
            <div class="header-left">
                <div class="icon-box {icon_class}">{icon}</div>
                <div class="card-title">{title}</div>
            </div>
            <div class="trend-box {trend_class}">{arrow} {pct_str}</div>
        </div>
        <div class="card-value" style="font-size: {font_size};">{val_formatado}</div>
    </div>
    """

# ==========================================
# 5. SISTEMA DE ABAS NATIVO
# ==========================================
aba_geral, aba_inventarios = st.tabs(["📈 Visão Geral", "📦 Painel de Inventários"])

with aba_geral:
    # --- CONTROLES DO GRÁFICO ---
    with st.container(border=True):
        col_tg_title, col_tg_escopo, col_tg_unid, col_tg_ano = st.columns([2.2, 1.2, 2.1, 1.5], gap="small")
        with col_tg_title:
            st.markdown("<div style='color: #ffffff; font-size: 13px; font-weight: bold; margin-top: 18px; border-left: 3px solid #d85c27; padding-left: 8px;'>📊 EVOLUÇÃO TEMPORAL DO ESTOQUE (R$)</div>", unsafe_allow_html=True)

        with col_tg_escopo:
            st.markdown("<div style='font-size: 10px; color: #8c9ba5; margin-bottom: -4px;'>Tipo Unidade:</div>", unsafe_allow_html=True)
            st.selectbox("Tipo Unidade:", ["Todas", "Ativa", "Gerencial"], key="chart_escopo", label_visibility="collapsed")

        with col_tg_unid:
            st.markdown("<div style='font-size: 10px; color: #8c9ba5; margin-bottom: -4px;'>Unidades:</div>", unsafe_allow_html=True)
            if st.session_state.chart_escopo == "Ativa":
                opcoes_unid = unidades_ativas
            elif st.session_state.chart_escopo == "Gerencial":
                opcoes_unid = unidades_gerenciais
            else:
                opcoes_unid = unidades_opcoes
            st.multiselect("Unidades:", opcoes_unid, key="chart_unidades", placeholder="Todas", label_visibility="collapsed")

        with col_tg_ano:
            st.markdown("<div style='font-size: 10px; color: #8c9ba5; margin-bottom: -4px;'>Anos:</div>", unsafe_allow_html=True)
            st.multiselect("Anos:", ano_opcoes, key="chart_anos", placeholder="Todos", label_visibility="collapsed")

        # 6. Filtragem Síncrona Rigorosa
        df_filtrado = df_completo

        escopo_atual = st.session_state.get('chart_escopo', 'Todas')
        if escopo_atual == "Ativa":
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_ativas)]
        elif escopo_atual == "Gerencial":
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_gerenciais)]

        unidades_sel = st.session_state.get('chart_unidades', [])
        if unidades_sel:
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_sel)]

        anos_sel = st.session_state.get('chart_anos', [])
        if anos_sel:
            df_filtrado = df_filtrado[df_filtrado["ano_referencia"].isin(anos_sel)]

        if not df_filtrado.empty:
            max_a_filt = int(df_filtrado['tmp_ano_num'].max())
            max_m_filt = int(df_filtrado[df_filtrado['tmp_ano_num'] == max_a_filt]['tmp_mes_num'].max())
            periodo_maximo_valido = f"{max_m_filt:02d}/{max_a_filt}"
        else:
            max_a_filt, max_m_filt = max_ano_base, max_mes_base
            periodo_maximo_valido = f"{max_m_filt:02d}/{max_a_filt}"

        p_sel = st.session_state.get('filtro_periodo_grafico')
        if not p_sel or df_filtrado.empty:
            st.session_state.filtro_periodo_grafico = periodo_maximo_valido
        else:
            m_str, a_str = p_sel.split('/')
            chk_per = df_filtrado[(df_filtrado['tmp_ano_num'] == int(a_str)) & (df_filtrado['tmp_mes_num'] == int(m_str))]
            if chk_per.empty:
                st.session_state.filtro_periodo_grafico = periodo_maximo_valido

        # --- LEGENDA INTELIGENTE COMPACTA ---
        c_leg1, c_leg2, c_leg3, c_leg4 = st.columns(4)
        lbl_tot = "🟡 Estoque Total" if st.session_state.vis_total else "⚪ Estoque Total"
        lbl_cri = "🟡 Estoque Crítico" if st.session_state.vis_critico else "⚪ Estoque Crítico"
        lbl_obs = "🟡 Estoque Obsoleto" if st.session_state.vis_obsoleto else "⚪ Estoque Obsoleto"
        lbl_obr = "🟡 Estoque Obra" if st.session_state.vis_obra else "⚪ Estoque Obra"

        with c_leg1:
            if st.button(lbl_tot, key="btn_vis_total", use_container_width=True, type="primary" if st.session_state.vis_total else "secondary"):
                st.session_state.vis_total = not st.session_state.vis_total
                st.rerun()

        with c_leg2:
            if st.button(lbl_cri, key="btn_vis_critico", use_container_width=True, type="primary" if st.session_state.vis_critico else "secondary"):
                st.session_state.vis_critico = not st.session_state.vis_critico
                st.rerun()

        with c_leg3:
            if st.button(lbl_obs, key="btn_vis_obsoleto", use_container_width=True, type="primary" if st.session_state.vis_obsoleto else "secondary"):
                st.session_state.vis_obsoleto = not st.session_state.vis_obsoleto
                st.rerun()

        with c_leg4:
            if st.button(lbl_obr, key="btn_vis_obra", use_container_width=True, type="primary" if st.session_state.vis_obra else "secondary"):
                st.session_state.vis_obra = not st.session_state.vis_obra
                st.rerun()

        # --- RENDERIZAÇÃO DO GRÁFICO DE TENDÊNCIA ---
        df_chart_base = df_filtrado

        df_estoque_mes = df_chart_base.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_estoque_mes = df_estoque_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        df_estoque_mes['Periodo'] = df_estoque_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_estoque_mes['ano_referencia'].astype(str)

        df_critico_trend = df_chart_base[df_chart_base['item_critico'] == '1-Sim']
        df_critico_mes = df_critico_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_critico_mes = df_critico_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        if not df_critico_mes.empty: df_critico_mes['Periodo'] = df_critico_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_critico_mes['ano_referencia'].astype(str)

        df_obsoleto_trend = df_chart_base[is_obsoleto_mask(df_chart_base)]
        df_obsoleto_mes = df_obsoleto_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_obsoleto_mes = df_obsoleto_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        if not df_obsoleto_mes.empty: df_obsoleto_mes['Periodo'] = df_obsoleto_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_obsoleto_mes['ano_referencia'].astype(str)

        df_obra_trend = df_chart_base[df_chart_base['nome_local_estoque'].astype(str).str.contains('obra', case=False, na=False)]
        df_obra_mes = df_obra_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_obra_mes = df_obra_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        if not df_obra_mes.empty: df_obra_mes['Periodo'] = df_obra_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_obra_mes['ano_referencia'].astype(str)

        def fmt_valor_milhoes(val):
            if val >= 1e9: return f"R$ {val/1e9:.1f}B".replace('.', ',')
            elif val >= 1e6: return f"R$ {val/1e6:.1f}M".replace('.', ',')
            else: return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        df_estoque_mes['texto_labels'] = df_estoque_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)
        if not df_critico_mes.empty: df_critico_mes['texto_labels'] = df_critico_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)
        if not df_obsoleto_mes.empty: df_obsoleto_mes['texto_labels'] = df_obsoleto_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)
        if not df_obra_mes.empty: df_obra_mes['texto_labels'] = df_obra_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)

        max_y_est = df_estoque_mes['valor_saldo_atual'].max() if not df_estoque_mes.empty else 100
        n_pontos_est = len(df_estoque_mes)

        layout_linha_estoque = dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=10, r=10, t=30, b=30), showlegend=False, hovermode='x')
        fig_linha_estoque = go.Figure()

        def get_vis(key): return True if st.session_state.get(key, False) else 'legendonly'

        fig_linha_estoque.add_trace(go.Scatter(
            x=df_estoque_mes['Periodo'], y=df_estoque_mes['valor_saldo_atual'],
            name='Estoque Total', mode='lines+markers+text', text=df_estoque_mes['texto_labels'],
            textposition='top center', textfont=dict(color='white', size=11),
            line=dict(color='#e74c3c', width=3, shape='spline', smoothing=1.3), 
            marker=dict(size=9, color='#e74c3c', line=dict(color='#ffffff', width=2)),
            fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.08)', hoverinfo='none',
            visible=get_vis('vis_total')
        ))

        if not df_estoque_mes.empty:
            max_idx = df_estoque_mes['valor_saldo_atual'].idxmax()
            min_idx = df_estoque_mes['valor_saldo_atual'].idxmin()
            
            fig_linha_estoque.add_annotation(x=df_estoque_mes.loc[max_idx, 'Periodo'], y=df_estoque_mes.loc[max_idx, 'valor_saldo_atual'], text="▲ PICO", showarrow=True, arrowhead=2, ax=0, ay=-35, font=dict(color="#e74c3c", size=10, family="monospace"), bgcolor="rgba(22, 28, 36, 0.85)", bordercolor="#e74c3c", borderwidth=1)
            fig_linha_estoque.add_annotation(x=df_estoque_mes.loc[min_idx, 'Periodo'], y=df_estoque_mes.loc[min_idx, 'valor_saldo_atual'], text="▼ VALE", showarrow=True, arrowhead=2, ax=0, ay=35, font=dict(color="#2ecc71", size=10, family="monospace"), bgcolor="rgba(22, 28, 36, 0.85)", bordercolor="#2ecc71", borderwidth=1)

        if not df_critico_mes.empty:
            fig_linha_estoque.add_trace(go.Scatter(
                x=df_critico_mes['Periodo'], y=df_critico_mes['valor_saldo_atual'], name='Estoque Crítico', mode='lines+markers+text', text=df_critico_mes['texto_labels'], textposition='bottom center', textfont=dict(color='#f39c12', size=11), line=dict(color='#f39c12', width=2.5, dash='dash', shape='spline', smoothing=1.3), marker=dict(size=6, color='#f39c12', line=dict(color='#ffffff', width=1)), hoverinfo='none', visible=get_vis('vis_critico')
            ))

        if not df_obsoleto_mes.empty:
            fig_linha_estoque.add_trace(go.Scatter(
                x=df_obsoleto_mes['Periodo'], y=df_obsoleto_mes['valor_saldo_atual'], name='Estoque Obsoleto', mode='lines+markers+text', text=df_obsoleto_mes['texto_labels'], textposition='top center', textfont=dict(color='#9b59b6', size=11), line=dict(color='#9b59b6', width=2.5, dash='dot', shape='spline', smoothing=1.3), marker=dict(size=6, color='#9b59b6', line=dict(color='#ffffff', width=1)), hoverinfo='none', visible=get_vis('vis_obsoleto')
            ))

        if not df_obra_mes.empty:
            fig_linha_estoque.add_trace(go.Scatter(
                x=df_obra_mes['Periodo'], y=df_obra_mes['valor_saldo_atual'], name='Estoque Obra', mode='lines+markers+text', text=df_obra_mes['texto_labels'], textposition='bottom center', textfont=dict(color='#1abc9c', size=11), line=dict(color='#1abc9c', width=2.5, dash='longdash', shape='spline', smoothing=1.3), marker=dict(size=6, color='#1abc9c', line=dict(color='#ffffff', width=1)), hoverinfo='none', visible=get_vis('vis_obra')
            ))

        sel_state = st.session_state.get("tendencia_geral", {})
        pontos_clicados = sel_state.get("selection", {}).get("points", []) if isinstance(sel_state, dict) else []

        if pontos_clicados and isinstance(pontos_clicados, list) and len(pontos_clicados) > 0 and "x" in pontos_clicados[0]:
            x_hl = pontos_clicados[0]["x"]
            if st.session_state.get("filtro_periodo_grafico") != x_hl:
                st.session_state.filtro_periodo_grafico = x_hl
                st.rerun()

        periodo_ativo = st.session_state.get("filtro_periodo_grafico")
        if periodo_ativo:
            match_idx = df_estoque_mes.index[df_estoque_mes['Periodo'] == periodo_ativo].tolist()
            if match_idx:
                idx = match_idx[0]
                fig_linha_estoque.add_shape(type="rect", x0=idx - 0.25, x1=idx + 0.25, y0=0, y1=1, yref="paper", fillcolor="rgba(216, 92, 39, 0.18)", line=dict(width=1.5, color="rgba(216, 92, 39, 0.6)"), layer="below")

        fig_linha_estoque.update_layout(**layout_linha_estoque)
        fig_linha_estoque.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, n_pontos_est - 0.2])
        fig_linha_estoque.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[-max_y_est * 0.08, max_y_est * 1.3], showticklabels=False)

        st.plotly_chart(fig_linha_estoque, use_container_width=True, config={'displayModeBar': False}, on_select="rerun", selection_mode="points", key="tendencia_geral")

    # 7. Criação do DataFrame de Snapshot Atual e Anterior
    df_snapshot = pd.DataFrame(columns=df_filtrado.columns)
    df_snapshot_prev = pd.DataFrame(columns=df_filtrado.columns)

    if st.session_state.get('filtro_periodo_grafico') and not df_filtrado.empty:
        p_sel = st.session_state.filtro_periodo_grafico
        m_str, a_str = p_sel.split('/')
        m_num, a_num = int(m_str), int(a_str)

        df_snapshot = df_filtrado[(df_filtrado['tmp_ano_num'] == a_num) & (df_filtrado['tmp_mes_num'] == m_num)]
        if m_num == 1:
            m_prev, a_prev = 12, a_num - 1
        else:
            m_prev, a_prev = m_num - 1, a_num
        df_snapshot_prev = df_filtrado[(df_filtrado['tmp_ano_num'] == a_prev) & (df_filtrado['tmp_mes_num'] == m_prev)]

    # 8. Somas e Contagens Dinâmicas
    def somar_coluna(dataframe, coluna):
        if coluna not in dataframe.columns or dataframe.empty: return 0.0
        return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

    val_estoque = somar_coluna(df_snapshot, "valor_saldo_atual")
    val_compras = somar_coluna(df_snapshot, "valor_entrada_compras")
    val_consumo = pd.to_numeric(df_snapshot["valor_saida_cons_interno"], errors='coerce').fillna(0.0).abs().sum() if "valor_saida_cons_interno" in df_snapshot.columns else 0.0
    val_skus = df_snapshot[(df_snapshot["qtde_saldo_atual"] > 0) & (df_snapshot["codigo_produto"] != "")]["codigo_produto"].nunique() if "qtde_saldo_atual" in df_snapshot.columns else 0
    val_critico = somar_coluna(df_snapshot[df_snapshot.get("item_critico", "") == "1-Sim"], "valor_saldo_atual") if not df_snapshot.empty else 0.0
    val_obsoleto = somar_coluna(df_snapshot[is_obsoleto_mask(df_snapshot)], "valor_saldo_atual") if not df_snapshot.empty else 0.0
    val_obra = somar_coluna(df_snapshot[df_snapshot.get("nome_local_estoque", "").astype(str).str.contains("obra", case=False, na=False)], "valor_saldo_atual") if not df_snapshot.empty else 0.0

    val_estoque_prev = somar_coluna(df_snapshot_prev, "valor_saldo_atual")
    val_compras_prev = somar_coluna(df_snapshot_prev, "valor_entrada_compras")
    val_consumo_prev = pd.to_numeric(df_snapshot_prev["valor_saida_cons_interno"], errors='coerce').fillna(0.0).abs().sum() if "valor_saida_cons_interno" in df_snapshot_prev.columns else 0.0
    val_skus_prev = df_snapshot_prev[(df_snapshot_prev["qtde_saldo_atual"] > 0) & (df_snapshot_prev["codigo_produto"] != "")]["codigo_produto"].nunique() if "qtde_saldo_atual" in df_snapshot_prev.columns else 0
    val_critico_prev = somar_coluna(df_snapshot_prev[df_snapshot_prev.get("item_critico", "") == "1-Sim"], "valor_saldo_atual") if not df_snapshot_prev.empty else 0.0
    val_obsoleto_prev = somar_coluna(df_snapshot_prev[is_obsoleto_mask(df_snapshot_prev)], "valor_saldo_atual") if not df_snapshot_prev.empty else 0.0
    val_obra_prev = somar_coluna(df_snapshot_prev[df_snapshot_prev.get("nome_local_estoque", "").astype(str).str.contains("obra", case=False, na=False)], "valor_saldo_atual") if not df_snapshot_prev.empty else 0.0

    # --- ⚡ AGREGAÇÃO MENSAL OPERACIONAL ---
    giro_mensal, giro_anual, cobertura_meses, cobertura_anos = 0.0, 0.0, 0.0, 0.0
    giro_mensal_prev, cobertura_meses_prev = 0.0, 0.0
    monthly_raw = pd.DataFrame(columns=['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num', 'estoque_op', 'consumo_op'])

    if not df_filtrado.empty:
        if st.session_state.get('filtro_periodo_grafico'):
            p_sel = st.session_state.filtro_periodo_grafico
            m_str, a_str = p_sel.split('/')
            ano_ativo_val, mes_teto_val = int(a_str), int(m_str)
        else:
            ano_ativo_val = int(df_filtrado['tmp_ano_num'].max())
            mes_teto_val = int(df_filtrado[df_filtrado['tmp_ano_num'] == ano_ativo_val]['tmp_mes_num'].max())

        df_op = df_filtrado.copy()
        df_op['consumo_abs'] = pd.to_numeric(df_op['valor_saida_cons_interno'], errors='coerce').fillna(0.0).abs()
        df_op['val_estoque'] = pd.to_numeric(df_op['valor_saldo_atual'], errors='coerce').fillna(0.0)

        mask_operacional_geral = ~(
            (df_op['item_critico'] == '1-Sim') |
            is_obsoleto_mask(df_op)
        )

        df_op['estoque_op'] = df_op['val_estoque'] * mask_operacional_geral
        df_op['consumo_op'] = df_op['consumo_abs'] * mask_operacional_geral

        monthly_raw = df_op.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num']).agg(
            estoque_op=('estoque_op', 'sum'),
            consumo_op=('consumo_op', 'sum')
        ).reset_index().sort_values(['tmp_ano_num', 'tmp_mes_num'])

        sub_atual = monthly_raw[(monthly_raw['tmp_ano_num'] == ano_ativo_val) & (monthly_raw['tmp_mes_num'] <= mes_teto_val)]
        if not sub_atual.empty:
            estoque_medio_op = sub_atual['estoque_op'].mean()
            consumo_medio_mensal = sub_atual['consumo_op'].mean()
            if estoque_medio_op > 0:
                giro_mensal = consumo_medio_mensal / estoque_medio_op
                giro_anual = giro_mensal * 12
            if consumo_medio_mensal > 0:
                cobertura_meses = estoque_medio_op / consumo_medio_mensal
                cobertura_anos = cobertura_meses / 12

        m_teto_prev = mes_teto_val - 1 if mes_teto_val > 1 else 12
        ano_prev_giro = ano_ativo_val if mes_teto_val > 1 else ano_ativo_val - 1
        sub_prev = monthly_raw[(monthly_raw['tmp_ano_num'] == ano_prev_giro) & (monthly_raw['tmp_mes_num'] <= m_teto_prev)]
        if not sub_prev.empty:
            est_med_p = sub_prev['estoque_op'].mean()
            con_med_p = sub_prev['consumo_op'].mean()
            if est_med_p > 0: giro_mensal_prev = con_med_p / est_med_p
            if con_med_p > 0: cobertura_meses_prev = est_med_p / con_med_p

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>💼 LINHA FINANCEIRA</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(render_card("📦", "icon-estoque", "(R$) ESTOQUE", fmt_brl(val_estoque), val_estoque, val_estoque_prev), unsafe_allow_html=True)
    with c2: st.markdown(render_card("⚠️", "icon-critico", "(R$) EST. CRÍTICO", fmt_brl(val_critico), val_critico, val_critico_prev), unsafe_allow_html=True)
    with c3: st.markdown(render_card("🗑️", "icon-obsoleto", "(R$) EST. OBSOLETO", fmt_brl(val_obsoleto), val_obsoleto, val_obsoleto_prev), unsafe_allow_html=True)
    with c4: st.markdown(render_card("🏗️", "icon-obra", "(R$) EST. OBRA", fmt_brl(val_obra), val_obra, val_obra_prev), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='section-title'>⚙️ LINHA OPERACIONAL</div>", unsafe_allow_html=True)
    c5, c6, c7, c8, c9 = st.columns(5)
    with c5: st.markdown(render_card("📥", "icon-compras", "COMPRAS", fmt_brl(val_compras), val_compras, val_compras_prev, "18px"), unsafe_allow_html=True)
    with c6: st.markdown(render_card("📤", "icon-consumo", "CONSUMO", fmt_brl(val_consumo), val_consumo, val_consumo_prev, "18px", invert_color=True), unsafe_allow_html=True)
    with c7: st.markdown(render_card("🏷️", "icon-skus", "SKUs ÚNICOS", fmt_int(val_skus), val_skus, val_skus_prev, "21px"), unsafe_allow_html=True)

    # Giro Card
    if giro_mensal_prev == 0 and giro_mensal == 0: giro_pct_str, giro_trend, giro_arr = "0,0%", "trend-neutral", "➖"
    elif giro_mensal_prev == 0: giro_pct_str, giro_trend, giro_arr = "100,0%", "trend-down", "🔺"
    else:
        g_pct = ((giro_mensal - giro_mensal_prev) / giro_mensal_prev) * 100
        giro_pct_str = f"{abs(g_pct):.1f}%".replace('.', ',')
        giro_trend = "trend-down" if g_pct > 0 else ("trend-up" if g_pct < 0 else "trend-neutral")
        giro_arr = "🔺" if g_pct > 0 else ("🔻" if g_pct < 0 else "➖")

    with c8:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="header-left"><div class="icon-box icon-giro">🔄</div><div class="card-title">GIRO DE ESTOQUE</div></div>
                <div class="trend-box {giro_trend}">{giro_arr} {giro_pct_str}</div>
            </div>
            <div style="display: flex; justify-content: space-around; align-items: center; margin-top: 8px;">
                <div style="text-align: center; flex: 1;"><span style="font-size: 11px; color: #8c9ba5; font-weight: bold;">MENSAL</span><br><span style="font-size: 19px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_dec(giro_mensal)}</span></div>
                <div style="height: 35px; width: 1px; background-color: #232b36;"></div>
                <div style="text-align: center; flex: 1;"><span style="font-size: 11px; color: #8c9ba5; font-weight: bold;">ANUAL</span><br><span style="font-size: 19px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_dec(giro_anual)}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Cobertura Card
    if cobertura_meses_prev == 0 and cobertura_meses == 0: cob_pct_str, cob_trend, cob_arr = "0,0%", "trend-neutral", "➖"
    elif cobertura_meses_prev == 0: cob_pct_str, cob_trend, cob_arr = "100,0%", "trend-up", "🔺"
    else:
        c_pct = ((cobertura_meses - cobertura_meses_prev) / cobertura_meses_prev) * 100
        cob_pct_str = f"{abs(c_pct):.1f}%".replace('.', ',')
        cob_trend = "trend-up" if c_pct > 0 else ("trend-down" if c_pct < 0 else "trend-neutral")
        cob_arr = "🔺" if c_pct > 0 else ("🔻" if c_pct < 0 else "➖")

    with c9:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="header-left"><div class="icon-box icon-cobertura">⏳</div><div class="card-title">COB. ESTOQUE</div></div>
                <div class="trend-box {cob_trend}">{cob_arr} {cob_pct_str}</div>
            </div>
            <div style="display: flex; justify-content: space-around; align-items: center; margin-top: 8px;">
                <div style="text-align: center; flex: 1;"><span style="font-size: 11px; color: #8c9ba5; font-weight: bold;">MENSAL</span><br><span style="font-size: 19px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_mes(cobertura_meses)}</span></div>
                <div style="height: 35px; width: 1px; background-color: #232b36;"></div>
                <div style="text-align: center; flex: 1;"><span style="font-size: 11px; color: #8c9ba5; font-weight: bold;">ANUAL</span><br><span style="font-size: 19px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_mes(cobertura_anos)}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if not df_filtrado.empty:
        layout_transparente = dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=10, r=10, t=10, b=10))

        col_c1, col_c2 = st.columns([5, 5], gap="medium")
        with col_c1:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>🏆 ESTOQUE POR UNIDADE (R$)</div>", unsafe_allow_html=True)
                
                with st.container(height=380, border=False):
                    df_rank = df_snapshot.groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                    df_rank = df_rank[df_rank['valor_saldo_atual'] > 0].sort_values('valor_saldo_atual', ascending=True)
                    df_rank['texto_formatado'] = df_rank['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e3:,.0f} mil".replace(',', 'X').replace('.', ',').replace('X', '.'))
                    df_rank['unidade_exibicao'] = df_rank['unidade_almoxarifado'] + " "

                    altura_grafico = max(350, len(df_rank) * 32)
                    fig_bar = px.bar(df_rank, x='valor_saldo_atual', y='unidade_exibicao', orientation='h', color_discrete_sequence=['#e74c3c'], text='texto_formatado')
                    fig_bar.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=155, r=15, t=10, b=10), height=altura_grafico, hovermode=False)
                    fig_bar.update_traces(textposition='auto', textfont=dict(color='white'), hoverinfo='none', hovertemplate=None)
                    fig_bar.update_xaxes(title="", showgrid=True, gridcolor='#232b36', tickprefix="R$ ", showticklabels=False, zeroline=False)
                    fig_bar.update_yaxes(title="", showgrid=False, tickfont=dict(size=10))
                    
                    st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False}, key="ranking_estoque_unidade")

        with col_c2:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>🍩 COMPOSIÇÃO DO ESTOQUE (%)</div>", unsafe_allow_html=True)
                
                m_obs = is_obsoleto_mask(df_snapshot)
                m_obra = df_snapshot.get("nome_local_estoque", "").astype(str).str.contains("obra", case=False, na=False) & ~m_obs
                m_crit = (df_snapshot.get("item_critico", "") == "1-Sim") & ~m_obs & ~m_obra
                
                val_obs_pizza = somar_coluna(df_snapshot[m_obs], "valor_saldo_atual")
                val_obra_pizza = somar_coluna(df_snapshot[m_obra], "valor_saldo_atual")
                val_crit_pizza = somar_coluna(df_snapshot[m_crit], "valor_saldo_atual")
                val_operacional_pizza = max(0, val_estoque - (val_obs_pizza + val_obra_pizza + val_crit_pizza))

                df_pizza = pd.DataFrame({
                    'Categoria': ['Estoque Crítico', 'Estoque Obsoleto', 'Estoque Obra', 'Estoque Operacional'], 
                    'Valor': [val_crit_pizza, val_obs_pizza, val_obra_pizza, val_operacional_pizza], 
                    'Cor': ['#f39c12', '#9b59b6', '#1abc9c', '#3498db']
                })
                df_pizza = df_pizza[df_pizza['Valor'] > 0]
                df_pizza['Valor_Formatado'] = df_pizza['Valor'].apply(fmt_brl)
                
                fig_rosca = go.Figure(data=[go.Pie(labels=df_pizza['Categoria'], values=df_pizza['Valor'], hole=0.65, marker=dict(colors=df_pizza['Cor'], line=dict(color='#161c24', width=2)), textinfo='label+percent', textposition='outside', hovertext=df_pizza['Valor_Formatado'], hovertemplate="<b>%{label}</b><br>%{hovertext}<extra></extra>", textfont=dict(size=11))])
                fig_rosca.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=80, r=80, t=30, b=30), height=380, showlegend=False, annotations=[dict(text=f"<b>TOTAL</b><br><span style='font-size:20px'>{fmt_valor_milhoes(val_estoque) if val_estoque > 0 else 'R$ 0,00'}</span>", x=0.5, y=0.5, font_size=14, font_color='white', showarrow=False)])
                st.plotly_chart(fig_rosca, use_container_width=True, config={'displayModeBar': False}, key="rosca_composicao")

        # ==========================================
        # 🆕 NOVOS RANKINGS POR CATEGORIA E UNIDADE
        # ==========================================
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='section-title'>📊 RANKING POR CATEGORIA E UNIDADE (R$)</div>", unsafe_allow_html=True)
        
        col_r1, col_r2, col_r3 = st.columns(3, gap="medium")
        
        # 1. Ranking Crítico por Unidade
        with col_r1:
            with st.container(border=True):
                st.markdown("<div style='color: #f39c12; font-size: 13px; font-weight: bold; margin-bottom: 12px;'>⚠️ ESTOQUE CRÍTICO POR UNIDADE</div>", unsafe_allow_html=True)
                with st.container(height=350, border=False):
                    df_crit_rank = df_snapshot[df_snapshot.get("item_critico", "") == "1-Sim"].groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                    df_crit_rank = df_crit_rank[df_crit_rank['valor_saldo_atual'] > 0].sort_values('valor_saldo_atual', ascending=True)
                    df_crit_rank['texto_formatado'] = df_crit_rank['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e3:,.0f} mil".replace(',', 'X').replace('.', ',').replace('X', '.'))
                    df_crit_rank['unidade_exibicao'] = df_crit_rank['unidade_almoxarifado'] + " "
                    
                    altura_crit = max(350, len(df_crit_rank) * 35) # Cálculo dinâmico para ativar a barra de rolagem
                    
                    fig_bar_crit = px.bar(df_crit_rank, x='valor_saldo_atual', y='unidade_exibicao', orientation='h', color_discrete_sequence=['#f39c12'], text='texto_formatado')
                    fig_bar_crit.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=110, r=10, t=10, b=10), height=altura_crit, hovermode=False)
                    fig_bar_crit.update_traces(textposition='auto', textfont=dict(color='white', size=9), hoverinfo='none')
                    fig_bar_crit.update_xaxes(title="", showgrid=True, gridcolor='#232b36', showticklabels=False, zeroline=False)
                    fig_bar_crit.update_yaxes(title="", showgrid=False, tickfont=dict(size=9))
                    st.plotly_chart(fig_bar_crit, use_container_width=True, config={'displayModeBar': False}, key="ranking_critico_unidade")

        # 2. Ranking Obsoleto por Unidade
        with col_r2:
            with st.container(border=True):
                st.markdown("<div style='color: #9b59b6; font-size: 13px; font-weight: bold; margin-bottom: 12px;'>🗑️ ESTOQUE OBSOLETO POR UNIDADE</div>", unsafe_allow_html=True)
                with st.container(height=350, border=False):
                    df_obs_rank = df_snapshot[is_obsoleto_mask(df_snapshot)].groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                    df_obs_rank = df_obs_rank[df_obs_rank['valor_saldo_atual'] > 0].sort_values('valor_saldo_atual', ascending=True)
                    df_obs_rank['texto_formatado'] = df_obs_rank['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e3:,.0f} mil".replace(',', 'X').replace('.', ',').replace('X', '.'))
                    df_obs_rank['unidade_exibicao'] = df_obs_rank['unidade_almoxarifado'] + " "
                    
                    altura_obs = max(350, len(df_obs_rank) * 35) # Cálculo dinâmico para ativar a barra de rolagem
                    
                    fig_bar_obs = px.bar(df_obs_rank, x='valor_saldo_atual', y='unidade_exibicao', orientation='h', color_discrete_sequence=['#9b59b6'], text='texto_formatado')
                    fig_bar_obs.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=110, r=10, t=10, b=10), height=altura_obs, hovermode=False)
                    fig_bar_obs.update_traces(textposition='auto', textfont=dict(color='white', size=9), hoverinfo='none')
                    fig_bar_obs.update_xaxes(title="", showgrid=True, gridcolor='#232b36', showticklabels=False, zeroline=False)
                    fig_bar_obs.update_yaxes(title="", showgrid=False, tickfont=dict(size=9))
                    st.plotly_chart(fig_bar_obs, use_container_width=True, config={'displayModeBar': False}, key="ranking_obsoleto_unidade")

        # 3. Ranking Obra por Unidade
        with col_r3:
            with st.container(border=True):
                st.markdown("<div style='color: #1abc9c; font-size: 13px; font-weight: bold; margin-bottom: 12px;'>🏗️ ESTOQUE OBRA POR UNIDADE</div>", unsafe_allow_html=True)
                with st.container(height=350, border=False):
                    df_obra_rank = df_snapshot[df_snapshot.get("nome_local_estoque", "").astype(str).str.contains("obra", case=False, na=False)].groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                    df_obra_rank = df_obra_rank[df_obra_rank['valor_saldo_atual'] > 0].sort_values('valor_saldo_atual', ascending=True)
                    df_obra_rank['texto_formatado'] = df_obra_rank['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e3:,.0f} mil".replace(',', 'X').replace('.', ',').replace('X', '.'))
                    df_obra_rank['unidade_exibicao'] = df_obra_rank['unidade_almoxarifado'] + " "
                    
                    altura_obra = max(350, len(df_obra_rank) * 35) # Cálculo dinâmico para ativar a barra de rolagem
                    
                    fig_bar_obra = px.bar(df_obra_rank, x='valor_saldo_atual', y='unidade_exibicao', orientation='h', color_discrete_sequence=['#1abc9c'], text='texto_formatado')
                    fig_bar_obra.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=110, r=10, t=10, b=10), height=altura_obra, hovermode=False)
                    fig_bar_obra.update_traces(textposition='auto', textfont=dict(color='white', size=9), hoverinfo='none')
                    fig_bar_obra.update_xaxes(title="", showgrid=True, gridcolor='#232b36', showticklabels=False, zeroline=False)
                    fig_bar_obra.update_yaxes(title="", showgrid=False, tickfont=dict(size=9))
                    st.plotly_chart(fig_bar_obra, use_container_width=True, config={'displayModeBar': False}, key="ranking_obra_unidade")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📈 EVOLUÇÃO TEMPORAL COMPRA x CONSUMO (R$)</div>", unsafe_allow_html=True)
            df_tempo = df_filtrado.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])[['valor_entrada_compras', 'valor_saida_cons_interno']].sum().reset_index().sort_values(['tmp_ano_num', 'tmp_mes_num'])
            df_tempo['Periodo'] = df_tempo['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_tempo['ano_referencia'].astype(str)
            df_tempo['valor_saida_cons_interno'] = df_tempo['valor_saida_cons_interno'].abs()
            fig_linha = go.Figure()
            fig_linha.add_trace(go.Scatter(x=df_tempo['Periodo'], y=df_tempo['valor_entrada_compras'], name='Compras', mode='lines+markers', line=dict(color='#e74c3c', width=3, shape='spline', smoothing=1.3)))
            fig_linha.add_trace(go.Scatter(x=df_tempo['Periodo'], y=df_tempo['valor_saida_cons_interno'], name='Consumo', mode='lines+markers', line=dict(color='#f39c12', width=3, shape='spline', smoothing=1.3)))
            if periodo_ativo and not df_tempo.empty:
                match_idx_tempo = df_tempo.index[df_tempo['Periodo'] == periodo_ativo].tolist()
                if match_idx_tempo: fig_linha.add_shape(type="rect", x0=match_idx_tempo[0] - 0.25, x1=match_idx_tempo[0] + 0.25, y0=0, y1=1, yref="paper", fillcolor="rgba(216, 92, 39, 0.18)", line=dict(width=1.5, color="rgba(216, 92, 39, 0.6)"), layer="below")
            fig_linha.update_layout(**layout_transparente, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1))
            fig_linha.update_xaxes(showgrid=False, zeroline=False)
            fig_linha.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, tickprefix="R$ ")
            st.plotly_chart(fig_linha, use_container_width=True, config={'displayModeBar': False}, key="compras_consumo_geral")

        st.markdown("<br>", unsafe_allow_html=True)
        col_esq, col_dir = st.columns(2)
        with col_esq:
            with st.container(border=True):
                st.markdown("<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;'><div style='color: #ffffff; font-size: 13px; font-weight: bold; border-left: 3px solid #d85c27; padding-left: 8px;'>📊 COMPRA x CONSUMO POR UNIDADE (R$)</div><div style='display: flex; gap: 10px; font-size: 11px; color: #8c9ba5; align-items: center; padding-right: 10px;'><span><span style='color: #e74c3c; font-size: 13px;'>■</span> Compras</span><span><span style='color: #f39c12; font-size: 13px;'>■</span> Consumo</span></div></div>", unsafe_allow_html=True)
                with st.container(height=380, border=False):
                    df_diag = df_snapshot.groupby('unidade_almoxarifado').agg(Compras=('valor_entrada_compras', 'sum'), Consumo=('valor_saida_cons_interno', lambda x: x.abs().sum())).reset_index()
                    
                    df_diag = df_diag[(df_diag['Compras'] > 0.01) | (df_diag['Consumo'] > 0.01)].sort_values('Compras', ascending=True)
                    ordem_unidades = df_diag['unidade_almoxarifado'].tolist()

                    def formata_mil_ou_zero(x):
                        if pd.isna(x) or x == 0:
                            return "R$ 0,00"
                        return f"R$ {x/1e3:,.0f} mil".replace(',', 'X').replace('.', ',').replace('X', '.')

                    df_diag['Compras_Label'] = df_diag['Compras'].apply(formata_mil_ou_zero)
                    df_diag['Consumo_Label'] = df_diag['Consumo'].apply(formata_mil_ou_zero)
                    df_diag_melted = df_diag.melt(id_vars=['unidade_almoxarifado', 'Compras_Label', 'Consumo_Label'], value_vars=['Compras', 'Consumo'], var_name='Métrica', value_name='Valor')
                    
                    df_diag_melted['Métrica'] = pd.Categorical(df_diag_melted['Métrica'], categories=['Compras', 'Consumo'], ordered=True)
                    df_diag_melted = df_diag_melted.sort_values(['unidade_almoxarifado', 'Métrica'])
                    df_diag_melted['Texto_Barra'] = np.where(df_diag_melted['Métrica'] == 'Compras', df_diag_melted['Compras_Label'], df_diag_melted['Consumo_Label'])
                    
                    fig_diag = px.bar(df_diag_melted, x='Valor', y='unidade_almoxarifado', color='Métrica', barmode='group', orientation='h', text='Texto_Barra', color_discrete_map={'Compras': '#e74c3c', 'Consumo': '#f39c12'}, category_orders={'unidade_almoxarifado': ordem_unidades, 'Métrica': ['Compras', 'Consumo']})
                    fig_diag.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=130, r=40, t=10, b=10), height=max(350, len(df_diag) * 60), showlegend=False, hovermode=False)
                    fig_diag.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, title="")
                    fig_diag.update_yaxes(title="", showgrid=False, zeroline=False, tickfont=dict(size=10), categoryorder='array', categoryarray=ordem_unidades)
                    fig_diag.update_traces(textposition='auto', textfont=dict(color='white', size=10), hoverinfo='none', hovertemplate=None)
                    st.plotly_chart(fig_diag, use_container_width=True, config={'displayModeBar': False}, key="diag_compras_consumo_lado")

        with col_dir:
            with st.container(border=True):
                st.markdown("<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;'><div style='color: #ffffff; font-size: 13px; font-weight: bold; border-left: 3px solid #3498db; padding-left: 8px;'>📦 SKUs POR UNIDADE (Qtde)</div></div>", unsafe_allow_html=True)
                with st.container(height=380, border=False):
                    df_skus_ativos = df_snapshot[(df_snapshot["qtde_saldo_atual"] > 0) & (df_snapshot["codigo_produto"] != "")]
                    df_skus = df_skus_ativos.groupby('unidade_almoxarifado').agg(Total_SKUs=('codigo_produto', 'nunique')).reset_index().sort_values('Total_SKUs', ascending=True)
                    ordem_skus = df_skus['unidade_almoxarifado'].tolist()
                    df_skus['SKUs_Label'] = df_skus['Total_SKUs'].apply(lambda x: f"{x:,.0f} SKUs".replace(',', '.'))
                    
                    fig_sku = px.bar(df_skus, x='Total_SKUs', y='unidade_almoxarifado', orientation='h', text='SKUs_Label', color_discrete_sequence=['#3498db'], category_orders={'unidade_almoxarifado': ordem_skus})
                    fig_sku.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=130, r=40, t=10, b=10), height=max(350, len(df_skus) * 45), showlegend=False, hovermode=False)
                    fig_sku.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, title="")
                    fig_sku.update_yaxes(title="", showgrid=False, zeroline=False, tickfont=dict(size=10), categoryorder='array', categoryarray=ordem_skus)
                    fig_sku.update_traces(textposition='auto', textfont=dict(color='white', size=10), hoverinfo='none', hovertemplate=None)
                    st.plotly_chart(fig_sku, use_container_width=True, config={'displayModeBar': False}, key="ranking_skus_lado")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📦 EVOLUÇÃO TEMPORAL DE SKUs (Qtde)</div>", unsafe_allow_html=True)
            df_sku_trend = df_filtrado[(df_filtrado["qtde_saldo_atual"] > 0) & (df_filtrado["codigo_produto"] != "")]
            df_sku_tempo = df_sku_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['codigo_produto'].nunique().reset_index().sort_values(['tmp_ano_num', 'tmp_mes_num'])
            df_sku_tempo['Periodo'] = df_sku_tempo['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_sku_tempo['ano_referencia'].astype(str)
            textos_skus = [f"{val:,}".replace(',', '.') for val in df_sku_tempo['codigo_produto']]
            
            layout_sku = dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=40, r=40, t=20, b=10))
            
            fig_sku_linha = go.Figure()
            fig_sku_linha.add_trace(go.Scatter(x=df_sku_tempo['Periodo'], y=df_sku_tempo['codigo_produto'], customdata=textos_skus, name='SKUs Ativos', mode='lines+markers+text', text=textos_skus, textposition='top center', textfont=dict(color='white', size=11), line=dict(color='#e74c3c', width=3, shape='spline', smoothing=1.3), fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.1)', hoverinfo='none'))
            
            if periodo_ativo and not df_sku_tempo.empty:
                match_idx_sku = df_sku_tempo.index[df_sku_tempo['Periodo'] == periodo_ativo].tolist()
                if match_idx_sku: fig_sku_linha.add_shape(type="rect", x0=match_idx_sku[0] - 0.25, x1=match_idx_sku[0] + 0.25, y0=0, y1=1, yref="paper", fillcolor="rgba(216, 92, 39, 0.18)", line=dict(width=1.5, color="rgba(216, 92, 39, 0.6)"), layer="below")
            
            fig_sku_linha.update_layout(**layout_sku, hovermode='x', showlegend=False)
            fig_sku_linha.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, len(df_sku_tempo) - 0.2])
            fig_sku_linha.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[0, (df_sku_tempo['codigo_produto'].max() if not df_sku_tempo.empty else 100) * 1.15], showticklabels=False)
            st.plotly_chart(fig_sku_linha, use_container_width=True, config={'displayModeBar': False}, key="skus_geral")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📈 EVOLUÇÃO TEMPORAL DE GIRO x COBERTURA (MENSAL)</div>", unsafe_allow_html=True)

            if not monthly_raw.empty:
                giro_mensal_lista, cobertura_lista, periodos_lista = [], [], []
                for _, row in monthly_raw.iterrows():
                    ano_alvo, mes_alvo = row['tmp_ano_num'], row['tmp_mes_num']
                    sub_ytd = monthly_raw[(monthly_raw['tmp_ano_num'] == ano_alvo) & (monthly_raw['tmp_mes_num'] <= mes_alvo)]
                    est_medio_ytd, con_medio_ytd = sub_ytd['estoque_op'].mean(), sub_ytd['consumo_op'].mean()
                    giro_mensal_lista.append((con_medio_ytd / est_medio_ytd) if est_medio_ytd > 0 else 0.0)
                    cobertura_lista.append((est_medio_ytd / con_medio_ytd) if con_medio_ytd > 0 else 0.0)
                    periodos_lista.append(f"{int(mes_alvo):02d}/{int(ano_alvo)}")

                df_duplo = pd.DataFrame({'Periodo': periodos_lista, 'Giro_Mensal': giro_mensal_lista, 'Cobertura_Meses': cobertura_lista})
                df_duplo['Giro_Texto'] = df_duplo['Giro_Mensal'].apply(lambda x: f"{x:,.2f}x".replace(',', 'X').replace('.', ',').replace('X', '.'))
                df_duplo['Cob_Texto'] = df_duplo['Cobertura_Meses'].apply(lambda x: f"{x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

                fig_duplo = go.Figure()
                fig_duplo.add_trace(go.Scatter(x=df_duplo['Periodo'], y=df_duplo['Giro_Mensal'], name='Giro Mensal', mode='lines+markers', line=dict(color='#3498db', width=3, shape='spline', smoothing=1.3), marker=dict(size=8, color='#3498db', line=dict(color='#ffffff', width=2)), customdata=df_duplo['Giro_Texto'], hovertemplate='Giro: %{customdata}<extra></extra>'))
                fig_duplo.add_trace(go.Scatter(x=df_duplo['Periodo'], y=df_duplo['Cobertura_Meses'], name='Cobertura', mode='lines+markers', line=dict(color='#e74c3c', width=3, shape='spline', smoothing=1.3), marker=dict(size=8, color='#e74c3c', line=dict(color='#ffffff', width=2)), yaxis='y2', customdata=df_duplo['Cob_Texto'], hovertemplate='Cobertura: %{customdata} meses<extra></extra>'))

                if periodo_ativo and not df_duplo.empty:
                    match_idx_duplo = df_duplo.index[df_duplo['Periodo'] == periodo_ativo].tolist()
                    if match_idx_duplo: fig_duplo.add_shape(type="rect", x0=match_idx_duplo[0] - 0.25, x1=match_idx_duplo[0] + 0.25, y0=0, y1=1, yref="paper", fillcolor="rgba(216, 92, 39, 0.18)", line=dict(width=1.5, color="rgba(216, 92, 39, 0.6)"), layer="below")

                fig_duplo.update_layout(**layout_transparente, hovermode='x unified', height=400, legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), yaxis=dict(title="", showgrid=True, gridcolor='#232b36', zeroline=False, showticklabels=False), yaxis2=dict(title="", overlaying='y', side='right', showgrid=False, zeroline=False, showticklabels=False))
                fig_duplo.update_xaxes(showgrid=False, zeroline=False)
                st.plotly_chart(fig_duplo, use_container_width=True, config={'displayModeBar': False}, key="duplo_eixo_giro_cobertura")
            else:
                st.info("Sem dados suficientes para calcular Giro x Cobertura no período selecionado.")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 5px; border-left: 3px solid #d85c27; padding-left: 10px;'>⏳ MATERIAIS PARADOS HÁ MAIS DE 3 MESES (SEM MOVIMENTAÇÃO)</div>", unsafe_allow_html=True)
            st.markdown("<p style='color: #8c9ba5; font-size: 12px; margin-bottom: 15px;'>Exclui itens Críticos e Obsoletos. Contabiliza o ciclo de inatividade considerando também o mês de origem (Efeito Coorte).</p>", unsafe_allow_html=True)

            df_calc = df_filtrado.copy()
            df_calc['tempo_idx'] = df_calc['tmp_ano_num'] * 12 + df_calc['tmp_mes_num']

            if periodo_ativo:
                m_At, a_At = periodo_ativo.split('/')
                snapshot_idx = int(a_At) * 12 + int(m_At)
            else:
                snapshot_idx = int(max_a_filt) * 12 + int(max_m_filt)

            df_calc = df_calc[(df_calc['tempo_idx'] <= snapshot_idx) & (df_calc['item_critico'] != '1-Sim') & (~is_obsoleto_mask(df_calc))]
            df_calc['teve_consumo'] = df_calc['valor_saida_cons_interno'].abs() > 0
            df_mov = df_calc[df_calc['teve_consumo']].groupby(['unidade_almoxarifado', 'codigo_produto'])['tempo_idx'].max().reset_index()
            df_mov.rename(columns={'tempo_idx': 'ultimo_mov_idx'}, inplace=True)

            m_teto_val = snapshot_idx % 12
            if m_teto_val == 0: m_teto_val = 12
            a_teto_val = snapshot_idx // 12 if m_teto_val != 12 else (snapshot_idx // 12) - 1

            df_snap_atual = df_calc[(df_calc['tmp_ano_num'] == a_teto_val) & (df_calc['tmp_mes_num'] == m_teto_val) & (df_calc['qtde_saldo_atual'] > 0) & (df_calc['codigo_produto'] != '')].copy()
            df_inativo = pd.merge(df_snap_atual, df_mov, on=['unidade_almoxarifado', 'codigo_produto'], how='left')

            df_min_hist = df_calc.groupby(['unidade_almoxarifado', 'codigo_produto'])['tempo_idx'].min().reset_index()
            df_min_hist.rename(columns={'tempo_idx': 'primeiro_hist_idx'}, inplace=True)
            df_inativo = pd.merge(df_inativo, df_min_hist, on=['unidade_almoxarifado', 'codigo_produto'], how='left')

            df_inativo['ultimo_mov_idx'] = df_inativo['ultimo_mov_idx'].fillna(df_inativo['primeiro_hist_idx'] - 1).fillna(snapshot_idx)
            df_inativo['meses_parado'] = (snapshot_idx - df_inativo['ultimo_mov_idx']).astype(int)

            df_parados_3m = df_inativo[df_inativo['meses_parado'] >= 3].copy()

            if not df_parados_3m.empty:
                df_chart_parados = df_parados_3m.groupby('meses_parado').agg(
                    valor_saldo_atual=('valor_saldo_atual', 'sum'),
                    qtd_skus=('codigo_produto', 'nunique')
                ).reset_index().sort_values('meses_parado')

                df_chart_parados['Meses_Label'] = df_chart_parados['meses_parado'].astype(str) + " Meses"
                df_chart_parados['Valor_Label'] = df_chart_parados['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e3:,.0f} mil".replace(',', 'X').replace('.', ',').replace('X', '.'))
                df_chart_parados['SKU_Label'] = df_chart_parados['qtd_skus'].astype(int).astype(str) + " SKUs"

                c_p1, c_p2 = st.columns(2)

                with c_p1:
                    st.markdown("<div style='color: #ffffff; font-size: 12px; font-weight: bold; margin-bottom: 5px; text-align: center;'>💰 VALOR PARADO (R$)</div>", unsafe_allow_html=True)
                    fig_val = px.bar(df_chart_parados, x='Meses_Label', y='valor_saldo_atual', text='Valor_Label', color_discrete_sequence=['#e74c3c'])
                    fig_val.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=20, r=20, t=10, b=10), height=320, showlegend=False)
                    fig_val.update_xaxes(title="", showgrid=False, zeroline=False)
                    fig_val.update_yaxes(title="", showgrid=True, gridcolor='#232b36', zeroline=False, showticklabels=False)
                    fig_val.update_traces(textposition='auto', textfont=dict(color='white', size=11))
                    st.plotly_chart(fig_val, use_container_width=True, config={'displayModeBar': False}, key="grafico_parados_valor")

                with c_p2:
                    st.markdown("<div style='color: #ffffff; font-size: 12px; font-weight: bold; margin-bottom: 5px; text-align: center;'>📦 QUANTIDADE DE SKUs (Qtde)</div>", unsafe_allow_html=True)
                    fig_sku_parados = px.bar(df_chart_parados, x='Meses_Label', y='qtd_skus', text='SKU_Label', color_discrete_sequence=['#f39c12'])
                    fig_sku_parados.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=20, r=20, t=10, b=10), height=320, showlegend=False)
                    fig_sku_parados.update_xaxes(title="", showgrid=False, zeroline=False)
                    fig_sku_parados.update_yaxes(title="", showgrid=True, gridcolor='#232b36', zeroline=False, showticklabels=False)
                    fig_sku_parados.update_traces(textposition='auto', textfont=dict(color='white', size=11))
                    st.plotly_chart(fig_sku_parados, use_container_width=True, config={'displayModeBar': False}, key="grafico_parados_skus")

                st.markdown("<br>", unsafe_allow_html=True)

                with st.expander("📂 Abrir Lista Completa de Itens Parados"):
                    col_f1, col_f2 = st.columns(2)
                    unidades_paradas = sorted(df_parados_3m['unidade_almoxarifado'].unique().tolist())
                    meses_opcoes = sorted(df_parados_3m['meses_parado'].unique().tolist())

                    with col_f1:
                        unidade_filtro_audit = st.selectbox("Filtrar por Unidade:", ["Todas as Unidades"] + unidades_paradas, key="select_audit_parados")
                    with col_f2:
                        meses_filtro_audit = st.selectbox("Filtrar por Tempo Parado:", ["Todos os Meses"] + [f"{m} Meses" for m in meses_opcoes], key="select_audit_meses")

                    df_audit_view = df_parados_3m.copy()

                    if unidade_filtro_audit != "Todas as Unidades":
                        df_audit_view = df_audit_view[df_audit_view['unidade_almoxarifado'] == unidade_filtro_audit]
                    if meses_filtro_audit != "Todos os Meses":
                        mes_selecionado = int(meses_filtro_audit.split()[0])
                        df_audit_view = df_audit_view[df_audit_view['meses_parado'] == mes_selecionado]

                    df_audit_view = df_audit_view.sort_values(by=['valor_saldo_atual', 'meses_parado'], ascending=[False, False])

                    df_audit_exib = pd.DataFrame()
                    df_audit_exib['Unidade'] = df_audit_view['unidade_almoxarifado']
                    df_audit_exib['Código SKU'] = df_audit_view['codigo_produto']
                    df_audit_exib['Nome do Produto'] = df_audit_view.get('nome_produto', '')
                    df_audit_exib['Quantidade'] = df_audit_view['qtde_saldo_atual'].apply(fmt_int)
                    df_audit_exib['Valor Parado'] = df_audit_view['valor_saldo_atual'].apply(fmt_brl)
                    df_audit_exib['Meses Parado'] = df_audit_view['meses_parado'].astype(str) + " meses"

                    st.dataframe(df_audit_exib, use_container_width=True, hide_index=True)

                    df_audit_excel = pd.DataFrame({
                        'Unidade': df_audit_view['unidade_almoxarifado'],
                        'Código SKU': df_audit_view['codigo_produto'],
                        'Nome do Produto': df_audit_view.get('nome_produto', ''),
                        'Quantidade': df_audit_view['qtde_saldo_atual'],
                        'Valor Parado': df_audit_view['valor_saldo_atual'],
                        'Meses Parado': df_audit_view['meses_parado']
                    })

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_audit_excel.to_excel(writer, index=False, header=False, startrow=1, sheet_name='Itens Parados')
                        workbook = writer.book
                        worksheet = writer.sheets['Itens Parados']

                        num_rows = len(df_audit_excel)
                        num_cols = len(df_audit_excel.columns)
                        col_settings = [{'header': col} for col in df_audit_excel.columns]

                        if num_rows > 0:
                            worksheet.add_table(0, 0, num_rows, num_cols - 1, {
                                'columns': col_settings,
                                'style': 'Table Style Medium 14'
                            })
                        else:
                            worksheet.write_row(0, 0, df_audit_excel.columns)

                        inteiro_format = workbook.add_format({'num_format': '#,##0'})
                        moeda_format = workbook.add_format({'num_format': 'R$ #,##0.00'})

                        worksheet.set_column(0, 0, 20)
                        worksheet.set_column(1, 1, 15)
                        worksheet.set_column(2, 2, 45)
                        worksheet.set_column(3, 3, 15, inteiro_format)
                        worksheet.set_column(4, 4, 20, moeda_format)
                        worksheet.set_column(5, 5, 15, inteiro_format)

                    st.download_button(
                        label="📥 Baixar em Formato de Tabela do Excel (.xlsx)",
                        data=output.getvalue(),
                        file_name="auditoria_itens_parados.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.info("Nenhum material operacional parado há mais de 3 meses para o período selecionado.")

import textwrap

# ==========================================
# ABA 2: INVENTÁRIOS (Tema Escuro & Tabela Executiva)
# ==========================================
with aba_inventarios:
    st.markdown("<div style='color: #ffffff; font-size: 16px; font-weight: bold; margin-bottom: 15px;'>📦 GESTÃO DE INVENTÁRIOS (FECHAMENTO EXECUTIVO)</div>", unsafe_allow_html=True)

    if df_inventario.empty:
        st.warning("⚠️ Nenhum dado de inventário encontrado na base.")
    else:
        # 1. Filtros Superiores (Mantidos no padrão escuro)
        with st.container(border=True):
            col_inv_f1, col_inv_f2, col_inv_f3, col_inv_f4 = st.columns(4, gap="small")
            with col_inv_f1:
                lista_empresas = sorted([str(x) for x in df_inventario.get('empresa_nome', pd.Series()).dropna().unique()]) if 'empresa_nome' in df_inventario.columns else []
                empresa_sel = st.selectbox("Empresa:", ["Todas as Empresas"] + lista_empresas, key="inv_empresa_sel")
            with col_inv_f2:
                df_ano = df_inventario if empresa_sel == "Todas as Empresas" else df_inventario[df_inventario.get('empresa_nome', '').astype(str) == empresa_sel]
                lista_anos = sorted([str(x) for x in df_ano.get('ano_referencia', pd.Series()).dropna().unique()], reverse=True) if 'ano_referencia' in df_ano.columns else []
                ano_sel = st.selectbox("Ano:", ["Todos os Anos"] + lista_anos, key="inv_ano_sel")
            with col_inv_f3:
                df_mes = df_ano if ano_sel == "Todos os Anos" else df_ano[df_ano.get('ano_referencia', '').astype(str) == ano_sel]
                lista_meses = sorted([str(x) for x in df_mes.get('mes_referencia', pd.Series()).dropna().unique()]) if 'mes_referencia' in df_mes.columns else []
                mes_sel = st.selectbox("Mês:", ["Todos os Meses"] + lista_meses, key="inv_mes_sel")
            with col_inv_f4:
                df_tipo = df_mes if mes_sel == "Todos os Meses" else df_mes[df_mes.get('mes_referencia', '').astype(str) == mes_sel]
                lista_tipos = sorted([str(x) for x in df_tipo.get('tipo_inventario', pd.Series()).dropna().unique()]) if 'tipo_inventario' in df_tipo.columns else []
                tipo_sel = st.selectbox("Tipo de Inventário:", ["Todos os Tipos"] + lista_tipos, key="inv_tipo_sel")

        # 2. Lógica de Filtragem
        df_inv = df_inventario.copy()
        if empresa_sel != "Todas as Empresas": df_inv = df_inv[df_inv['empresa_nome'].astype(str) == empresa_sel]
        if ano_sel != "Todos os Anos": df_inv = df_inv[df_inv['ano_referencia'].astype(str) == ano_sel]
        if mes_sel != "Todos os Meses": df_inv = df_inv[df_inv['mes_referencia'].astype(str) == mes_sel]
        if tipo_sel != "Todos os Tipos": df_inv = df_inv[df_inv['tipo_inventario'].astype(str) == tipo_sel]

        st.markdown("<br>", unsafe_allow_html=True)

        if df_inv.empty:
            st.info("Nenhum dado encontrado para os filtros selecionados.")
        else:
            # 3. Cálculos Consolidados
            saldo_sistema = df_inv['saldo_anterior_val'].sum() if 'saldo_anterior_val' in df_inv.columns else 0.0
            ganhos = df_inv[df_inv['diferenca_val'] > 0]['diferenca_val'].sum() if 'diferenca_val' in df_inv.columns else 0.0
            perdas = df_inv[df_inv['diferenca_val'] < 0]['diferenca_val'].sum() if 'diferenca_val' in df_inv.columns else 0.0
            diferenca_liq = ganhos + perdas
            
            divergencia_absoluta = abs(df_inv['diferenca_val']).sum() if 'diferenca_val' in df_inv.columns else 0.0
            acuracia_fin = max(0, (1 - (divergencia_absoluta / saldo_sistema)) * 100) if saldo_sistema > 0 else (100.0 if divergencia_absoluta == 0 else 0.0)

            cor_ganho = "#2ecc71"
            cor_perda = "#e74c3c"

            # Agrupamento por empresa para gerar as linhas da tabela
            if 'empresa_nome' in df_inv.columns:
                df_empresas_resumo = df_inv.groupby('empresa_nome').agg(
                    saldo=('saldo_anterior_val', 'sum'),
                    div_abs=('diferenca_val', lambda x: abs(x).sum()),
                    ganho=('diferenca_val', lambda x: x[x > 0].sum()),
                    perda=('diferenca_val', lambda x: x[x < 0].sum()),
                    liq=('diferenca_val', 'sum')
                ).reset_index()
            else:
                df_empresas_resumo = pd.DataFrame()

            # 4. Construção da Tabela com Estilo Escuro (Dark Theme)
            linhas_tabela_html = ""
            if not df_empresas_resumo.empty:
                for _, row in df_empresas_resumo.iterrows():
                    emp = row['empresa_nome']
                    sal = row['saldo']
                    dab = row['div_abs']
                    acur = max(0, (1 - (dab / sal)) * 100) if sal > 0 else 100.0
                    gnh = row['ganho']
                    prd = row['perda']
                    liq = row['liq']
                    
                    linhas_tabela_html += f"""
                    <tr style="border-bottom: 1px solid #232b36;">
                        <td style="padding: 12px; border-right: 1px solid #232b36; text-align: left; padding-left: 15px; color: #ffffff;">{emp}</td>
                        <td style="padding: 12px; border-right: 1px solid #232b36; font-weight: bold; color: #ffffff;">{acur:.2f}%</td>
                        <td style="padding: 12px; border-right: 1px solid #232b36; color: {cor_ganho}; font-weight: bold;">{fmt_brl(gnh)}</td>
                        <td style="padding: 12px; border-right: 1px solid #232b36; color: {cor_perda}; font-weight: bold;">{fmt_brl(prd)}</td>
                        <td style="padding: 12px; color: {cor_perda if liq < 0 else cor_ganho}; font-weight: bold;">{fmt_brl(liq)}</td>
                    </tr>
                    """

            html_tabela_geral = textwrap.dedent(f"""
            <div style="background-color: #161c24; border: 1px solid #232b36; border-radius: 8px; overflow: hidden; margin-bottom: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.5);">
                <div style="background-color: #1a222d; padding: 12px; text-align: center; font-weight: bold; color: #ffffff; border-bottom: 2px solid #d85c27; font-size: 15px; letter-spacing: 0.5px;">
                    INVENTÁRIO GERAL - RESUMO EXECUTIVO
                </div>
                <table style="width: 100%; text-align: center; border-collapse: collapse; font-size: 13px;">
                    <tr style="background-color: #1f2836; font-weight: bold; font-size: 11px; color: #8c9ba5; border-bottom: 1px solid #232b36; text-transform: uppercase;">
                        <th style="padding: 10px; border-right: 1px solid #232b36; text-align: left; padding-left: 15px;">Empresa</th>
                        <th style="padding: 10px; border-right: 1px solid #232b36;">Acurácia</th>
                        <th style="padding: 10px; border-right: 1px solid #232b36;">Ganhos</th>
                        <th style="padding: 10px; border-right: 1px solid #232b36;">Perdas</th>
                        <th style="padding: 10px;">Diferença</th>
                    </tr>
                    {linhas_tabela_html}
                    <tr style="background-color: #1a222d; font-size: 15px; border-top: 2px solid #333d4d;">
                        <td style="padding: 15px; border-right: 1px solid #232b36; text-align: left; padding-left: 15px; font-weight: 900; color: #ffffff;">TOTAL</td>
                        <td style="padding: 15px; border-right: 1px solid #232b36; font-weight: 900; color: #ffffff;">{acuracia_fin:.2f}%</td>
                        <td style="padding: 15px; border-right: 1px solid #232b36; color: {cor_ganho}; font-weight: 900;">{fmt_brl(ganhos)}</td>
                        <td style="padding: 15px; border-right: 1px solid #232b36; color: {cor_perda}; font-weight: 900;">{fmt_brl(perdas)}</td>
                        <td style="padding: 15px; color: {cor_perda if diferenca_liq < 0 else cor_ganho}; font-weight: 900;">{fmt_brl(diferenca_liq)}</td>
                    </tr>
                </table>
            </div>
            """)
            
            st.markdown(html_tabela_geral, unsafe_allow_html=True)
