import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import time

# --- Configuração Inicial ---
st.set_page_config(page_title="Painel de Auditorias ECV", page_icon="🚗", layout="wide")
st.title("Painel de Auditorias ECV 🚗")

# --- Autenticação PyDrive ---
gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)

# --- IDs das pastas por empresa ---
pastas_empresas = {
    "VELOX": "1VU-7ny4JOI3oFyuB8TBu6ecwLCQt6cim",
    "STARCHECK": "1UbMlKP67fkK7D3aiZ9_w9WTESAf32VdA",
    "TOKYO": "1ItAdYVhnl-IqIbEAD0AhVlWEm6Zt8-FP",
    "LOG": "1_m65QEty9gt8guRIxLz78UppADO7fSel"
}

# --- Lista planilhas na pasta ---
def listar_planilhas(pasta_id):
    file_list = drive.ListFile({'q': f"'{pasta_id}' in parents and trashed=false"}).GetList()
    return [f"https://drive.google.com/uc?id={f['id']}&export=download" for f in file_list if f['title'].endswith('.xlsx')]

# --- Carrega todas planilhas automaticamente ---
@st.cache_data(ttl=5)
def carregar_dados_automatico():
    todos_df = []
    for empresa, pasta_id in pastas_empresas.items():
        links = listar_planilhas(pasta_id)
        for link in links:
            try:
                df = pd.read_excel(link)
                df.columns = df.columns.str.strip().str.upper()
                df['EMPRESA'] = empresa
                todos_df.append(df)
            except:
                continue
    if todos_df:
        df_final = pd.concat(todos_df, ignore_index=True)
        if 'DATA' in df_final.columns:
            df_final['DATA_CONVERTIDA'] = pd.to_datetime(df_final['DATA'], errors='coerce')
        return df_final
    return pd.DataFrame()

# --- Atualização automática ---
intervalo_auto = st.sidebar.selectbox("Atualização automática (segundos)", [5, 10, 30, 60])

def recarregar():
    time.sleep(intervalo_auto)
    st.experimental_rerun()

df_completo = carregar_dados_automatico()

# --- Barra lateral ---
st.sidebar.markdown(f"**🕒 Atualizado em:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

# --- Filtros ---
empresa_selecionada = st.sidebar.selectbox("Selecione a Empresa", ["TODAS"] + list(pastas_empresas.keys()))
df_filtrado = df_completo.copy()
if empresa_selecionada != "TODAS":
    df_filtrado = df_filtrado[df_filtrado['EMPRESA'] == empresa_selecionada]

# Calendário
if 'DATA_CONVERTIDA' in df_filtrado.columns:
    data_min = df_filtrado['DATA_CONVERTIDA'].min()
    data_max = df_filtrado['DATA_CONVERTIDA'].max()
    periodo = st.sidebar.date_input("Período da Auditoria", [data_min, data_max])
    df_filtrado = df_filtrado[(df_filtrado['DATA_CONVERTIDA'] >= pd.to_datetime(periodo[0])) &
                              (df_filtrado['DATA_CONVERTIDA'] <= pd.to_datetime(periodo[1]))]

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
    placa_input = st.sidebar.text_input("Buscar Placa").upper()
    if placa_input:
        df_filtrado = df_filtrado[df_filtrado['PLACA'].astype(str).str.upper().str.contains(placa_input, na=False)]

# --- KPIs ---
total_auditorias = len(df_filtrado)
aprovadas = df_filtrado[df_filtrado['LAUDOS AUD.C/ ERROS'].astype(str).str.upper().str.contains('APROVADO', na=False)].shape[0] if 'LAUDOS AUD.C/ ERROS' in df_filtrado.columns else 0
nao_conforme = total_auditorias - aprovadas
total_erros = int(pd.to_numeric(df_filtrado['QTD DE ERROS'], errors='coerce').fillna(0).sum()) if 'QTD DE ERROS' in df_filtrado.columns else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de Vistorias", total_auditorias)
col2.metric("Aprovadas", aprovadas)
col3.metric("Não Conformes", nao_conforme)
col4.metric("Qtd Total de Erros", total_erros)

st.markdown("---")

# --- Gráficos ---
if 'CATEGORIA' in df_filtrado.columns and not df_filtrado.empty:
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        df_count = df_filtrado['CATEGORIA'].value_counts().reset_index(name='Quantidade')
        df_count.columns = ['Categoria','Quantidade']
        fig_bar = px.bar(df_count, x='Categoria', y='Quantidade', color='Categoria', text_auto=True)
        st.plotly_chart(fig_bar, use_container_width=True)
    with col_g2:
        fig_pie = px.pie(df_count, names='Categoria', values='Quantidade', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

# --- Resumo Consolidado ---
if 'CATEGORIA' in df_completo.columns and not df_completo.empty:
    resumo_geral = df_completo.groupby(["EMPRESA","CATEGORIA"]).size().reset_index(name='Quantidade')
    fig_consolidado = px.bar(resumo_geral, x='EMPRESA', y='Quantidade', color='CATEGORIA', barmode='group', text_auto=True)
    st.subheader("📈 Resumo Consolidado Inter-Empresas")
    st.plotly_chart(fig_consolidado, use_container_width=True)

# --- Atualização automática ---
recarregar()