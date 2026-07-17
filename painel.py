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

# ✅ IDs reais das suas pastas
PASTAS_DRIVE = {
    "STARCHECK": "1_m65QEty9gt8guRIxLz78UppADO7fSel",
    "VELOX": "1VU-7ny4JOI3oFyuB8TBu6ecwLCQt6cim",
    "TOKYO": "1UbMlKP67fkK7D3aiZ9_w9WTESAf32VdA",
    "LOG": "1ItAdYVhnl-IqIbEAD0AhVlWEm6Zt8-FP"
}

# --- Conexão Segura e Inteligente via OAuth / Nuvem ---
import json
from google.oauth2 import service_account

def obter_servico_drive():
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = None
    
    if "google_credentials" in st.secrets:
        try:
            info_credenciais = json.loads(st.secrets["google_credentials"]["content"])
            creds = service_account.Credentials.from_service_account_info(info_credenciais, scopes=SCOPES)
        except Exception as e:
            st.error(f"❌ Erro nas credenciais secrets do Streamlit Cloud: {e}")
            
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

# --- Varre as pastas e junta todas as planilhas ---
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
            query = f"'{folder_id}' in parents and trashed = false and (mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or mimeType = 'text/csv')"
            resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute()
            arquivos = resultados.get('files', [])

            for arquivo in arquivos:
                file_id = arquivo['id']
                mime_type = arquivo['mimeType']
                
                requisicao = drive_service.files().get_media(fileId=file_id)
                conteudo_arquivo = requisicao.execute()
                
                if 'csv' in mime_type:
                    df = pd.read_csv(io.BytesIO(conteudo_arquivo))
                else:
                    df = pd.read_excel(io.BytesIO(conteudo_arquivo), sheet_name=0)
                
                df.columns = df.columns.str.strip().str.upper()
                
                for col in colunas_obrigatorias:
                    if col not in df.columns:
                        df[col] = None
                        
                df['EMPRESA'] = empresa
                df['ARQUIVO_ORIGEM'] = arquivo['name']
                todos_df.append(df[colunas_obrigatorias + ['EMPRESA', 'ARQUIVO_ORIGEM']])
                
        except Exception as e:
            st.warning(f"⚠️ Não foi possível ler a pasta da {empresa}. Erro: {e}")
            continue
            
        barra_progresso.progress((i + 1) / len(PASTAS_DRIVE))
        
    status_texto.empty()
    barra_progresso.empty()
            
    if todos_df:
        df_final = pd.concat(todos_df, ignore_index=True)
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
        
        # Padroniza a coluna LAUDOS AUD.C/ ERROS
        if 'LAUDOS AUD.C/ ERROS' in df_final.columns:
            df_final['LAUDOS AUD.C/ ERROS'] = df_final['LAUDOS AUD.C/ ERROS'].astype(str).str.strip().str.upper()

        # Padroniza a coluna STATUS para evitar problemas de maiúscula/minúscula ou espaços
        if 'STATUS' in df_final.columns:
            df_final['STATUS'] = df_final['STATUS'].astype(str).str.strip().str.upper()
            df_final['STATUS'] = df_final['STATUS'].replace({'NAN': 'NÃO PREENCHIDO', '': 'NÃO PREENCHIDO'})
            
        return df_final
        
    return pd.DataFrame()

# --- Interface Visual ---
intervalo_auto = st.sidebar.selectbox("Atualização automática", ["Desativado", "30 segundos", "60 segundos"], index=0)

