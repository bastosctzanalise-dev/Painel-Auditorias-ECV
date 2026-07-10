import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import io
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- Configuração Inicial do Streamlit ---
st.set_page_config(page_title="Painel de Auditorias ECV", page_icon="🚗", layout="wide")
st.title("Painel de Auditorias ECV 🚗")

# ✅ IDs reais das suas pastas limpos e extraídos dos seus links
PASTAS_DRIVE = {
    "STARCHECK": "1_m65QEty9gt8guRIxLz78UppAD07fSel",
    "VELOX": "1VU-7ny4JOI3oFyuB8TBu6ecwLCQt6cim",
    "TOKYO": "1UbMlKP67fkk7D3aiZ_wWTESAf32VdA",
    "LOG": "1ItAdYVhnl-IqIbEAD0AhVlWEm6Zt8-FP"
}

# --- Conexão Segura e Inteligente via OAuth / Nuvem ---
import json
from google.oauth2 import service_account

def obter_servico_drive():
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = None
    
    # 1º Tenta ler as credenciais secretas do Streamlit Cloud (Internet)
    if "google_credentials" in st.secrets:
        try:
            info_credenciais = json.loads(st.secrets["google_credentials"]["content"])
            creds = service_account.Credentials.from_service_account_info(info_credenciais, scopes=SCOPES)
        except Exception as e:
            st.error(f"❌ Erro nas credenciais secrets do Streamlit Cloud: {e}")
            
    # 2º Se não estiver na nuvem (rodando em localhost), usa o método com navegador local
    if not creds:
        if os.path.exists('token.json'):
            creds = UserCredentials.from_authorized_user_file('token.json', SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                if not os.path.exists('client_sercrets.json'):
                    st.error("❌ Arquivo 'client_sercrets.json' não foi encontrado na pasta do projeto!")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file('client_sercrets.json', SCOPES)
                creds = flow.run_local_server(port=0)
                
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
    try:
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Google Drive: {e}")
        return None

# --- Varre as pastas e junta todas as planilhas de todos os meses ---
@st.cache_data(ttl=60)
def carregar_dados_das_pastas():
    todos_df = []
    colunas_obrigatorias = ['DATA', 'ANALISTA', 'CATEGORIA', 'STATUS', 'PLACA', 'LAUDOS AUD.C/ ERROS', 'QTD DE ERROS']
    
    drive_service = obter_servico_drive()
    if drive_service is None:
        return pd.DataFrame()

    barra_progresso = st.progress(0)
    status_texto = st.empty()
    
    for i, (empresa, folder_id) in enumerate(PASTAS_DRIVE.items()):
        status_texto.text(f"🔄 Buscando planilhas da {empresa}...")
        try:
            # Busca arquivos Excel (.xlsx ou .csv) dentro da pasta específica
            query = f"'{folder_id}' in parents and trashed = false and (mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or mimeType = 'text/csv')"
            resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute()
            arquivos = resultados.get('files', [])

            for arquivo in arquivos:
                file_id = arquivo['id']
                mime_type = arquivo['mimeType']
                
                # Baixa o arquivo direto para a memória
                requisicao = drive_service.files().get_media(fileId=file_id)
                conteudo_arquivo = requisicao.execute()
                
                # Leitura dinâmica baseada no formato do arquivo
                if 'csv' in mime_type:
                    df = pd.read_csv(io.BytesIO(conteudo_arquivo))
                else:
                    df = pd.read_excel(io.BytesIO(conteudo_arquivo), sheet_name=0)
                
                # Padroniza os nomes das colunas para letras maiúsculas
                df.columns = df.columns.str.strip().str.upper()
                
                # Garante que as colunas obrigatórias existam
                for col in colunas_obrigatorias:
                    if col not in df.columns:
                        df[col] = None
                        
                df['EMPRESA'] = empresa
                df['ARQUIVO_ORIGEM'] = arquivo['name']  # Guarda o nome do arquivo (ex: Janeiro.xlsx)
                todos_df.append(df[colunas_obrigatorias + ['EMPRESA', 'ARQUIVO_ORIGEM']])
                
        except Exception as e:
            st.warning(f"⚠️ Não foi possível ler a pasta da {empresa}. Erro: {e}")
            continue
            
        barra_progresso.progress((i + 1) / len(PASTAS_DRIVE))
        
    status_texto.empty()
    barra_progresso.empty()
            
    if todos_df:
        df_final = pd.concat(todos_df, ignore_index=True)
        
        # Tratamento inteligente de datas para o calendário
        df_final['DATA_CONVERTIDA'] = pd.to_datetime(df_final['DATA'], errors='coerce')
        df_final['ANO_MES'] = df_final['DATA_CONVERTIDA'].dt.strftime('%Y-%m')
        
        meses_pt = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
            7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }
        
        def formatar_mes_ano(row):
            if pd.notna(row['DATA_CONVERTIDA']):
                mes_nome = meses_pt.get(row['DATA_CONVERTIDA'].month, "")
                ano = row['DATA_CONVERTIDA'].year
                return f"{mes_nome}/{ano}"
            return "Sem Data"
            
        df_final['MES_ANO_TEXTO'] = df_final.apply(formatar_mes_ano, axis=1)
        return df_final
        
    return pd.DataFrame()

