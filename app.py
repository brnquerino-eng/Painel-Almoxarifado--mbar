from concurrent.futures import ThreadPoolExecutor
import time
import pandas as pd
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
    st.session_state.chart_escopo = "Todas"
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
    "codigo_produto", "qtde_saldo_atual", "item_critico", "nome_local_estoque",
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

# 2. Performance Otimizada e Estável com Retry Progressivo
@st.cache_data()
def carregar_dados():
    try:
        with st.spinner("Carregando e normalizando base de dados em alta performance..."):
            count_res = supabase.table(table_name).select("*", count="exact", head=True).execute()
            total_rows = getattr(count_res, 'count', None)

            if not total_rows or total_rows == 0:
                total_rows = 460000  # Fallback de segurança

            batch_size = 1000
            ranges = [(i, min(i + batch_size - 1, total_rows - 1)) for i in range(0, total_rows, batch_size)]

            all_data = []

            def fetch_range(start_r, end_r, tentativas=3):
                ultimo_erro = None
                for tentativa in range(1, tentativas + 1):
                    try:
                        res = supabase.table(table_name).select(
                            "valor_saldo_atual, valor_entrada_compras, valor_saida_cons_interno, unidade_almoxarifado, mes_referencia, ano_referencia, codigo_produto, qtde_saldo_atual, item_critico, nome_local_estoque"
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

            if "unidade_almoxarifado" in df.columns:
                df["unidade_almoxarifado"] = df["unidade_almoxarifado"].astype(str).str.strip().str.upper()

            def limpar_valor(val):
                if pd.isna(val) or val is None:
                    return ""
                s_val = str(val).strip()
                if s_val.endswith('.0'):
                    s_val = s_val[:-2]
                return s_val

            for col in ["mes_referencia", "ano_referencia", "codigo_produto", "item_critico", "nome_local_estoque"]:
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

df_completo = carregar_dados()

# Identificação automática do último mês e ano disponíveis na base inteira
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
        padding: 16px;
        min-height: 130px;
        height: auto;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5), 0 4px 8px rgba(0, 0, 0, 0.3);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    .card-box:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8), 0 5px 15px rgba(216, 92, 39, 0.15);
        border-color: #333d4d;
    }
    div[data-testid="stContainer"] {
        background-color: #161c24 !important;
        border: 1px solid #232b36 !important;
        border-radius: 8px !important;
        padding: 20px !important;
        box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8) !important;
        overflow: visible !important;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    div[data-testid="stContainer"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 20px 35px rgba(0, 0, 0, 0.85), 0 8px 20px rgba(216, 92, 39, 0.2) !important;
        border-color: #333d4d !important;
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
    .icon-critico { background-color: #2a1515; color: #e74c3c; }
    .icon-obsoleto { background-color: #2a2a2a; color: #9b59b6; }
    .icon-obra { background-color: #1a2a2a; color: #1abc9c; }
    .icon-skus { background-color: #1a222d; color: #3498db; }
    .icon-giro { background-color: #221a2d; color: #9b59b6; }
    .icon-cobertura { background-color: #2a2211; color: #e67e22; }
    .card-title {
        color: #8c9ba5;
        font-size: 11px;
        font-weight: bold;
        letter-spacing: 0.5px;
    }
    .card-value {
        color: #ffffff;
        font-size: 21px;
        font-weight: bold;
        text-align: center;
        font-family: monospace;
        margin-top: 8px;
    }
    .section-title {
        color: #ffffff;
        font-size: 14px;
        font-weight: bold;
        margin-bottom: 12px;
        letter-spacing: 0.5px;
        border-left: 3px solid #d85c27;
        padding-left: 10px;
    }
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
        <div class="title-sub">Valores Consolidados</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 5. SISTEMA DE ABAS NATIVO
# ==========================================
aba_geral, aba_detalhada = st.tabs(["📈 Visão Geral", "📊 Análises Detalhadas & Tendência de Estoque"])

with aba_geral:
    # --- CONTROLES DO GRÁFICO DENTRO DO PRÓPRIO CARTÃO DE TENDÊNCIA ---
    with st.container(border=True):
        col_tg_title, col_tg_escopo, col_tg_unid, col_tg_ano = st.columns([1.8, 1.2, 2.0, 1.5])
        with col_tg_title:
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 5px; border-left: 3px solid #d85c27; padding-left: 10px;'>📊 TENDÊNCIA: TOTAL VS CRÍTICO VS OBSOLETO VS OBRA</div>", unsafe_allow_html=True)
        
        with col_tg_escopo:
            st.selectbox("Escopo:", ["Todas", "Ativas", "Gerenciais"], key="chart_escopo")
        
        with col_tg_unid:
            if st.session_state.chart_escopo == "Ativas":
                opcoes_unid = unidades_ativas
            elif st.session_state.chart_escopo == "Gerenciais":
                opcoes_unid = unidades_gerenciais
            else:
                opcoes_unid = unidades_opcoes
            
            st.multiselect("Unidades:", opcoes_unid, key="chart_unidades", placeholder="Todas")
        
        with col_tg_ano:
            st.multiselect("Anos:", ano_opcoes, key="chart_anos", placeholder="Todos")

        # 6. Filtragem Síncrona Rigorosa
        df_filtrado = df_completo.copy()

        escopo_atual = st.session_state.get('chart_escopo', 'Todas')
        if escopo_atual == "Ativas":
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_ativas)]
        elif escopo_atual == "Gerenciais":
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_gerenciais)]

        unidades_sel = st.session_state.get('chart_unidades', [])
        if unidades_sel:
            df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(unidades_sel)]

        anos_sel = st.session_state.get('chart_anos', [])
        if anos_sel:
            df_filtrado = df_filtrado[df_filtrado["ano_referencia"].isin(anos_sel)]

        # Validação e Correção Automática do Período Ativo
        if st.session_state.get('filtro_periodo_grafico') and not df_filtrado.empty:
            p_sel = st.session_state.filtro_periodo_grafico
            m_str, a_str = p_sel.split('/')
            chk_per = df_filtrado[(df_filtrado['tmp_ano_num'] == int(a_str)) & (df_filtrado['tmp_mes_num'] == int(m_str))]
            if chk_per.empty:
                max_a = df_filtrado['tmp_ano_num'].max()
                max_m = df_filtrado[df_filtrado['tmp_ano_num'] == max_a]['tmp_mes_num'].max()
                st.session_state.filtro_periodo_grafico = f"{int(max_m):02d}/{int(max_a)}"

        # --- LEGENDA INTELIGENTE COM MEMÓRIA (Substitui a nativa do Plotly) ---
        c_leg1, c_leg2, c_leg3, c_leg4 = st.columns(4)
        with c_leg1:
            if st.button("● Estoque Total", key="btn_vis_total", use_container_width=True):
                st.session_state.vis_total = not st.session_state.vis_total
                st.rerun()
        with c_leg2:
            if st.button("● Estoque Crítico", key="btn_vis_critico", use_container_width=True):
                st.session_state.vis_critico = not st.session_state.vis_critico
                st.rerun()
        with c_leg3:
            if st.button("● Estoque Obsoleto", key="btn_vis_obsoleto", use_container_width=True):
                st.session_state.vis_obsoleto = not st.session_state.vis_obsoleto
                st.rerun()
        with c_leg4:
            if st.button("● Estoque Obra", key="btn_vis_obra", use_container_width=True):
                st.session_state.vis_obra = not st.session_state.vis_obra
                st.rerun()

        # --- RENDERIZAÇÃO DO GRÁFICO DE TENDÊNCIA ---
        df_chart_base = df_filtrado.copy()

        df_estoque_mes = df_chart_base.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_estoque_mes = df_estoque_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        df_estoque_mes['Periodo'] = df_estoque_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_estoque_mes['ano_referencia'].astype(str)

        df_critico_trend = df_chart_base[df_chart_base['item_critico'] == '1-Sim']
        df_critico_mes = df_critico_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_critico_mes = df_critico_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        df_critico_mes['Periodo'] = df_critico_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_critico_mes['ano_referencia'].astype(str)

        df_obsoleto_trend = df_chart_base[df_chart_base['nome_local_estoque'].astype(str).str.contains('Obsoleto', case=False, na=False)]
        df_obsoleto_mes = df_obsoleto_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_obsoleto_mes = df_obsoleto_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        df_obsoleto_mes['Periodo'] = df_obsoleto_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_obsoleto_mes['ano_referencia'].astype(str)

        df_obra_trend = df_chart_base[df_chart_base['nome_local_estoque'].astype(str).str.contains('obra', case=False, na=False)]
        df_obra_mes = df_obra_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
        df_obra_mes = df_obra_mes.sort_values(['tmp_ano_num', 'tmp_mes_num'])
        df_obra_mes['Periodo'] = df_obra_mes['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_obra_mes['ano_referencia'].astype(str)

        def fmt_valor_milhoes(val):
            if val >= 1e9:
                return f"R$ {val/1e9:.1f}B".replace('.', ',')
            elif val >= 1e6:
                return f"R$ {val/1e6:.1f}M".replace('.', ',')
            else:
                return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        df_estoque_mes['texto_labels'] = df_estoque_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)
        if not df_critico_mes.empty: df_critico_mes['texto_labels'] = df_critico_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)
        if not df_obsoleto_mes.empty: df_obsoleto_mes['texto_labels'] = df_obsoleto_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)
        if not df_obra_mes.empty: df_obra_mes['texto_labels'] = df_obra_mes['valor_saldo_atual'].apply(fmt_valor_milhoes)

        max_y_est = df_estoque_mes['valor_saldo_atual'].max() if not df_estoque_mes.empty else 100
        n_pontos_est = len(df_estoque_mes)

        layout_linha_estoque = dict(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#8c9ba5'),
            margin=dict(l=10, r=10, t=30, b=30),
            showlegend=False,  # Desativada pois usamos nossa legenda inteligente customizada
            hovermode='x'
        )

        fig_linha_estoque = go.Figure()

        # Função auxiliar de visibilidade com base no session_state
        def get_vis(key):
            return True if st.session_state.get(key, False) else 'legendonly'

        fig_linha_estoque.add_trace(go.Scatter(
            x=df_estoque_mes['Periodo'], y=df_estoque_mes['valor_saldo_atual'],
            name='Estoque Total', mode='lines+markers+text', text=df_estoque_mes['texto_labels'],
            textposition='top center', textfont=dict(color='white', size=11),
            line=dict(color='#e74c3c', width=3), marker=dict(size=8, color='#e74c3c', line=dict(color='#ffffff', width=2)),
            fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.08)', hoverinfo='none',
            visible=get_vis('vis_total')
        ))

        if not df_critico_mes.empty:
            fig_linha_estoque.add_trace(go.Scatter(
                x=df_critico_mes['Periodo'], y=df_critico_mes['valor_saldo_atual'],
                name='Estoque Crítico', mode='lines+markers+text', text=df_critico_mes['texto_labels'],
                textposition='bottom center', textfont=dict(color='#f39c12', size=11),
                line=dict(color='#f39c12', width=2.5, dash='dash'), marker=dict(size=6, color='#f39c12', line=dict(color='#ffffff', width=1)),
                hoverinfo='none', visible=get_vis('vis_critico')
            ))

        if not df_obsoleto_mes.empty:
            fig_linha_estoque.add_trace(go.Scatter(
                x=df_obsoleto_mes['Periodo'], y=df_obsoleto_mes['valor_saldo_atual'],
                name='Estoque Obsoleto', mode='lines+markers+text', text=df_obsoleto_mes['texto_labels'],
                textposition='top center', textfont=dict(color='#9b59b6', size=11),
                line=dict(color='#9b59b6', width=2.5, dash='dot'), marker=dict(size=6, color='#9b59b6', line=dict(color='#ffffff', width=1)),
                hoverinfo='none', visible=get_vis('vis_obsoleto')
            ))

        if not df_obra_mes.empty:
            fig_linha_estoque.add_trace(go.Scatter(
                x=df_obra_mes['Periodo'], y=df_obra_mes['valor_saldo_atual'],
                name='Estoque Obra', mode='lines+markers+text', text=df_obra_mes['texto_labels'],
                textposition='bottom center', textfont=dict(color='#1abc9c', size=11),
                line=dict(color='#1abc9c', width=2.5, dash='longdash'), marker=dict(size=6, color='#1abc9c', line=dict(color='#ffffff', width=1)),
                hoverinfo='none', visible=get_vis('vis_obra')
            ))

        sel_state = st.session_state.get("tendencia_geral", {})
        pontos_clicados = sel_state.get("selection", {}).get("points", []) if isinstance(sel_state, dict) else []

        if pontos_clicados:
            x_hl = pontos_clicados[0]["x"]
            if st.session_state.get("filtro_periodo_grafico") != x_hl:
                st.session_state.filtro_periodo_grafico = x_hl
                st.rerun()

        periodo_ativo = st.session_state.get("filtro_periodo_grafico")
        if periodo_ativo:
            match_idx = df_estoque_mes.index[df_estoque_mes['Periodo'] == periodo_ativo].tolist()
            if match_idx:
                idx = match_idx[0]
                fig_linha_estoque.add_shape(
                    type="rect",
                    x0=idx - 0.25, x1=idx + 0.25,
                    y0=0, y1=1, yref="paper",
                    fillcolor="rgba(216, 92, 39, 0.18)", line=dict(width=1.5, color="rgba(216, 92, 39, 0.6)"), layer="below"
                )

        fig_linha_estoque.update_layout(**layout_linha_estoque)
        fig_linha_estoque.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, n_pontos_est - 0.2])
        fig_linha_estoque.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[-max_y_est * 0.08, max_y_est * 1.3], showticklabels=False)

        st.plotly_chart(
            fig_linha_estoque, use_container_width=True, config={'displayModeBar': False},
            on_select="rerun", selection_mode="points", key="tendencia_geral"
        )
        
        if st.session_state.get('filtro_periodo_grafico'):
            col_b_info, col_b_acao = st.columns([3, 1])
            with col_b_info:
                st.markdown(f"<span style='color: #d85c27; font-size: 12px;'>📌 Período fixado pelo gráfico: <b>{st.session_state.filtro_periodo_grafico}</b></span>", unsafe_allow_html=True)
            with col_b_acao:
                if st.button("🔄 Limpar Filtro do Gráfico", use_container_width=True):
                    st.session_state.filtro_periodo_grafico = None
                    st.rerun()

    # 6.1 Resumo Inteligente Logo Abaixo do Gráfico
    if escopo_atual == "Todas":
        texto_informativo = "Exibindo dados consolidados de **todas as unidades** (Ativas e Gerenciais)."
    elif escopo_atual == "Ativas":
        texto_informativo = "Exibindo dados consolidados apenas das **unidades ativas**."
    else:
        texto_informativo = "Exibindo dados consolidados apenas das **unidades gerenciais**."

    if st.session_state.get('filtro_periodo_grafico'):
        texto_informativo += f" 🎯 **Período Ativo (Gráfico): {st.session_state.filtro_periodo_grafico}**"

    st.markdown(f"<p style='color: #8c9ba5; font-size: 14px; margin-top: 10px; margin-bottom: 20px;'>{texto_informativo}</p>", unsafe_allow_html=True)

    # 7. Criação do DataFrame de Snapshot (para os Cards e Top 10)
    df_snapshot = df_filtrado.copy()

    if st.session_state.get('filtro_periodo_grafico'):
        p_sel = st.session_state.filtro_periodo_grafico
        m_str, a_str = p_sel.split('/')
        m_num, a_num = int(m_str), int(a_str)
        df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == a_num) & (df_snapshot['tmp_mes_num'] == m_num)]
    else:
        if st.session_state.get('chart_anos'):
            anos_sel_num = [int(a) for a in st.session_state.chart_anos]
            df_anos_sel = df_snapshot[df_snapshot['tmp_ano_num'].isin(anos_sel_num)]
            if not df_anos_sel.empty:
                m_ano = df_anos_sel['tmp_ano_num'].max()
                m_mes = df_anos_sel[df_anos_sel['tmp_ano_num'] == m_ano]['tmp_mes_num'].max()
                df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == m_ano) & (df_snapshot['tmp_mes_num'] == m_mes)]
        else:
            df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == max_ano_base) & (df_snapshot['tmp_mes_num'] == max_mes_base)]

    # 8. Somas e Contagens Dinâmicas baseadas no Snapshot Sincronizado
    def somar_coluna(dataframe, coluna):
        if coluna not in dataframe.columns or dataframe.empty:
            return 0.0
        return pd.to_numeric(dataframe[coluna], errors='coerce').fillna(0.0).sum()

    val_estoque = somar_coluna(df_snapshot, "valor_saldo_atual")

    if "qtde_saldo_atual" in df_snapshot.columns and "codigo_produto" in df_snapshot.columns:
        df_skus_ativos = df_snapshot[
            (df_snapshot["qtde_saldo_atual"] > 0) & (df_snapshot["codigo_produto"] != "")
        ]
        val_skus = df_skus_ativos["codigo_produto"].nunique()
    else:
        val_skus = 0

    if "item_critico" in df_snapshot.columns and "valor_saldo_atual" in df_snapshot.columns:
        df_criticos = df_snapshot[df_snapshot["item_critico"] == "1-Sim"]
        val_critico = somar_coluna(df_criticos, "valor_saldo_atual")
    else:
        val_critico = 0.0

    if "nome_local_estoque" in df_snapshot.columns and "valor_saldo_atual" in df_snapshot.columns:
        df_obsoleto = df_snapshot[df_snapshot["nome_local_estoque"].astype(str).str.contains("Obsoleto", case=False, na=False)]
        val_obsoleto = somar_coluna(df_obsoleto, "valor_saldo_atual")
    else:
        val_obsoleto = 0.0

    if "nome_local_estoque" in df_snapshot.columns and "valor_saldo_atual" in df_snapshot.columns:
        df_obra = df_snapshot[df_snapshot["nome_local_estoque"].astype(str).str.contains("obra", case=False, na=False)]
        val_obra = somar_coluna(df_obra, "valor_saldo_atual")
    else:
        val_obra = 0.0

    # --- CÁLCULO DO GIRO E COBERTURA DE ESTOQUE ---
    giro_mensal = 0.0
    giro_anual = 0.0
    cobertura_meses = 0.0
    cobertura_anos = 0.0

    if not df_filtrado.empty:
        df_giro = df_filtrado.copy()
        df_giro['consumo_abs'] = pd.to_numeric(df_giro['valor_saida_cons_interno'], errors='coerce').fillna(0.0).abs()
        df_giro['val_estoque'] = pd.to_numeric(df_giro['valor_saldo_atual'], errors='coerce').fillna(0.0)

        df_giro['is_critico'] = df_giro['item_critico'] == '1-Sim'
        df_giro['is_obsoleto'] = df_giro['nome_local_estoque'].astype(str).str.contains('Obsoleto', case=False, na=False)

        monthly_groups = df_giro.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])
        monthly_df = monthly_groups.apply(lambda g: pd.Series({
            'estoque_op': g.loc[~(g['is_critico'] | g['is_obsoleto']), 'val_estoque'].sum(),
            'consumo_op': g.loc[~(g['is_critico'] | g['is_obsoleto']), 'consumo_abs'].sum()
        })).reset_index()

        if not monthly_df.empty:
            estoque_medio_op = monthly_df['estoque_op'].mean()
            consumo_medio_mensal = monthly_df['consumo_op'].mean()
            if estoque_medio_op > 0:
                giro_mensal = consumo_medio_mensal / estoque_medio_op
                giro_anual = giro_mensal * 12
            if consumo_medio_mensal > 0:
                cobertura_meses = estoque_medio_op / consumo_medio_mensal
                cobertura_anos = cobertura_meses / 12

    def fmt_brl(val):
        return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def fmt_int(val):
        return f"{val:,}".replace(',', '.')

    def fmt_pct(val):
        return f"{val * 100:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "%"

    def fmt_dec(val):
        return f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "x"

    def fmt_mes(val):
        return f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    st.markdown("<br>", unsafe_allow_html=True)

    # --- LINHA FINANCEIRA ---
    st.markdown("<div class='section-title'>💼 LINHA FINANCEIRA</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

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
                <div class="icon-box icon-critico">⚠️</div>
                <div class="card-title">ESTOQUE CRÍTICO (1-SIM)</div>
            </div>
            <div class="card-value">{fmt_brl(val_critico)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-obsoleto">🗑️</div>
                <div class="card-title">ESTOQUE OBSOLETO</div>
            </div>
            <div class="card-value">{fmt_brl(val_obsoleto)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-obra">🏗️</div>
                <div class="card-title">ESTOQUE OBRA</div>
            </div>
            <div class="card-value">{fmt_brl(val_obra)}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- LINHA OPERACIONAL ---
    st.markdown("<div class='section-title'>⚙️ LINHA OPERACIONAL</div>", unsafe_allow_html=True)
    c5, c6, c7 = st.columns(3)

    with c5:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-skus">🏷️</div>
                <div class="card-title">TOTAL DE SKUs ÚNICOS</div>
            </div>
            <div class="card-value">{fmt_int(val_skus)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c6:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-giro">🔄</div>
                <div class="card-title">GIRO DE ESTOQUE</div>
            </div>
            <div style="display: flex; justify-content: space-around; align-items: center; margin-top: 8px;">
                <div style="text-align: center; flex: 1;">
                    <span style="font-size: 10px; color: #8c9ba5; letter-spacing: 0.5px;">MENSAL</span><br>
                    <span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_dec(giro_mensal)}</span>
                </div>
                <div style="height: 35px; width: 1px; background-color: #232b36;"></div>
                <div style="text-align: center; flex: 1;">
                    <span style="font-size: 10px; color: #8c9ba5; letter-spacing: 0.5px;">ANUALIZADO</span><br>
                    <span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_dec(giro_anual)}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c7:
        st.markdown(f"""
        <div class="card-box">
            <div class="card-header">
                <div class="icon-box icon-cobertura">⏳</div>
                <div class="card-title">COBERTURA DE ESTOQUE</div>
            </div>
            <div style="display: flex; justify-content: space-around; align-items: center; margin-top: 8px;">
                <div style="text-align: center; flex: 1;">
                    <span style="font-size: 10px; color: #8c9ba5; letter-spacing: 0.5px;">MENSAL (MESES)</span><br>
                    <span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_mes(cobertura_meses)}</span>
                </div>
                <div style="height: 35px; width: 1px; background-color: #232b36;"></div>
                <div style="text-align: center; flex: 1;">
                    <span style="font-size: 10px; color: #8c9ba5; letter-spacing: 0.5px;">ANUALIZADO (ANOS)</span><br>
                    <span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_mes(cobertura_anos)}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 10. GRÁFICOS INTERATIVOS SECUNDÁRIOS
    st.markdown("<br>", unsafe_allow_html=True)

    if not df_filtrado.empty:
        layout_transparente = dict(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#8c9ba5'),
            margin=dict(l=10, r=10, t=10, b=10)
        )

        col_g1, col_g2 = st.columns([6, 4], gap="large")

        with col_g1:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📈 EVOLUÇÃO: COMPRAS VS CONSUMO</div>", unsafe_allow_html=True)

                df_trend = df_filtrado.copy()
                df_tempo = df_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])[['valor_entrada_compras', 'valor_saida_cons_interno']].sum().reset_index()
                df_tempo = df_tempo.sort_values(['tmp_ano_num', 'tmp_mes_num'])
                df_tempo['Periodo'] = df_tempo['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_tempo['ano_referencia'].astype(str)

                df_tempo['valor_saida_cons_interno'] = df_tempo['valor_saida_cons_interno'].abs()

                fig_linha = go.Figure()
                fig_linha.add_trace(go.Scatter(x=df_tempo['Periodo'], y=df_tempo['valor_entrada_compras'],
                                             name='Compras', mode='lines+markers', line=dict(color='#f39c12', width=3)))
                fig_linha.add_trace(go.Scatter(x=df_tempo['Periodo'], y=df_tempo['valor_saida_cons_interno'],
                                             name='Consumo', mode='lines+markers', line=dict(color='#e74c3c', width=3)))

                fig_linha.update_layout(**layout_transparente, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1))
                fig_linha.update_xaxes(showgrid=False, zeroline=False)
                fig_linha.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, tickprefix="R$ ")

                st.plotly_chart(fig_linha, use_container_width=True, config={'displayModeBar': False}, key="compras_consumo_geral")

        with col_g2:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>🏆 TOP 10: MAIOR VALOR EM ESTOQUE</div>", unsafe_allow_html=True)

                df_rank = df_snapshot.groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                df_rank = df_rank[df_rank['valor_saldo_atual'] > 0]
                df_rank = df_rank.sort_values('valor_saldo_atual', ascending=True).tail(10)

                df_rank['texto_formatado'] = df_rank['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e6:.1f}M".replace('.', ','))

                fig_bar = px.bar(df_rank, x='valor_saldo_atual', y='unidade_almoxarifado', orientation='h',
                                 color_discrete_sequence=['#e74c3c'], text='texto_formatado')

                fig_bar.update_layout(**layout_transparente, hovermode="y unified")
                fig_bar.update_traces(textposition='auto', textfont=dict(color='white'))
                fig_bar.update_xaxes(title="", showgrid=True, gridcolor='#232b36', tickprefix="R$ ", zeroline=False)
                fig_bar.update_yaxes(title="", showgrid=False)

                st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False}, key="top10_geral")

        # 11. EVOLUÇÃO TEMPORAL DE SKUS ATIVOS
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📦 EVOLUÇÃO DO MIX: TOTAL DE SKUs ATIVOS NO TEMPO</div>", unsafe_allow_html=True)

            df_sku_trend = df_filtrado[
                (df_filtrado["qtde_saldo_atual"] > 0) & (df_filtrado["codigo_produto"] != "")
            ].copy()

            df_sku_tempo = df_sku_trend.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['codigo_produto'].nunique().reset_index()
            df_sku_tempo = df_sku_tempo.sort_values(['tmp_ano_num', 'tmp_mes_num'])
            df_sku_tempo['Periodo'] = df_sku_tempo['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_sku_tempo['ano_referencia'].astype(str)

            textos_skus = [f"{val:,}".replace(',', '.') for val in df_sku_tempo['codigo_produto']]
            max_y = df_sku_tempo['codigo_produto'].max() if not df_sku_tempo.empty else 100
            n_pontos = len(df_sku_tempo)

            total_skus_grafico = df_snapshot[
                (df_snapshot['qtde_saldo_atual'] > 0) & (df_snapshot['codigo_produto'] != "")
            ]['codigo_produto'].nunique()
            total_formatado = f"{total_skus_grafico:,}".replace(',', '.')

            layout_sku = dict(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#8c9ba5'),
                margin=dict(l=40, r=40, t=50, b=10),
                annotations=[
                    dict(
                        x=1.0,
                        y=1.12,
                        xref="paper",
                        yref="paper",
                        text=f"<b>Total Período:</b> {total_formatado}",
                        showarrow=False,
                        font=dict(color="#ffffff", size=12, family="monospace"),
                        bgcolor="#1a222d",
                        bordercolor="#333d4d",
                        borderwidth=1,
                        borderpad=6,
                        align="right"
                    )
                ]
            )

            fig_sku_linha = go.Figure()
            fig_sku_linha.add_trace(go.Scatter(
                x=df_sku_tempo['Periodo'],
                y=df_sku_tempo['codigo_produto'],
                customdata=textos_skus,
                name='SKUs Ativos',
                mode='lines+markers+text',
                text=textos_skus,
                textposition='top center',
                textfont=dict(color='white', size=11),
                line=dict(color='#e74c3c', width=3),
                fill='tozeroy',
                fillcolor='rgba(231, 76, 60, 0.1)',
                hoverinfo='none'
            ))

            fig_sku_linha.update_layout(**layout_sku, hovermode='x', showlegend=False)
            fig_sku_linha.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, n_pontos - 0.2])
            fig_sku_linha.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[0, max_y * 1.15], showticklabels=False)

            st.plotly_chart(fig_sku_linha, use_container_width=True, config={'displayModeBar': False}, key="skus_geral")

    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")

with aba_detalhada:
    if not df_snapshot.empty:
        st.markdown("<div style='color: #ffffff; font-size: 16px; font-weight: bold; margin-bottom: 15px;'>📋 CONSOLIDAÇÃO ANALÍTICA POR UNIDADE DE ALMOXARIFADO</div>", unsafe_allow_html=True)

        df_tabela = df_snapshot.groupby('unidade_almoxarifado').agg(
            Valor_Estoque=('valor_saldo_atual', 'sum'),
            Valor_Compras=('valor_entrada_compras', 'sum'),
            Valor_Consumo=('valor_saida_cons_interno', lambda x: x.abs().sum()),
            SKUs_Ativos=('codigo_produto', lambda x: x[
                (df_snapshot.loc[x.index, 'qtde_saldo_atual'] > 0) & (x != "")
            ].nunique())
        ).reset_index()

        df_tabela = df_tabela.sort_values(by='Valor_Estoque', ascending=False)

        df_exibicao = pd.DataFrame()
        df_exibicao['Unidade de Almoxarifado'] = df_tabela['unidade_almoxarifado']
        df_exibicao['Valor em Estoque'] = df_tabela['Valor_Estoque'].apply(fmt_brl)
        df_exibicao['Valor de Compras'] = df_tabela['Valor_Compras'].apply(fmt_brl)
        df_exibicao['Valor de Consumo'] = df_tabela['Valor_Consumo'].apply(fmt_brl)
        df_exibicao['SKUs Ativos'] = df_tabela['SKUs_Ativos'].apply(fmt_int)

        st.dataframe(
            df_exibicao,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")
