import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# Auto refresh
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Painel de Auditorias ECV", page_icon="🚗", layout="wide")
st.title("Painel de Auditorias ECV 🚗")

# --- Intervalos de atualização automática ---
intervalo_selecionado = st.sidebar.selectbox(
    "⏱️ Atualização automática:",
    ["Desativada", "5 segundos", "10 segundos", "30 segundos", "60 segundos"]
)

# Mapear para milissegundos
intervalos = {
    "Desativada": 0,
    "5 segundos": 5000,
    "10 segundos": 10000,
    "30 segundos": 30000,
    "60 segundos": 60000
}

ms_interval = intervalos[intervalo_selecionado]
if ms_interval > 0:
    st_autorefresh(interval=ms_interval, key="refresh")

# --- Pastas ou planilhas das empresas ---
planilhas = {
    "STARCHECK": "https://docs.google.com/spreadsheets/d/1BIGV5pZxScW-Zx4swzNUzhf_6kAxOkd20iUxhbJ_khk/export?format=xlsx",
    "VELOX": "https://docs.google.com/spreadsheets/d/1xiMTFW3x5Sj-SLXUWiNO2kjo-eXT1HRlNvh-p8RQYyY/export?format=xlsx",
    "TOKYO": "https://docs.google.com/spreadsheets/d/1Fbl_yGGU2ivt9Sg6mDuBR-gMdHVix_gHIZMy0FBpW2s/export?format=xlsx",
    "LOG": "https://docs.google.com/spreadsheets/d/1HNiUmhUn3rijc1AFhSvxIqeLVMMMRISd16lzRNcMA4A/export?format=xlsx"
}

@st.cache_data(ttl=60)
def carregar_dados(planilhas):
    todos_df = []
    for empresa, url in planilhas.items():
        try:
            df = pd.read_excel(url)
            df.columns = df.columns.str.strip().str.upper()
            df['EMPRESA'] = empresa
            if 'DATA' in df.columns:
                df['DATA_CONVERTIDA'] = pd.to_datetime(df['DATA'], errors='coerce')
            todos_df.append(df)
        except Exception as e:
            st.error(f"Erro ao carregar {empresa}: {e}")
    if todos_df:
        return pd.concat(todos_df, ignore_index=True)
    return pd.DataFrame()

# Carregar dados
df_completo = carregar_dados(planilhas)

# Exibir última atualização
st.sidebar.markdown(f"**🕒 Última atualização:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

if df_completo.empty:
    st.warning("⚠️ Nenhum dado carregado.")
else:
    # Filtros
    st.sidebar.header("🔍 Filtros de Auditoria")
    
    # Calendário
    if 'DATA_CONVERTIDA' in df_completo.columns:
        min_data = df_completo['DATA_CONVERTIDA'].min()
        max_data = df_completo['DATA_CONVERTIDA'].max()
        periodo = st.sidebar.date_input("Período da Auditoria", [min_data, max_data])
        df_filtrado = df_completo[
            (df_completo['DATA_CONVERTIDA'] >= pd.to_datetime(periodo[0])) &
            (df_completo['DATA_CONVERTIDA'] <= pd.to_datetime(periodo[1]))
        ]
    else:
        df_filtrado = df_completo.copy()

    # Empresa
    empresa_selecionada = st.sidebar.selectbox("Empresa", ["TODAS"] + list(planilhas.keys()))
    if empresa_selecionada != "TODAS":
        df_filtrado = df_filtrado[df_filtrado['EMPRESA'] == empresa_selecionada]

    # Analista
    if 'ANALISTA' in df_filtrado.columns:
        analistas = ["TODOS"] + sorted(df_filtrado['ANALISTA'].dropna().unique())
        analista_sel = st.sidebar.selectbox("Filtrar por Analista", analistas)
        if analista_sel != "TODOS":
            df_filtrado = df_filtrado[df_filtrado['ANALISTA'] == analista_sel]

    # Categoria
    if 'CATEGORIA' in df_filtrado.columns:
        categorias = ["TODAS"] + sorted(df_filtrado['CATEGORIA'].dropna().unique())
        categoria_sel = st.sidebar.selectbox("Filtrar por Categoria", categorias)
        if categoria_sel != "TODAS":
            df_filtrado = df_filtrado[df_filtrado['CATEGORIA'] == categoria_sel]

    # Status
    if 'STATUS' in df_filtrado.columns:
        status = ["TODOS"] + sorted(df_filtrado['STATUS'].dropna().unique())
        status_sel = st.sidebar.selectbox("Filtrar por Status", status)
        if status_sel != "TODOS":
            df_filtrado = df_filtrado[df_filtrado['STATUS'] == status_sel]

    # Placa
    if 'PLACA' in df_filtrado.columns:
        busca = st.sidebar.text_input("Buscar Placa:").strip().upper()
        if busca:
            df_filtrado = df_filtrado[df_filtrado['PLACA'].astype(str).str.upper().str.contains(busca, na=False)]

    # KPIs
    total = len(df_filtrado)
    if 'LAUDOS AUD.C/ ERROS' in df_filtrado.columns:
        aprovadas = df_filtrado[df_filtrado['LAUDOS AUD.C/ ERROS'].astype(str).str.upper().str.contains('APROVADO', na=False)].shape[0]
        nao_conforme = total - aprovadas
    else:
        aprovadas = total
        nao_conforme = 0

    total_erros = int(df_filtrado['QTD DE ERROS'].fillna(0).sum()) if 'QTD DE ERROS' in df_filtrado.columns else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Vistorias", total)
    col2.metric("Aprovadas Absoluto", aprovadas)
    col3.metric("Não Conformes (Erros)", nao_conforme)
    col4.metric("Qtd Total de Erros", total_erros)

    st.markdown("---")
    
    # Gráficos categoria
    if 'CATEGORIA' in df_filtrado.columns and not df_filtrado.empty:
        df_cat_count = df_filtrado['CATEGORIA'].value_counts().reset_index()
        df_cat_count.columns = ['Categoria', 'Quantidade']
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_bar = px.bar(df_cat_count, x='Categoria', y='Quantidade', text_auto=True,
                             title="Volumetria por Categoria", color='Categoria')
            st.plotly_chart(fig_bar, use_container_width=True)
        with col_g2:
            fig_pie = px.pie(df_cat_count, names='Categoria', values='Quantidade', hole=0.4,
                             title="Proporção de Ocorrências")
            st.plotly_chart(fig_pie, use_container_width=True)

    # Resumo consolidado
    if 'CATEGORIA' in df_filtrado.columns and not df_filtrado.empty:
        resumo_geral = df_filtrado.groupby(['EMPRESA','CATEGORIA']).size().reset_index(name='Quantidade')
        fig_consolidado = px.bar(resumo_geral, x='EMPRESA', y='Quantidade', color='CATEGORIA',
                                 barmode='group', text_auto=True, title="Resumo Consolidado")
        st.plotly_chart(fig_consolidado, use_container_width=True)
        tabela_pivot = df_filtrado.groupby(['EMPRESA','CATEGORIA']).size().unstack(fill_value=0)
        st.dataframe(tabela_pivot, use_container_width=True)

    # Tabela completa
    st.subheader("📋 Base de Dados Completa")
    st.dataframe(df_filtrado, use_container_width=True)