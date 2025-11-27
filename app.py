import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from datetime import datetime

# --- 1. CONFIGURAÇÃO DE UI (PROFISSIONAL) ---
st.set_page_config(
    page_title="Extrator de Códigos de Barras",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS para dar acabamento corporativo
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        border: 1px solid #e9ecef;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
        height: 3.5em;
    }
    /* Destaque para o botão de download */
    div[data-testid="stDownloadButton"] > button {
        background-color: #2e7d32;
        color: white;
        border: none;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #1b5e20;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. LÓGICA DE EXTRAÇÃO (MOTOR V3.2 - MULTI-PATTERN) ---

def extrair_texto_pdf(file):
    """Extrai texto mantendo layout visual"""
    texto_completo = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""
    return texto_completo

def limpar_string_numerica(s):
    if not s: return None
    return re.sub(r'[^0-9]', '', s)

def buscar_padroes(texto):
    """Motor de extração: Suporte a múltiplos formatos de boletos bancários."""
    dados = {
        "Beneficiario_Pagador_Doc": None,
        "Data_Vencimento": None,
        "Valor": 0.0,
        "Codigo_Barras": None,
        "Nome_Arquivo": None
    }

    # --- A. DADOS GERAIS ---
    
    # CNPJ/CPF
    cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
    cpf = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto)
    if cnpj: dados["Beneficiario_Pagador_Doc"] = cnpj.group()
    elif cpf: dados["Beneficiario_Pagador_Doc"] = cpf.group()

    # Data (Janela 2020-2030)
    datas_encontradas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
    datas_validas = []
    if datas_encontradas:
        for d in datas_encontradas:
            try:
                dt_obj = datetime.strptime(d, "%d/%m/%Y")
                if 2020 <= dt_obj.year <= 2030:
                    datas_validas.append(dt_obj)
            except: continue
    if datas_validas:
        dados["Data_Vencimento"] = max(datas_validas).strftime("%d/%m/%Y")

    # Valor
    valores = re.findall(r'(?:R\$\s?|Valor\s?)([\d\.]+,\d{2})', texto, re.IGNORECASE)
    if not valores:
        valores = re.findall(r'(?:\s|^)(\d{1,3}(?:\.\d{3})*,\d{2})(?:\s|$)', texto)
    
    if valores:
        try:
            valores_float = []
            for v in valores:
                if isinstance(v, tuple): v = v[0]
                v_clean = v.replace('.', '').replace(',', '.')
                valores_float.append(float(v_clean))
            max_val = max(valores_float)
            if max_val > 0: dados["Valor"] = max_val
        except: pass

    # --- B. CÓDIGO DE BARRAS (LÓGICA MULTI-PADRÃO) ---
    
    # Lista de padrões aceitos. O sistema tentará um por um.
    padroes = []

    # 1. Padrão Bancário Clássico (FEBRABAN)
    # Ex: 12345.12345 12345.123456 12345.123456 1 12345678901234
    padroes.append(r'(\d{5}[\.]?\d{5}[\s\.]+\d{5}[\.]?\d{6}[\s\.]+\d{5}[\.]?\d{6}[\s\.]+\d[\s\.]+\d{14})')
    
    # 2. Padrão Bancário Alternativo (Ex: Santander/Estácio)
    # Ex: 033990067.2 4121010110.5 2444060101.1 5 ...
    # Estrutura: Bloco1(9.1) Bloco2(10.1) Bloco3(10.1) Digito(1) Valor(14)
    # A regex abaixo permite o ponto mais para o final do bloco
    padroes.append(r'(\d{9,10}[\.]?\d{1,2}[\s\.]+\d{10,11}[\.]?\d{1,2}[\s\.]+\d{10,11}[\.]?\d{1,2}[\s\.]+\d[\s\.]+\d{14})')

    # 3. Padrão Arrecadação (Concessionárias) - 4 blocos
    padroes.append(r'(\d{11,12}[-\s]?\d{1}[\s\.]+\d{11,12}[-\s]?\d{1}[\s\.]+\d{11,12}[-\s]?\d{1}[\s\.]+\d{11,12}[-\s]?\d{1})')

    linha_encontrada = None

    for regex in padroes:
        match = re.search(regex, texto)
        if match:
            linha_encontrada = match.group(0)
            break # Parar no primeiro padrão que funcionar
    
    if linha_encontrada:
        dados["Codigo_Barras"] = limpar_string_numerica(linha_encontrada)

    return dados