# --- Interface Visual ---
intervalo_auto = st.sidebar.selectbox("Atualização automática (segundos)", [10, 30, 60])

df_completo = carregar_dados_das_pastas()
st.sidebar.markdown(f"**🕒 Atualizado em:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

if df_completo.empty:
    st.info("👋 Aguardando a autenticação ou nenhuma planilha válida foi encontrada nas pastas.")
else:
    # --- FILTROS LATERAIS ---
    st.sidebar.header("🔍 Filtros de Auditoria")
    
    meses_disponiveis = ["TODOS OS MESES"]
    df_validos = df_completo[df_completo['MES_ANO_TEXTO'] != "Sem Data"]
    if not df_validos.empty:
        df_ordenado = df_validos.sort_values('ANO_MES', ascending=False)
        meses_disponiveis += list(df_ordenado['MES_ANO_TEXTO'].unique())
        
    mes_selecionado = st.sidebar.selectbox("Selecione o Mês/Ano:", meses_disponiveis)
    df_filtrado_tempo = df_completo[df_completo['MES_ANO_TEXTO'] == mes_selecionado].copy() if mes_selecionado != "TODOS OS MESES" else df_completo.copy()

    empresa_selecionada = st.sidebar.selectbox("Selecione a Empresa", ["TODAS"] + list(PASTAS_DRIVE.keys()))
    df_filtrado = df_filtrado_tempo[df_filtrado_tempo['EMPRESA'] == empresa_selecionada].copy() if empresa_selecionada != "TODAS" else df_filtrado_tempo.copy()

    # Filtros Dinâmicos (Analista, Categoria)
    analistas_validos = df_filtrado['ANALISTA'].dropna().unique()
    analistas = ["TODOS"] + sorted(list(analistas_validos)) if len(analistas_validos) > 0 else ["TODOS"]
    analista_sel = st.sidebar.selectbox("Filtrar por Analista", analistas)
    if analista_sel != "TODOS": 
        df_filtrado = df_filtrado[df_filtrado['ANALISTA'] == analista_sel]

    categorias_validas = df_filtrado['CATEGORIA'].dropna().unique()
    categorias = ["TODAS"] + sorted(list(categorias_validas)) if len(categorias_validas) > 0 else ["TODAS"]
    categoria_sel = st.sidebar.selectbox("Filtrar por Categoria", categorias)
    if categoria_sel != "TODAS": 
        df_filtrado = df_filtrado[df_filtrado['CATEGORIA'] == categoria_sel]

    # --- KPIs Indicadores ---
    st.markdown(f"### 📈 Indicadores — `Mês: {mes_selecionado}` | `Empresa: {empresa_selecionada}`")
    total_auditorias = len(df_filtrado)
    col_laudos = df_filtrado['LAUDOS AUD.C/ ERROS'].fillna('').astype(str).str.upper()
    aprovadas = col_laudos[col_laudos.str.contains('APROVADO', na=False)].shape[0]
    nao_conforme = total_auditorias - aprovadas
    total_erros = int(pd.to_numeric(df_filtrado['QTD DE ERROS'], errors='coerce').fillna(0).sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de Vistorias", total_auditorias)
    col2.metric("Aprovadas", aprovadas)
    col3.metric("Não Conformes", nao_conforme)
    col4.metric("Qtd Total de Erros", total_erros)

    st.markdown("---")

    # --- ABAS INTERATIVAS ---
    tab_graficos, tab_consolidado, tab_tabela = st.tabs(["📊 Visão Gráfica Interativa", "🏢 Resumo Consolidado", "📋 Base de Dados Completa"])

    with tab_graficos:
        df_grafico = df_filtrado.dropna(subset=['CATEGORIA'])
        if not df_grafico.empty:
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                df_count = df_grafico['CATEGORIA'].value_counts().reset_index(name='Quantidade')
                df_count.columns = ['Categoria','Quantidade']
                st.plotly_chart(px.bar(df_count, x='Categoria', y='Quantidade', color='Categoria', text_auto=True, title="Quantidade por Categoria"), use_container_width=True)
            with col_g2:
                st.plotly_chart(px.pie(df_count, names='Categoria', values='Quantidade', hole=0.4, title="Proporção por Categoria"), use_container_width=True)

    with tab_consolidado:
        df_consolidado = df_filtrado_tempo.dropna(subset=['CATEGORIA'])
        if not df_consolidado.empty:
            resumo_geral = df_consolidado.groupby(["EMPRESA","CATEGORIA"]).size().reset_index(name='Quantidade')
            st.plotly_chart(px.bar(resumo_geral, x='EMPRESA', y='Quantidade', color='CATEGORIA', barmode='group', text_auto=True, title="Comparativo entre Empresas"), use_container_width=True)

    with tab_tabela:
        st.subheader("📋 Dados Consolidados (Mostrando o arquivo de origem)")
        st.dataframe(df_filtrado, use_container_width=True)

# Loop de recarregamento do Streamlit
time.sleep(intervalo_auto)
st.rerun()