df_completo = carregar_dados_das_pastas()
st.sidebar.markdown(f"**🕒 Atualizado em:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

if df_completo.empty:
    st.info("👋 Aguardando a autenticação ou nenhuma planilha válida foi encontrada nas pastas.")
else:
    # --- FILTROS LATERAIS ---
    st.sidebar.header("🔍 Filtros de Auditoria")
    
    meses_disponiveis = ["TODOS OS MESES"]
    if 'MES_ANO_TEXTO' in df_completo.columns:
        df_validos = df_completo[(df_completo['MES_ANO_TEXTO'] != "Sem Data") & (df_completo['ANO_MES'].notna())]
        if not df_validos.empty:
            df_ordenado = df_validos.sort_values('ANO_MES', ascending=False)
            meses_disponiveis += list(df_ordenado['MES_ANO_TEXTO'].unique())
        
    mes_selecionado = st.sidebar.selectbox("Selecione o Mês/Ano:", meses_disponiveis)
    df_filtrado_tempo = df_completo[df_completo['MES_ANO_TEXTO'] == mes_selecionado].copy() if mes_selecionado != "TODOS OS MESES" else df_completo.copy()

    empresa_selecionada = st.sidebar.selectbox("Selecione a Empresa", ["TODAS"] + list(PASTAS_DRIVE.keys()))
    df_filtrado = df_filtrado_tempo[df_filtrado_tempo['EMPRESA'] == empresa_selecionada].copy() if empresa_selecionada != "TODAS" else df_filtrado_tempo.copy()

    # 🤝 RETORNADO: Filtro por Analista
    analistas_validos = df_filtrado['ANALISTA'].dropna().unique() if not df_filtrado.empty else []
    analistas = ["TODOS"] + sorted(list(analistas_validos)) if len(analistas_validos) > 0 else ["TODOS"]
    analista_sel = st.sidebar.selectbox("Filtrar por Analista", analistas)
    if analista_sel != "TODOS" and not df_filtrado.empty: 
        df_filtrado = df_filtrado[df_filtrado['ANALISTA'] == analista_sel]

    # FILTRO DE PARECER (STATUS DA COLUNA H)
    status_validos = df_filtrado['STATUS'].unique() if not df_filtrado.empty else []
    lista_status = ["TODOS OS PARECERES"] + sorted([str(s) for s in status_validos if s != 'NÃO PREENCHIDO'])
    if 'NÃO PREENCHIDO' in status_validos:
        lista_status.append('NÃO PREENCHIDO')
        
    status_sel = st.sidebar.selectbox("Filtrar por Parecer (Status Coluna H)", lista_status)
    if status_sel != "TODOS OS PARECERES" and not df_filtrado.empty:
        df_filtrado = df_filtrado[df_filtrado['STATUS'] == status_sel]

    # Filtro por Categoria
    categorias_validas = df_filtrado['CATEGORIA'].dropna().unique() if not df_filtrado.empty else []
    categorias = ["TODAS"] + sorted(list(categorias_validas)) if len(categorias_validas) > 0 else ["TODAS"]
    categoria_sel = st.sidebar.selectbox("Filtrar por Categoria", categorias)
    if categoria_sel != "TODAS" and not df_filtrado.empty: 
        df_filtrado = df_filtrado[df_filtrado['CATEGORIA'] == categoria_sel]

    # --- 🛡️ PROTEÇÃO CONTRA FILTROS VAZIOS ---
    if df_filtrado.empty:
        st.markdown(f"### 📈 Indicadores — `Mês: {mes_selecionado}` | `Empresa: {empresa_selecionada}`")
        st.warning(f"ℹ️ Não existem dados ou vistorias registradas para os filtros selecionados.")
        
        tab_graficos, tab_consolidado, tab_tabela = st.tabs(["📊 Visão Gráfica Interativa", "🏢 Resumo Consolidado", "📋 Base de Dados Completa"])
        with tab_graficos: st.info("ℹ️ Sem gráficos para este filtro.")
        with tab_consolidado: st.info("ℹ️ Sem comparativos para este filtro.")
        with tab_tabela: st.dataframe(df_filtrado, use_container_width=True)
            
    else:
        # --- KPIs Indicadores Corrigidos ---
        st.markdown(f"### 📈 Indicadores — `Mês: {mes_selecionado}` | `Empresa: {empresa_selecionada}`")
        
        total_vistorias = len(df_filtrado)
        
        # 🟢 CONTAGEM DA COLUNA D: Filtra quem está escrito 'APROVADO' na coluna D
        qtd_aprovados_col_d = df_filtrado[df_filtrado['LAUDOS AUD.C/ ERROS'] == 'APROVADO'].shape[0]
        
        # 🔴 CONTROLE DA COLUNA H: Filtra os status específicos preenchidos
        qtd_reprovados = df_filtrado[df_filtrado['STATUS'] == 'REPROVADO'].shape[0]
        qtd_apontamentos = df_filtrado[df_filtrado['STATUS'].str.contains('APONTAM', na=False)].shape[0]
        
        qtd_total_erros = int(pd.to_numeric(df_filtrado['QTD DE ERROS'], errors='coerce').fillna(0).sum())

        # Exibição organizada dos blocos de métricas
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Analisado", total_vistorias)
        col2.metric("✅ Aprovados (Coluna D)", qtd_aprovados_col_d)
        col3.metric("❌ Reprovados (Coluna H)", qtd_reprovados)
        col4.metric("⚠️ Com Apontamentos", qtd_apontamentos)
        col5.metric("💥 Total de Erros", qtd_total_erros)

        st.markdown("---")

        # --- ABAS INTERATIVAS ---
        tab_graficos, tab_consolidado, tab_tabela = st.tabs(["📊 Visão Gráfica Interativa", "🏢 Resumo Consolidado", "📋 Base de Dados Completa"])

        with tab_graficos:
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                df_status_count = df_filtrado['STATUS'].value_counts().reset_index()
                df_status_count.columns = ['Parecer (Status)', 'Quantidade']
                st.plotly_chart(px.bar(df_status_count, x='Parecer (Status)', y='Quantidade', color='Parecer (Status)', text_auto=True, title="Quantidade por Parecer Final"), use_container_width=True)
            with col_g2:
                df_cat_df = df_filtrado.dropna(subset=['CATEGORIA'])
                if not df_cat_df.empty:
                    df_count = df_cat_df['CATEGORIA'].value_counts().reset_index()
                    df_count.columns = ['Categoria','Quantidade']
                    st.plotly_chart(px.pie(df_count, names='Categoria', values='Quantidade', hole=0.4, title="Proporção por Categoria do Veículo"), use_container_width=True)

        with tab_consolidado:
            df_consolidado = df_filtrado_tempo.dropna(subset=['STATUS'])
            if not df_consolidado.empty:
                resumo_geral = df_consolidado.groupby(["EMPRESA","STATUS"]).size().reset_index(name='Quantidade')
                st.plotly_chart(px.bar(resumo_geral, x='EMPRESA', y='Quantidade', color='STATUS', barmode='group', text_auto=True, title="Comparativo de Pareceres por Empresa"), use_container_width=True)
            else:
                st.info("ℹ️ Não existem dados suficientes para gerar o comparativo.")

        with tab_tabela:
            st.subheader(f"📋 Registros Filtrados — Analista: {analista_sel} | Parecer: {status_sel}")
            st.dataframe(df_filtrado, use_container_width=True)

# Loop de recarregamento
if intervalo_auto != "Desativado":
    tempo_segundos = 30 if "30" in intervalo_auto else 60
    time.sleep(tempo_segundos)
    st.rerun()
         
