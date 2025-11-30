# Desenvolvido por: Paulo César Jr.
#26/11/2025
import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from datetime import datetime

# --- 1. CONFIGURAÇÃO DE UI ---
st.set_page_config(
    page_title="Extrator de Boletos (Multi-Page)",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #fff; border: 1px solid #e9ecef; border-radius: 8px; padding: 10px; }
    .stButton>button { width: 100%; border-radius: 6px; height: 3em; font-weight: bold; }
    div[data-testid="stDownloadButton"] > button { background-color: #2e7d32; color: white; border: none; }
    div[data-testid="stDownloadButton"] > button:hover { background-color: #1b5e20; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. MOTOR DE EXTRAÇÃO ESTRUTURAL (V4.0) ---

def limpar_string_numerica(s):
    if not s: return None
    return re.sub(r'[^0-9]', '', s)

def buscar_padroes_na_pagina(texto, numero_pagina, nome_arquivo):
    """
    Analisa UMA única página por vez.
    Retorna um dicionário de dados se achar algo relevante, ou dados vazios.
    """
    dados = {
        "Arquivo_Origem": f"{nome_arquivo} (Pág {numero_pagina})",
        "Beneficiario_Pagador_Doc": None,
        "Data_Vencimento": None,
        "Valor": 0.0,
        "Codigo_Barras": None
    }

    # --- A. CÓDIGO DE BARRAS (Prioridade Máxima) ---
    # Se não tiver código de barras na página, provavelmente é capa ou extrato.
    
    padroes_barras = [
        # 1. Bancário Padrão (47 dígitos com espaços/pontos)
        r'(\d{5}[\.]?\d{5}[\s\.]+\d{5}[\.]?\d{6}[\s\.]+\d{5}[\.]?\d{6}[\s\.]+\d[\s\.]+\d{14})',
        # 2. Bancário Compacto/Alternativo (Ex: Santander/Estácio - pontos deslocados)
        r'(\d{9,10}[\.]?\d{1,2}[\s\.]+\d{10,11}[\.]?\d{1,2}[\s\.]+\d{10,11}[\.]?\d{1,2}[\s\.]+\d[\s\.]+\d{14})',
        # 3. Arrecadação/Concessionárias (4 blocos de 12 dígitos - Ex: Detran/Luz)
        r'(\d{11,12}[-\s]?\d{1}[\s\.]+\d{11,12}[-\s]?\d{1}[\s\.]+\d{11,12}[-\s]?\d{1}[\s\.]+\d{11,12}[-\s]?\d{1})'
    ]

    linha_crua = None
    for p in padroes_barras:
        match = re.search(p, texto)
        if match:
            linha_crua = match.group(0)
            break
    
    if linha_crua:
        dados["Codigo_Barras"] = limpar_string_numerica(linha_crua)
    else:
        # Se não achou código de barras, marcamos para descarte posterior
        return None 

    # --- B. DADOS COMPLEMENTARES (Só busca se achou o código) ---
    
    # CNPJ/CPF
    cnpj = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
    cpf = re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto)
    if cnpj: dados["Beneficiario_Pagador_Doc"] = cnpj.group()
    elif cpf: dados["Beneficiario_Pagador_Doc"] = cpf.group()

    # Data (Janela 2020-2030)
    datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
    datas_validas = []
    if datas:
        for d in datas:
            try:
                dt = datetime.strptime(d, "%d/%m/%Y")
                if 2020 <= dt.year <= 2030: datas_validas.append(dt)
            except: continue
    if datas_validas:
        # Geralmente o vencimento é a maior data futura
        dados["Data_Vencimento"] = max(datas_validas).strftime("%d/%m/%Y")

    # Valor
    # Tenta achar valor monetário explícito (R$)
    valores = re.findall(r'(?:R\$\s?|Valor\s?)([\d\.]+,\d{2})', texto, re.IGNORECASE)
    if not valores:
        # Tenta achar formato monetário isolado
        valores = re.findall(r'(?:\s|^)(\d{1,3}(?:\.\d{3})*,\d{2})(?:\s|$)', texto)
    
    if valores:
        valores_float = []
        for v in valores:
            try:
                if isinstance(v, tuple): v = v[0]
                v_clean = v.replace('.', '').replace(',', '.')
                valores_float.append(float(v_clean))
            except: continue
        
        if valores_float:
            dados["Valor"] = max(valores_float)

    return dados

# --- 3. FRONTEND ---

with st.sidebar:
    st.header("Fluxo V4.0 (Multi-Page)")
    st.info("""
    **1. Upload:** Arraste seus arquivos PDF.
    
    **2. Processamento:** O sistema identifica Cód. Barras, Valores e Datas.
    
    **3. Conferência:** Verifique o **Valor Total** no topo da tela.
    
    **4. Ajuste:** Edite a tabela se necessário.
    
    **5. Exportação:** Baixe o Excel final.
    """"""
    **Novidade:** Agora o sistema lê arquivos PDF com múltiplas páginas (ex: 1 arquivo com 50 boletos).
    
    Ele verifica página por página e ignora capas ou extratos que não tenham código de barras.
    """)

st.title("💰 Extrator de Código de Barras de Boletos")
st.markdown("### Processamento de Arquivos Individuais e/ou Multipáginas")

uploaded_files = st.file_uploader(
    "Arraste arquivos PDF (Individuais ou com Múltiplos Boletos)", 
    type=['pdf'], 
    accept_multiple_files=True
)

if uploaded_files:
    lista_final = []
    
    with st.status("Analisando páginas...", expanded=True) as status:
        progresso_geral = st.progress(0)
        
        for i_file, file in enumerate(uploaded_files):
            try:
                # ABRE O PDF
                with pdfplumber.open(file) as pdf:
                    total_paginas = len(pdf.pages)
                    
                    # ITERA SOBRE CADA PÁGINA INDIVIDUALMENTE
                    for i_page, page in enumerate(pdf.pages):
                        texto_pagina = page.extract_text() or ""
                        
                        # Processa a página
                        resultado = buscar_padroes_na_pagina(texto_pagina, i_page + 1, file.name)
                        
                        # FILTRO INTELIGENTE: Só adiciona se achou código de barras
                        if resultado and resultado["Codigo_Barras"]:
                            lista_final.append(resultado)
                        
                        # Log discreto para debug visual se necessário
                        # st.text(f"Lendo {file.name} - Pág {i_page+1}")

            except Exception as e:
                st.error(f"Erro ao ler {file.name}: {e}")
            
            progresso_geral.progress((i_file + 1) / len(uploaded_files))
        
        status.update(label=f"Concluído! Encontrados {len(lista_final)} boletos válidos.", state="complete", expanded=False)

    if lista_final:
        df = pd.DataFrame(lista_final)
        
        # Converte Data
        df['Data_Vencimento'] = pd.to_datetime(df['Data_Vencimento'], format='%d/%m/%Y', errors='coerce')

        # Ordena Colunas
        cols = ['Arquivo_Origem', 'Beneficiario_Pagador_Doc', 'Data_Vencimento', 'Valor', 'Codigo_Barras']
        for c in cols: 
            if c not in df.columns: df[c] = None
        df = df[cols]

        # --- DASHBOARD ---
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Valor Total (R$)", f"R$ {df['Valor'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        c2.metric("Boletos Detectados", len(df))
        c3.metric("Arquivos Enviados", len(uploaded_files))

        # --- TABELA ---
        st.subheader("Validação")
        df_editado = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Valor": st.column_config.NumberColumn(format="R$ %.2f"),
                "Data_Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Codigo_Barras": st.column_config.TextColumn(width="large", required=True)
            }
        )

        # --- DOWNLOAD ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_editado.to_excel(writer, index=False, sheet_name='Boletos')
        
        st.download_button(
            "📥 Baixar Planilha em Excel (.xlsx)",
            data=output.getvalue(),
            file_name="Boletos_Extraidos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    else:
        st.warning("Nenhum código de barras válido foi encontrado nos arquivos. Verifique se são boletos legíveis (não imagens).")

else:
    st.info("Aguardando upload...")
