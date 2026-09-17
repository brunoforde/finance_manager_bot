import pdfplumber
import pandas as pd
import re
import glob
import os
from tqdm import tqdm
from datetime import datetime

# --- CONFIGURAÇÕES ---

TERMOS_IGNORAR = [
    "PAGTO DEBITO AUTOMATICO", "PAGAMENTO EFETUADO", "OBRIGADO PELO PAGAMENTO",
    "SALDO ANTERIOR", "CREDITO ROTATIVO", "TOTAL DA FATURA", "SALDO DEVEDOR",
    "PAGAMENTO EM CONTA CORRENTE", "TOTAL DESTA FATURA", "PAGAMENTO RECEBIDO",
    "SALDO DO PARCELAMENTO", "SALDO RESTANTE", "PAGAMENTO MÍNIMO"
]

CATEGORIAS_DICT = {
    'Alimentação/Lazer': [
        'RESTAURANTE', 'IFOOD', 'BURGER', 'MCDONALDS', 'PIZZARIA', 'SORVETERIA', 
        'BAR', 'ZIG', 'CHOCOLATE', 'PADARIA', 'SUPERMERCADO', 'MARKET', 'ATACADO',
        'OUTBACK', 'THE BEST', 'KIBE', 'DOCES'
    ],
    'Transporte': [
        'POSTO', 'UBER', '99APP', 'SHELL', 'IPIRANGA', 'PEDAGIO', 'ESTACIONAMENTO',
        'AUTO POSTO', 'ABAST', 'VIACAO', 'BLABLACAR', 'MOBIFACIL'
    ],
    'Moradia': [
        'ELETRO', 'CASA', 'CONSTRUCAO', 'LEROY', 'TELHANORTE', 'INTERNET', 'CLARO', 'VIVO'
    ],
    'Saúde': [
        'FARMACIA', 'DROGARIA', 'HOSPITAL', 'MEDICO', 'DENTISTA', 'RAIA', 'SOUSMILE'
    ],
    'Investimentos': [
        'CORRETORA', 'XP', 'BTG', 'CRIPT'
    ],
    'Salário': []
}

MAPA_MESES = {
    'janeiro': 1, 'jan': 1,
    'fevereiro': 2, 'fev': 2,
    'março': 3, 'marco': 3, 'mar': 3,
    'abril': 4, 'abr': 4,
    'maio': 5, 'mai': 5,
    'junho': 6, 'jun': 6,
    'julho': 7, 'jul': 7,
    'agosto': 8, 'ago': 8,
    'setembro': 9, 'set': 9,
    'outubro': 10, 'out': 10,
    'novembro': 11, 'nov': 11,
    'dezembro': 12, 'dez': 12
}

def definir_categoria(descricao):
    desc_upper = descricao.upper()
    for categoria, palavras_chave in CATEGORIAS_DICT.items():
        for palavra in palavras_chave:
            if palavra in desc_upper:
                return categoria
    return "Outros"

def validar_data_real(dia_str):
    try:
        dia = int(dia_str)
        return 1 <= dia <= 31
    except:
        return False

def extrair_data_do_nome(nome_arquivo):
    """
    Lê o Mês e Ano do NOME do arquivo.
    """
    nome_limpo = nome_arquivo.lower()
    
    match_ano = re.search(r'(20\d{2})', nome_limpo)
    ano = int(match_ano.group(1)) if match_ano else datetime.now().year
    
    mes_encontrado = 0
    for texto_mes, num_mes in MAPA_MESES.items():
        if re.search(rf'[-_ \.]{texto_mes}[-_ \.]', f".{nome_limpo}."): 
            mes_encontrado = num_mes
            break
            
    if mes_encontrado == 0:
        match_num = re.search(r'[-_ ](0[1-9]|1[0-2])[-_ \.]', nome_limpo)
        if match_num:
            mes_encontrado = int(match_num.group(1))

    if mes_encontrado > 0:
        return datetime(ano, mes_encontrado, 1)
    
    return None

# ==============================================================================
# PARSER CARTÃO INTER (ATIVO)
# ==============================================================================

def parse_inter(pdf_path):
    transacoes = []
    meses = {'jan': '01', 'fev': '02', 'mar': '03', 'abr': '04', 'mai': '05', 'jun': '06',
             'jul': '07', 'ago': '08', 'set': '09', 'out': '10', 'nov': '11', 'dez': '12'}
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            
            lines = text.split('\n')
            for line in lines:
                match_data = re.search(r'(\d{2})\s+de\s+([a-z]{3})\.\s+(\d{4})', line, re.IGNORECASE)
                match_valor = re.search(r'([+\-]?\s*R\$\s*[\d\.,]+)', line)
                
                if match_data and match_valor:
                    dia, mes_ext, ano = match_data.groups()
                    if not validar_data_real(dia): continue

                    mes_num = meses.get(mes_ext.lower(), '01')
                    data_fmt = f"{dia}/{mes_num}/{ano}"
                    
                    valor_raw = match_valor.group(1)
                    fator = -1.0 if '+' in valor_raw else 1.0
                    
                    valor_limpo = valor_raw.replace('R$', '').replace('.', '').replace(',', '.').replace('+', '').replace('-', '').strip()
                    valor_float = float(valor_limpo) * fator
                    
                    desc = line[match_data.end():].replace(valor_raw, '').strip()
                    
                    ignorar = any(termo in desc.upper() for termo in TERMOS_IGNORAR)
                    if ignorar: continue
                    
                    cat = definir_categoria(desc)
                    tipo = "Entrada" if valor_float < 0 else "Saída"

                    transacoes.append({
                        'Data': data_fmt, 'Descrição': desc, 'Categoria': cat,
                        'Tipo': tipo, 'Valor': valor_float, 'Meio de Pagamento': 'Cartão Inter',
                        'Arquivo': os.path.basename(pdf_path)
                    })
    return transacoes