# --- 3. BARRA LATERAL (SIDEBAR) ---
with st.sidebar:
    st.header("Fluxo de Trabalho")
    st.markdown("""
    **1. Upload:** Arraste seus arquivos PDF.
    
    **2. Processamento:** O sistema identifica Cód. Barras, Valores e Datas.
    
    **3. Conferência:** Verifique o **Valor Total** no topo da tela.
    
    **4. Ajuste:** Edite a tabela se necessário.
    
    **5. Exportação:** Baixe o Excel final.
    """)
    
    st.info("💡 **Dica:** O sistema foi ajustado para ignorar datas próximas ao código de barras.")
    
    st.divider()
    st.caption("v3.2 | Multi-Pattern Support")

# --- 4. ÁREA PRINCIPAL ---

st.title("💰 Extrator de Código de Barras Inteligente")

uploaded_files = st.file_uploader(
    "Arraste os arquivos PDF do lote aqui:", 
    type=['pdf'], 
    accept_multiple_files=True
)

if uploaded_files:
    lista_dados = []
    
    # Status container animado
    with st.status("Processando documentos...", expanded=True) as status:
        progresso_bar = st.progress(0)
        st.write("Iniciando leitura rigorosa dos arquivos...")
        
        for i, file in enumerate(uploaded_files):
            try:
                texto = extrair_texto_pdf(file)
                dados = buscar_padroes(texto)
                dados['Nome_Arquivo'] = file.name
                lista_dados.append(dados)
            except Exception as e:
                st.error(f"Erro no arquivo {file.name}")
            
            progresso_bar.progress((i + 1) / len(uploaded_files))
        
        status.update(label="✅ Processamento Finalizado!", state="complete", expanded=False)

    if lista_dados:
        df = pd.DataFrame(lista_dados)
        
        # --- TRATAMENTO DE ERROS NA DATA ---
        # Converte para datetime e trata erros silenciosamente (NaT)
        df['Data_Vencimento'] = pd.to_datetime(df['Data_Vencimento'], format='%d/%m/%Y', errors='coerce')

        # Ordenação de colunas
        cols_order = ['Nome_Arquivo', 'Beneficiario_Pagador_Doc', 'Data_Vencimento', 'Valor', 'Codigo_Barras']
        for c in cols_order:
            if c not in df.columns: df[c] = None
        df = df[cols_order]

        # --- DASHBOARD (KPIs) ---
        st.divider()
        st.subheader("📊 Resumo do Lote")
        
        col1, col2, col3 = st.columns(3)
        
        valor_total = df['Valor'].sum()
        qtd_boletos = len(df)
        sem_barras = df['Codigo_Barras'].isna().sum()

        with col1:
            st.metric("Valor Total do Lote", f"R$ {valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        with col2:
            st.metric("Quantidade de Boletos", qtd_boletos)
        with col3:
            st.metric("Boletos c/ Pendência", f"{sem_barras}", delta_color="inverse" if sem_barras > 0 else "normal")

        # --- TABELA INTERATIVA ---
        st.subheader("📝 Validação e Edição")
        st.caption("Dê um duplo clique na célula para corrigir valores manualmente.")

        df_editado = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            height=400,
            column_config={
                "Nome_Arquivo": st.column_config.TextColumn("Arquivo", disabled=True),
                "Beneficiario_Pagador_Doc": st.column_config.TextColumn("CNPJ/CPF", width="medium"),
                "Data_Vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
                "Valor": st.column_config.NumberColumn(
                    "Valor (R$)",
                    format="R$ %.2f",
                    min_value=0
                ),
                "Codigo_Barras": st.column_config.TextColumn(
                    "Linha Digitável",
                    help="Código para pagamento bancário",
                    width="large",
                    required=True
                )
            }
        )

        # --- EXPORTAÇÃO ---
        st.divider()
        col_esq, col_dir = st.columns([2, 1])
        
        with col_dir:
            # Preparar buffer Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_editado.to_excel(writer, index=False, sheet_name='Pagamentos')
            
            st.download_button(
                label="📥 BAIXAR PLANILHA FINAL (.xlsx)",
                data=output.getvalue(),
                file_name=f"Lote_Boletos_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
else:
    # Estado inicial amigável
    st.info("👆 Selecione os arquivos PDF acima para começar a extração.")