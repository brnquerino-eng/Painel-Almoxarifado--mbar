from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import streamlit as st
from supabase import create_client
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# CONFIGURAÇÃO E ESTADOS DA APLICAÇÃO
# ==========================================
st.set_page_config(page_title="Visão Executiva de Estoque", layout="wide")

if 'f_unidades' not in st.session_state: st.session_state.f_unidades = []
if 'f_meses' not in st.session_state: st.session_state.f_meses = []
if 'f_anos' not in st.session_state: st.session_state.f_anos = []

# ==========================================
# 1. CONEXÃO COM SUPABASE
# ==========================================
@st.cache_resource
def conectar_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = conectar_supabase()
table_name = "painel_estoque"

# ==========================================
# 2. CARREGAMENTO E NORMALIZAÇÃO
# ==========================================
@st.cache_data()
def carregar_dados():
    try:
        with st.spinner("Carregando e normalizando base de dados em alta performance..."):
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
                    if data:
                        all_data.extend(data)

            if not all_data: return pd.DataFrame()
            df = pd.DataFrame(all_data)

            if "unidade_almoxarifado" in df.columns:
                df["unidade_almoxarifado"] = df["unidade_almoxarifado"].astype(str).str.strip().str.upper()

            def limpar_valor(val):
                if pd.isna(val) or val is None: return ""
                s_val = str(val).strip()
                return s_val[:-2] if s_val.endswith('.0') else s_val

            for col in ["mes_referencia", "ano_referencia", "codigo_produto", "item_critico", "nome_local_estoque"]:
                if col in df.columns:
                    df[col] = df[col].apply(limpar_valor)

            for col in ["valor_saldo_atual", "valor_entrada_compras", "valor_saida_cons_interno", "qtde_saldo_atual"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            # Colunas numéricas temporárias para ordenação de tempo
            df['tmp_ano_num'] = pd.to_numeric(df['ano_referencia'], errors='coerce').fillna(0)
            df['tmp_mes_num'] = pd.to_numeric(df['mes_referencia'], errors='coerce').fillna(0)

            return df
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return pd.DataFrame()

df_completo = carregar_dados()

# 2.1 Identificação automática do Snapshot (Último mês atualizado na base)
if not df_completo.empty:
    max_ano_base = df_completo['tmp_ano_num'].max()
    max_mes_base = df_completo[df_completo['tmp_ano_num'] == max_ano_base]['tmp_mes_num'].max()
else:
    max_ano_base, max_mes_base = 2026, 7

unidades_opcoes = sorted(df_completo["unidade_almoxarifado"].dropna().unique().tolist()) if not df_completo.empty else []
unidades_gerenciais = [u for u in unidades_opcoes if "GERENCIAL" in u]
unidades_ativas = [u for u in unidades_opcoes if "GERENCIAL" not in u]

def _chave_numerica(val):
    try: return (0, int(val))
    except (ValueError, TypeError): return (1, str(val))

dict_meses_nome = {
    "1": "01 - Janeiro", "01": "01 - Janeiro", "2": "02 - Fevereiro", "02": "02 - Fevereiro",
    "3": "03 - Março", "03": "03 - Março", "4": "04 - Abril", "04": "04 - Abril",
    "5": "05 - Maio", "05": "05 - Maio", "6": "06 - Junho", "06": "06 - Junho",
    "7": "07 - Julho", "07": "07 - Julho", "8": "08 - Agosto", "08": "08 - Agosto",
    "9": "09 - Setembro", "09": "09 - Setembro", "10": "10 - Outubro", "10": "10 - Outubro",
    "11": "11 - Novembro", "11": "11 - Novembro", "12": "12 - Dezembro", "12": "12 - Dezembro"
}

raw_meses = sorted(df_completo["mes_referencia"].dropna().unique().tolist(), key=_chave_numerica) if not df_completo.empty else []
map_raw_para_fmt = {m: dict_meses_nome.get(str(m).strip(), f"{str(m).strip().zfill(2)} - Mês {m}") for m in raw_meses}
map_fmt_para_raw = {v: k for k, v in map_raw_para_fmt.items()}
meses_opcoes_formatadas = list(map_raw_para_fmt.values())

ano_opcoes = sorted(df_completo["ano_referencia"].dropna().unique().tolist(), key=_chave_numerica) if not df_completo.empty else []

# ==========================================
# 3. MODAL DE FILTROS
# ==========================================
@st.dialog("Filtros de Análise - Visão Executiva", width="large")
def modal_filtros():
    st.markdown("<p style='color: #8c9ba5; font-size: 13px; margin-bottom: 20px;'>Selecione uma ou mais opções para consolidar os dados (deixe em branco para considerar todas):</p>", unsafe_allow_html=True)
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        default_ativas = [u for u in st.session_state.f_unidades if u in unidades_ativas]
        f_ativas_sel = st.multiselect("🏢 Unidades Ativas:", unidades_ativas, default=default_ativas)
    with col_u2:
        default_gerenciais = [u for u in st.session_state.f_unidades if u in unidades_gerenciais]
        f_gerenciais_sel = st.multiselect("📊 Unidades Gerenciais:", unidades_gerenciais, default=default_gerenciais)

    f_unidades_sel = f_ativas_sel + f_gerenciais_sel
    default_meses_fmt = [map_raw_para_fmt[m] for m in st.session_state.f_meses if m in map_raw_para_fmt]
    f_meses_sel_fmt = st.multiselect("Meses de Referência:", meses_opcoes_formatadas, default=default_meses_fmt)
    f_anos_sel = st.multiselect("Anos de Referência:", ano_opcoes, default=st.session_state.f_anos)

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("Limpar Filtros", use_container_width=True):
            st.session_state.f_unidades, st.session_state.f_meses, st.session_state.f_anos = [], [], []
            st.rerun()
    with col_btn2:
        if st.button("Aplicar Filtros", use_container_width=True, type="primary"):
            st.session_state.f_unidades = f_unidades_sel
            st.session_state.f_meses = [map_fmt_para_raw[f] for f in f_meses_sel_fmt]
            st.session_state.f_anos = f_anos_sel
            st.rerun()

# ==========================================
# 4. ESTILIZAÇÃO CSS
# ==========================================
st.markdown("""
<style>
    @keyframes smoothPageLoad { 0% { opacity: 0.2; transform: scale(0.98); } 100% { opacity: 1; transform: scale(1); } }
    .stApp { background-color: #0f141c; animation: smoothPageLoad 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards !important; }
    div[role="dialog"], div[data-testid="stDialog"] { animation: scaleInModal 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards !important; transform-origin: center center; }
    div[data-testid="stModalScrim"] { background-color: rgba(15, 20, 28, 0.7) !important; animation: fadeInScrim 0.6s ease-out forwards !important; }
    .stButton > button { background-color: #1a222d !important; color: #ffffff !important; border: 1px solid #333d4d !important; border-radius: 6px !important; transition: all 0.3s ease; }
    .stButton > button:hover { border-color: #d85c27 !important; color: #d85c27 !important; }
    .header-container { display: flex; align-items: center; border-bottom: 2px solid #d85c27; padding-bottom: 12px; margin-bottom: 20px; gap: 20px; }
    .logo-container { background-color: #ffffff; padding: 6px 16px; border-radius: 4px; text-align: center; font-family: Arial, sans-serif; }
    .logo-main { color: #12161f; font-weight: 900; font-size: 18px; line-height: 1; }
    .logo-sub { color: #d85c27; font-size: 9px; font-weight: bold; letter-spacing: 1px; }
    .title-container { border-left: 1px solid #333d4d; padding-left: 15px; }
    .title-main { color: #ffffff; font-size: 18px; font-weight: bold; letter-spacing: 1px; margin: 0; }
    .title-sub { color: #8c9ba5; font-size: 12px; margin: 0; }
    .card-box { background-color: #161c24; border: 1px solid #232b36; border-radius: 8px; padding: 16px; min-height: 130px; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 10px 20px rgba(0, 0, 0, 0.5), 0 4px 8px rgba(0, 0, 0, 0.3); transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
    .card-box:hover { transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8), 0 5px 15px rgba(216, 92, 39, 0.15); border-color: #333d4d; }
    div[data-testid="stContainer"] { background-color: #161c24 !important; border: 1px solid #232b36 !important; border-radius: 8px !important; padding: 20px !important; box-shadow: 0 15px 30px rgba(0, 0, 0, 0.8) !important; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
    div[data-testid="stContainer"]:hover { transform: translateY(-4px); box-shadow: 0 20px 35px rgba(0, 0, 0, 0.85), 0 8px 20px rgba(216, 92, 39, 0.2) !important; border-color: #333d4d !important; }
    .card-header { display: flex; align-items: center; gap: 12px; }
    .icon-box { width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 14px; }
    .icon-estoque { background-color: #132a24; color: #2ecc71; } .icon-critico { background-color: #2a1515; color: #e74c3c; } .icon-obsoleto { background-color: #2a2a2a; color: #9b59b6; } .icon-obra { background-color: #1a2a2a; color: #1abc9c; } .icon-skus { background-color: #1a222d; color: #3498db; } .icon-giro { background-color: #221a2d; color: #9b59b6; } .icon-cobertura { background-color: #2a2211; color: #e67e22; }
    .card-title { color: #8c9ba5; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; }
    .card-value { color: #ffffff; font-size: 21px; font-weight: bold; text-align: center; font-family: monospace; margin-top: 8px; }
    .section-title { color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 12px; letter-spacing: 0.5px; border-left: 3px solid #d85c27; padding-left: 10px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 5. HEADER
# ==========================================
col_header, col_btn = st.columns([5, 1])
with col_header:
    st.markdown("""
    <div class="header-container">
        <div class="logo-container"><div class="logo-main">Âmbar</div><div class="logo-sub">ENERGIA</div></div>
        <div class="title-container"><div class="title-main">VISÃO EXECUTIVA DE ESTOQUE</div><div class="title-sub">Valores Consolidados</div></div>
    </div>
    """, unsafe_allow_html=True)

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    filtro_ativo = bool(st.session_state.f_unidades or st.session_state.f_meses or st.session_state.f_anos)
    if st.button("⚙️ Filtros (Ativo)" if filtro_ativo else "⚙️ Filtros", use_container_width=True):
        modal_filtros()

# Texto explicativo dinâmico
f_unidades_atuais = st.session_state.get('f_unidades', [])
if not f_unidades_atuais:
    texto_info = "Exibindo dados consolidados de **todas as unidades** (Ativas e Gerenciais)."
else:
    sel_ativas = [u for u in f_unidades_atuais if u in unidades_ativas]
    sel_gerenciais = [u for u in f_unidades_atuais if u in unidades_gerenciais]
    partes = []
    if sel_ativas: partes.append(f"**{len(sel_ativas)} unidade(s) ativa(s)**")
    if sel_gerenciais: partes.append(f"**{len(sel_gerenciais)} gerencial(is)**")
    texto_info = "Exibindo dados de " + " e ".join(partes) + "."
st.markdown(f"<p style='color: #8c9ba5; font-size: 14px; margin-top: -10px; margin-bottom: 20px;'>{texto_info}</p>", unsafe_allow_html=True)

# ==========================================
# 6. ENGENHARIA DE DADOS E SNAPSHOT
# ==========================================
# df_filtrado = base para evolução temporal completa
df_filtrado = df_completo.copy()
if st.session_state.f_unidades: df_filtrado = df_filtrado[df_filtrado["unidade_almoxarifado"].isin(st.session_state.f_unidades)]
if st.session_state.f_meses: df_filtrado = df_filtrado[df_filtrado["mes_referencia"].isin(st.session_state.f_meses)]
if st.session_state.f_anos: df_filtrado = df_filtrado[df_filtrado["ano_referencia"].isin(st.session_state.f_anos)]

# df_snapshot = base para cards e posições atuais de saldo (posição estática para não acumular tudo)
df_snapshot = df_filtrado.copy()
if not st.session_state.f_meses:
    if st.session_state.f_anos:
        anos_sel_num = [int(a) for a in st.session_state.f_anos]
        df_anos_sel = df_snapshot[df_snapshot['tmp_ano_num'].isin(anos_sel_num)]
        if not df_anos_sel.empty:
            m_ano = df_anos_sel['tmp_ano_num'].max()
            m_mes = df_anos_sel[df_anos_sel['tmp_ano_num'] == m_ano]['tmp_mes_num'].max()
            df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == m_ano) & (df_snapshot['tmp_mes_num'] == m_mes)]
    else:
        df_snapshot = df_snapshot[(df_snapshot['tmp_ano_num'] == max_ano_base) & (df_snapshot['tmp_mes_num'] == max_mes_base)]

# Funções auxiliares
def somar_coluna(df_target, coluna):
    return pd.to_numeric(df_target[coluna], errors='coerce').fillna(0.0).sum() if not df_target.empty and coluna in df_target.columns else 0.0

def fmt_brl(val): return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
def fmt_int(val): return f"{val:,}".replace(',', '.')
def fmt_pct(val): return f"{val * 100:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "%"
def fmt_dec(val): return f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') + "x"
def fmt_mes(val): return f"{val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
def fmt_valor_milhoes(val):
    if val >= 1e9: return f"R$ {val/1e9:.1f}B".replace('.', ',')
    elif val >= 1e6: return f"R$ {val/1e6:.1f}M".replace('.', ',')
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# Cálculos Estruturais do Snapshot
val_estoque = somar_coluna(df_snapshot, "valor_saldo_atual")
val_critico = somar_coluna(df_snapshot[df_snapshot.get("item_critico", "") == "1-Sim"], "valor_saldo_atual")
val_obsoleto = somar_coluna(df_snapshot[df_snapshot.get("nome_local_estoque", "").astype(str).str.contains("Obsoleto", case=False, na=False)], "valor_saldo_atual")
val_obra = somar_coluna(df_snapshot[df_snapshot.get("nome_local_estoque", "").astype(str).str.contains("obra", case=False, na=False)], "valor_saldo_atual")

val_skus = df_snapshot[(df_snapshot.get("qtde_saldo_atual", 0) > 0) & (df_snapshot.get("codigo_produto", "") != "")]["codigo_produto"].nunique() if not df_snapshot.empty else 0

# Cálculos de Giro (Baseados na evolução total)
giro_mensal, giro_anual, cobertura_meses, cobertura_anos = 0.0, 0.0, 0.0, 0.0
if not df_filtrado.empty:
    df_giro = df_filtrado.copy()
    df_giro['consumo_abs'] = pd.to_numeric(df_giro['valor_saida_cons_interno'], errors='coerce').fillna(0.0).abs()
    df_giro['is_critico'] = df_giro.get('item_critico', '') == '1-Sim'
    df_giro['is_obsoleto'] = df_giro.get('nome_local_estoque', '').astype(str).str.contains('Obsoleto', case=False, na=False)
    
    monthly_df = df_giro.groupby(['ano_referencia', 'mes_referencia']).apply(lambda g: pd.Series({
        'estoque_op': g.loc[~(g['is_critico'] | g['is_obsoleto']), 'valor_saldo_atual'].sum(),
        'consumo_op': g.loc[~(g['is_critico'] | g['is_obsoleto']), 'consumo_abs'].sum()
    })).reset_index()
    
    if not monthly_df.empty:
        est_medio, cons_medio = monthly_df['estoque_op'].mean(), monthly_df['consumo_op'].mean()
        if est_medio > 0: giro_mensal = cons_medio / est_medio; giro_anual = giro_mensal * 12
        if cons_medio > 0: cobertura_meses = est_medio / cons_medio; cobertura_anos = cobertura_meses / 12

# ==========================================
# 7. DASHBOARD FRONT-END
# ==========================================
aba_geral, aba_detalhada = st.tabs(["📈 Visão Geral", "📊 Análises Detalhadas"])

with aba_geral:
    # --- LINHA FINANCEIRA ---
    st.markdown("<div class='section-title'>💼 LINHA FINANCEIRA</div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-estoque">📦</div><div class="card-title">VALOR TOTAL EM ESTOQUE</div></div><div class="card-value">{fmt_brl(val_estoque)}</div></div>""", unsafe_allow_html=True)
    with c2: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-critico">⚠️</div><div class="card-title">ESTOQUE CRÍTICO (1-SIM)</div></div><div class="card-value">{fmt_brl(val_critico)}</div></div>""", unsafe_allow_html=True)
    with c3: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-obsoleto">🗑️</div><div class="card-title">ESTOQUE OBSOLETO</div></div><div class="card-value">{fmt_brl(val_obsoleto)}</div></div>""", unsafe_allow_html=True)
    with c4: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-obra">🏗️</div><div class="card-title">ESTOQUE OBRA</div></div><div class="card-value">{fmt_brl(val_obra)}</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- LINHA OPERACIONAL ---
    st.markdown("<div class='section-title'>⚙️ LINHA OPERACIONAL</div>", unsafe_allow_html=True)
    c5, c6, c7 = st.columns(3)
    with c5: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-skus">🏷️</div><div class="card-title">TOTAL DE SKUs ÚNICOS</div></div><div class="card-value">{fmt_int(val_skus)}</div></div>""", unsafe_allow_html=True)
    with c6: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-giro">🔄</div><div class="card-title">GIRO DE ESTOQUE</div></div><div style="display: flex; justify-content: space-around; align-items: center; margin-top: 8px;"><div style="text-align: center; flex: 1;"><span style="font-size: 10px; color: #8c9ba5;">MENSAL</span><br><span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_pct(giro_mensal)}</span></div><div style="height: 35px; width: 1px; background-color: #232b36;"></div><div style="text-align: center; flex: 1;"><span style="font-size: 10px; color: #8c9ba5;">ANUALIZADO</span><br><span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_dec(giro_anual)}</span></div></div></div>""", unsafe_allow_html=True)
    with c7: st.markdown(f"""<div class="card-box"><div class="card-header"><div class="icon-box icon-cobertura">⏳</div><div class="card-title">COBERTURA DE ESTOQUE</div></div><div style="display: flex; justify-content: space-around; align-items: center; margin-top: 8px;"><div style="text-align: center; flex: 1;"><span style="font-size: 10px; color: #8c9ba5;">MENSAL (MESES)</span><br><span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_mes(cobertura_meses)}</span></div><div style="height: 35px; width: 1px; background-color: #232b36;"></div><div style="text-align: center; flex: 1;"><span style="font-size: 10px; color: #8c9ba5;">ANUALIZADO (ANOS)</span><br><span style="font-size: 20px; font-weight: bold; color: #ffffff; font-family: monospace;">{fmt_mes(cobertura_anos)}</span></div></div></div>""", unsafe_allow_html=True)

    # --- GRÁFICO DE TENDÊNCIA COM HIGHLIGHT ---
    st.markdown("<br>", unsafe_allow_html=True)
    if not df_filtrado.empty:
        with st.container(border=True):
            col_tg_title, col_tg_filter = st.columns([3, 2])
            with col_tg_title: st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 5px; border-left: 3px solid #e74c3c; padding-left: 10px;'>📊 TENDÊNCIA: TOTAL VS CRÍTICO VS OBSOLETO VS OBRA</div>", unsafe_allow_html=True)
            with col_tg_filter: filtro_unidade_chart = st.multiselect("Filtrar Unidades no Gráfico:", sorted(df_filtrado["unidade_almoxarifado"].dropna().unique().tolist()), key="local_chart_filter", placeholder="Todas as unidades filtradas")

            df_cb = df_filtrado.copy()
            if filtro_unidade_chart: df_cb = df_cb[df_cb["unidade_almoxarifado"].isin(filtro_unidade_chart)]

            def agg_mes(df_filter, is_critico=False, is_obsoleto=False, is_obra=False):
                d = df_filter.copy()
                if is_critico: d = d[d.get('item_critico', '') == '1-Sim']
                if is_obsoleto: d = d[d.get('nome_local_estoque', '').astype(str).str.contains('Obsoleto', case=False, na=False)]
                if is_obra: d = d[d.get('nome_local_estoque', '').astype(str).str.contains('obra', case=False, na=False)]
                
                res = d.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['valor_saldo_atual'].sum().reset_index()
                res = res.sort_values(['tmp_ano_num', 'tmp_mes_num'])
                res['Periodo'] = res['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + res['ano_referencia'].astype(str)
                res['texto'] = res['valor_saldo_atual'].apply(fmt_valor_milhoes)
                res['hover'] = res['valor_saldo_atual'].apply(fmt_brl)
                return res

            df_t = agg_mes(df_cb)
            df_c = agg_mes(df_cb, is_critico=True)
            df_o = agg_mes(df_cb, is_obsoleto=True)
            df_ob = agg_mes(df_cb, is_obra=True)

            max_y_est = df_t['valor_saldo_atual'].max() if not df_t.empty else 100
            n_pts = len(df_t)

            fig = go.Figure()
            
            # 1. Total (Visível Padrão)
            fig.add_trace(go.Scatter(x=df_t['Periodo'], y=df_t['valor_saldo_atual'], customdata=df_t['hover'], name='Estoque Total', mode='lines+markers+text', text=df_t['texto'], textposition='top center', textfont=dict(color='white', size=11), line=dict(color='#e74c3c', width=3), marker=dict(size=8, color='#e74c3c', line=dict(color='#ffffff', width=2)), fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.08)', hovertemplate='<b>%{x}</b><br>Estoque Total: %{customdata}<extra></extra>'))
            
            # 2. Crítico, Obsoleto, Obra (Visíveis ao clicar na legenda)
            if not df_c.empty: fig.add_trace(go.Scatter(x=df_c['Periodo'], y=df_c['valor_saldo_atual'], customdata=df_c['hover'], name='Estoque Crítico', mode='lines+markers+text', text=df_c['texto'], textposition='bottom center', textfont=dict(color='#f39c12', size=11), line=dict(color='#f39c12', width=2.5, dash='dash'), marker=dict(size=6, color='#f39c12', line=dict(color='#ffffff', width=1)), visible='legendonly', hovertemplate='<b>%{x}</b><br>Crítico: %{customdata}<extra></extra>'))
            if not df_o.empty: fig.add_trace(go.Scatter(x=df_o['Periodo'], y=df_o['valor_saldo_atual'], customdata=df_o['hover'], name='Estoque Obsoleto', mode='lines+markers+text', text=df_o['texto'], textposition='top center', textfont=dict(color='#9b59b6', size=11), line=dict(color='#9b59b6', width=2.5, dash='dot'), marker=dict(size=6, color='#9b59b6', line=dict(color='#ffffff', width=1)), visible='legendonly', hovertemplate='<b>%{x}</b><br>Obsoleto: %{customdata}<extra></extra>'))
            if not df_ob.empty: fig.add_trace(go.Scatter(x=df_ob['Periodo'], y=df_ob['valor_saldo_atual'], customdata=df_ob['hover'], name='Estoque Obra', mode='lines+markers+text', text=df_ob['texto'], textposition='bottom center', textfont=dict(color='#1abc9c', size=11), line=dict(color='#1abc9c', width=2.5, dash='longdash'), marker=dict(size=6, color='#1abc9c', line=dict(color='#ffffff', width=1)), visible='legendonly', hovertemplate='<b>%{x}</b><br>Obra: %{customdata}<extra></extra>'))

            # Renderizar o Efeito Visual de Highlight se um ponto foi clicado
            sel_state = st.session_state.get("tendencia_geral_key", {})
            pontos_clicados = sel_state.get("selection", {}).get("points", []) if isinstance(sel_state, dict) else []
            
            if pontos_clicados:
                x_hl = pontos_clicados[0]["x"]
                y_hl = pontos_clicados[0]["y"]
                fig.add_trace(go.Scatter(
                    x=[x_hl], y=[y_hl], mode='markers', name='Foco Selecionado',
                    marker=dict(size=24, color='rgba(0,0,0,0)', line=dict(color='#f1c40f', width=4)),
                    showlegend=False, hoverinfo='skip'
                ))

            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'),
                margin=dict(l=10, r=10, t=50, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified"
            )
            fig.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, n_pts - 0.2])
            fig.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[-max_y_est * 0.08, max_y_est * 1.3], showticklabels=False)

            # Plota o gráfico permitindo o clique dinâmico para gerar o anel de Highlight (on_select nativo)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False}, on_select="rerun", selection_mode="points", key="tendencia_geral_key")

    # --- GRÁFICOS INFERIORES ---
    st.markdown("<br>", unsafe_allow_html=True)
    if not df_filtrado.empty:
        layout_trans = dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=10, r=10, t=10, b=10))
        col_g1, col_g2 = st.columns([6, 4], gap="large")

        with col_g1:
            with st.container(border=True):
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>📈 EVOLUÇÃO: COMPRAS VS CONSUMO</div>", unsafe_allow_html=True)
                df_evo = df_filtrado.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])[['valor_entrada_compras', 'valor_saida_cons_interno']].sum().reset_index().sort_values(['tmp_ano_num', 'tmp_mes_num'])
                df_evo['Periodo'] = df_evo['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_evo['ano_referencia'].astype(str)
                df_evo['valor_saida_cons_interno'] = df_evo['valor_saida_cons_interno'].abs()

                fig_evo = go.Figure()
                fig_evo.add_trace(go.Scatter(x=df_evo['Periodo'], y=df_evo['valor_entrada_compras'], name='Compras', mode='lines+markers', line=dict(color='#f39c12', width=3)))
                fig_evo.add_trace(go.Scatter(x=df_evo['Periodo'], y=df_evo['valor_saida_cons_interno'], name='Consumo', mode='lines+markers', line=dict(color='#e74c3c', width=3)))
                fig_evo.update_layout(**layout_trans, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1))
                fig_evo.update_xaxes(showgrid=False, zeroline=False)
                fig_evo.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, tickprefix="R$ ")
                st.plotly_chart(fig_evo, use_container_width=True, config={'displayModeBar': False}, key="evo_comp_cons")

        with col_g2:
            with st.container(border=True):
                # Top 10 baseia-se exclusivamente no Snapshot Atual
                st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #d85c27; padding-left: 10px;'>🏆 TOP 10: MAIOR VALOR EM ESTOQUE</div>", unsafe_allow_html=True)
                df_r = df_snapshot.groupby('unidade_almoxarifado')['valor_saldo_atual'].sum().reset_index()
                df_r = df_r[df_r['valor_saldo_atual'] > 0].sort_values('valor_saldo_atual', ascending=True).tail(10)
                df_r['fmt'] = df_r['valor_saldo_atual'].apply(lambda x: f"R$ {x/1e6:.1f}M".replace('.', ','))

                fig_b = px.bar(df_r, x='valor_saldo_atual', y='unidade_almoxarifado', orientation='h', color_discrete_sequence=['#e74c3c'], text='fmt')
                fig_b.update_layout(**layout_trans, hovermode="y unified")
                fig_b.update_traces(textposition='auto', textfont=dict(color='white'))
                fig_b.update_xaxes(title="", showgrid=True, gridcolor='#232b36', tickprefix="R$ ", zeroline=False)
                fig_b.update_yaxes(title="", showgrid=False)
                st.plotly_chart(fig_b, use_container_width=True, config={'displayModeBar': False}, key="top_10_bar")

        # Mix de SKUs
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #ffffff; font-size: 14px; font-weight: bold; margin-bottom: 15px; border-left: 3px solid #e74c3c; padding-left: 10px;'>📦 EVOLUÇÃO DO MIX: TOTAL DE SKUs ATIVOS NO TEMPO</div>", unsafe_allow_html=True)
            df_sku_act = df_filtrado[(df_filtrado["qtde_saldo_atual"] > 0) & (df_filtrado["codigo_produto"] != "")]
            df_sku_t = df_sku_act.groupby(['ano_referencia', 'mes_referencia', 'tmp_ano_num', 'tmp_mes_num'])['codigo_produto'].nunique().reset_index().sort_values(['tmp_ano_num', 'tmp_mes_num'])
            df_sku_t['Periodo'] = df_sku_t['tmp_mes_num'].astype(int).astype(str).str.zfill(2) + '/' + df_sku_t['ano_referencia'].astype(str)

            txt_sku = [f"{v:,}".replace(',', '.') for v in df_sku_t['codigo_produto']]
            val_skus_fmt = f"{val_skus:,}".replace(',', '.') # Utiliza o SKU do snapshot calculado nos cards

            l_sku = dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#8c9ba5'), margin=dict(l=40, r=40, t=50, b=10), annotations=[dict(x=1.0, y=1.12, xref="paper", yref="paper", text=f"<b>Total Mês Atual:</b> {val_skus_fmt}", showarrow=False, font=dict(color="#ffffff", size=12, family="monospace"), bgcolor="#1a222d", bordercolor="#333d4d", borderwidth=1, borderpad=6, align="right")])

            fig_s = go.Figure(go.Scatter(x=df_sku_t['Periodo'], y=df_sku_t['codigo_produto'], customdata=txt_sku, name='SKUs Ativos', mode='lines+markers+text', text=txt_sku, textposition='top center', textfont=dict(color='white', size=11), line=dict(color='#e74c3c', width=3), fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.1)', hovertemplate='<b>%{x}</b><br>SKUs Ativos: %{customdata}<extra></extra>'))
            fig_s.update_layout(**l_sku, hovermode="x unified", showlegend=False)
            fig_s.update_xaxes(showgrid=False, zeroline=False, range=[-0.8, len(df_sku_t) - 0.2])
            fig_s.update_yaxes(showgrid=True, gridcolor='#232b36', zeroline=False, range=[0, df_sku_t['codigo_produto'].max() * 1.15 if not df_sku_t.empty else 100], showticklabels=False)
            st.plotly_chart(fig_s, use_container_width=True, config={'displayModeBar': False}, key="skus_evo")

with aba_detalhada:
    if not df_snapshot.empty:
        st.markdown("<div style='color: #ffffff; font-size: 16px; font-weight: bold; margin-bottom: 15px;'>📋 CONSOLIDAÇÃO ANALÍTICA POR UNIDADE DE ALMOXARIFADO (POSIÇÃO MÊS ATUAL)</div>", unsafe_allow_html=True)
        
        df_tab = df_snapshot.groupby('unidade_almoxarifado').agg(
            Valor_Estoque=('valor_saldo_atual', 'sum'), Valor_Compras=('valor_entrada_compras', 'sum'),
            Valor_Consumo=('valor_saida_cons_interno', lambda x: x.abs().sum()),
            SKUs_Ativos=('codigo_produto', lambda x: x[df_snapshot.loc[x.index, 'qtde_saldo_atual'] > 0].nunique())
        ).reset_index().sort_values(by='Valor_Estoque', ascending=False)

        df_ex = pd.DataFrame({
            'Unidade de Almoxarifado': df_tab['unidade_almoxarifado'],
            'Valor em Estoque': df_tab['Valor_Estoque'].apply(fmt_brl),
            'Valor de Compras': df_tab['Valor_Compras'].apply(fmt_brl),
            'Valor de Consumo': df_tab['Valor_Consumo'].apply(fmt_brl),
            'SKUs Ativos': df_tab['SKUs_Ativos'].apply(fmt_int)
        })

        st.dataframe(df_ex, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum dado encontrado para os filtros selecionados.")