# ==============================================================================
# PARSER CARTÃO ELO / CAIXA (DESATIVADO TEMPORARIAMENTE)
# ==============================================================================
# def limpar_valor_elo(valor_str):
#     if not valor_str: return 0.0
#     clean = valor_str.strip().upper()
#     fator = 1.0
#     if clean.endswith('C'):
#         fator = -1.0
#         clean = clean[:-1]
#     elif clean.endswith('D'):
#         fator = 1.0
#         clean = clean[:-1]
#     clean = clean.replace('R$', '').replace('US$', '').strip().replace('.', '')
#     if re.search(r',\d{3}$', clean) and clean.endswith('0'):
#         clean = clean[:-1]
#     clean = clean.replace(',', '.')
#     try:
#         return float(clean) * fator
#     except ValueError:
#         return 0.0

# def parse_elo(pdf_path):
#     transacoes = []
#     ... (mantido comentado caso precise no futuro) ...
#     return transacoes

# --- EXECUTOR ---

def processar_faturas():
    arquivos_pdf = glob.glob("*.pdf")
    
    if not arquivos_pdf:
        print("Nenhum arquivo PDF encontrado nesta pasta.")
        return

    todas_transacoes = []
    dados_validacao = []
    datas_encontradas = []

    print(f"Processando {len(arquivos_pdf)} arquivo(s) PDF de faturas...\n")
    pbar = tqdm(arquivos_pdf, desc="Progresso", unit="fatura", colour="green")

    for arquivo in pbar:
        try:
            nome_arquivo = os.path.basename(arquivo)
            pbar.set_description(f"Lendo {nome_arquivo[:15]}...")
            
            data_arq = extrair_data_do_nome(nome_arquivo)
            mes_ref_str = data_arq.strftime('%m/%Y') if data_arq else "Indefinido"
            if data_arq:
                datas_encontradas.append(data_arq)

            cartao = "Outros"
            txs = []
            
            # Apenas o parser do Inter está ativo
            if "inter" in nome_arquivo.lower():
                cartao = "Inter"
                txs = parse_inter(arquivo)
            # elif "elo" in nome_arquivo.lower() or "caixa" in nome_arquivo.lower():
            #     cartao = "Elo/Caixa"
            #     txs = parse_elo(arquivo)
            else:
                tqdm.write(f"Aviso: Arquivo '{nome_arquivo}' ignorado (sem parser compatível ativo).")
            
            if txs:
                todas_transacoes.extend(txs)
                dados_validacao.append({
                    "Arquivo": nome_arquivo,
                    "Cartão": cartao,
                    "Mês Referência": mes_ref_str,
                    "Total PDF": 0.0
                })
                
        except Exception as e:
            tqdm.write(f"Erro no arquivo {arquivo}: {e}")

    if todas_transacoes:
        df = pd.DataFrame(todas_transacoes)
        
        if datas_encontradas:
            min_date = min(datas_encontradas)
            max_date = max(datas_encontradas)
            periodo = f"{min_date.strftime('%m-%Y')}_a_{max_date.strftime('%m-%Y')}"
        else:
            periodo = "Geral"

        output_file = f'Relatorio_Faturas_{periodo}.xlsx'
        colunas_finais = ['Data', 'Descrição', 'Categoria', 'Tipo', 'Valor', 'Meio de Pagamento', 'Arquivo']
        df = df[colunas_finais]
        df_val = pd.DataFrame(dados_validacao)

        with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Extrato_Geral', index=False)
            
            cols_val = ['Arquivo', 'Cartão', 'Mês Referência', 'Total PDF']
            df_val.to_excel(writer, sheet_name='Validacao', index=False, columns=cols_val)
            
            workbook = writer.book
            worksheet = writer.sheets['Validacao']
            money_fmt = workbook.add_format({'num_format': '#,##0.00'})
            
            worksheet.write('E1', 'Soma Extraída')
            worksheet.write('F1', 'Diferença')

            for i in range(len(df_val)):
                row_idx = i + 2
                formula_soma = f"=SUMIF(Extrato_Geral!G:G, A{row_idx}, Extrato_Geral!E:E)"
                formula_diff = f"=D{row_idx}-E{row_idx}"
                worksheet.write_formula(f'E{row_idx}', formula_soma, money_fmt)
                worksheet.write_formula(f'F{row_idx}', formula_diff, money_fmt)
        
        print(f"\n\nSucesso! Arquivo gerado: {output_file}")
    else:
        print("\nNenhuma transação de fatura extraída.")

if __name__ == "__main__":
    processar_faturas()