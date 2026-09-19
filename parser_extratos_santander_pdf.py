import pdfplumber
import pandas as pd
import re
import glob
import os
from tqdm import tqdm
from datetime import datetime

CATEGORIAS_DICT = {
    'Alimentação/Lazer': [
        'RESTAURANTE', 'IFOOD', 'BURGER', 'MCDONALDS', 'PIZZARIA', 'SORVETERIA', 
        'BAR', 'ZIG', 'CHOCOLATE', 'PADARIA', 'SUPERMERCADO', 'MARKET', 'ATACADO'
    ],
    'Transporte': [
        'POSTO', 'UBER', '99APP', 'SHELL', 'IPIRANGA', 'PEDAGIO', 'ESTACIONAMENTO',
        'AUTO POSTO', 'ABAST', 'VIACAO'
    ],
    'Moradia': [
        'ELETRO', 'ENERGIA', 'LUZ', 'AGUA', 'INTERNET', 'CLARO', 'VIVO', 'ALUGUEL', 
        'CONDOMINIO', 'SEMAE', 'PAULISTA DE FOR', 'MARTH'
    ],
    'Saúde': [
        'FARMACIA', 'DROGARIA', 'HOSPITAL', 'MEDICO', 'DENTISTA'
    ],
    'Investimentos': [
        'CORRETORA', 'XP', 'BTG', 'APLICACAO', 'INVESTIMENTO', 'REMUNERACAO APLICACAO'
    ],
    'Salário': [
        'SALARIO', 'PROVENTOS', 'REMUNERACAO', 'FERIAS', 'ADIANTAMENTO'
    ],
    'Transferências/Pix': [
        'PIX', 'TRANSF', 'TEV', 'DOC', 'TED'
    ]
}

MAPA_MESES = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9,
    'outubro': 10, 'novembro': 11, 'dezembro': 12
}

def definir_categoria(descricao):
    desc_upper = descricao.upper()
    for categoria, palavras_chave in CATEGORIAS_DICT.items():
        for palavra in palavras_chave:
            if palavra in desc_upper:
                return categoria
    return "Outros"

def limpar_valor_santander(valor_str):
    if not valor_str:
        return 0.0
    clean = str(valor_str).strip()
    eh_debito = clean.endswith('-') or clean.startswith('-')
    clean = clean.replace('-', '').replace('+', '').replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        val = float(clean)
        return -val if eh_debito else val
    except ValueError:
        return 0.0

def extrair_mes_ano(pdf):
    for page in pdf.pages[:2]:
        texto = page.extract_text() or ""
        match = re.search(r'([a-zç]+|\d{2})/(\d{4})', texto.lower())
        if match:
            mes_raw, ano_raw = match.groups()
            ano = int(ano_raw)
            mes = MAPA_MESES.get(mes_raw, int(mes_raw) if mes_raw.isdigit() else 1)
            return mes, ano
    return 1, 2026

def parse_santander_pdf(pdf_path):
    transacoes = []
    dentro_extrato = False
    ultimo_dia = "01"
    
    with pdfplumber.open(pdf_path) as pdf:
        mes_ref, ano_ref = extrair_mes_ano(pdf)
        
        for page in pdf.pages[1:3]:
            texto = page.extract_text()
            if not texto:
                continue

            for linha in texto.split('\n'):
                linha_limpa = linha.strip()
                linha_upper = linha_limpa.upper()

                # Marca de entrada no extrato
                if "MOVIMENTO" in linha_upper and "SALDO" in linha_upper:
                    dentro_extrato = True
                    continue

                # Marca de encerramento do extrato
                if dentro_extrato and any(t in linha_upper for t in [
                    "SALDOS POR PERÍODO", "SALDOS POR PERIODO", "COMPROVANTES DE PAGAMENTO", 
                    "CRÉDITOS CONTRATADOS", "PACOTE DE SERVIÇOS"
                ]):
                    dentro_extrato = False
                    break

                if not dentro_extrato:
                    continue

                # Ignora cabeçalhos soltos e saldos acumulados
                if any(t in linha_upper for t in ["EXTRATO CONSOLIDADO", "SALDO EM", "SALDO DISPONÍVEL", "CHEQUE ESPECIAL"]):
                    continue

                # Procura valores monetários na linha
                valores = list(re.finditer(r'(\d{1,3}(?:\.\d{3})*,\d{2}-?)', linha_limpa))

                # CASO 1: A linha NÃO tem valor -> É complemento da descrição da transação anterior
                if not valores:
                    if transacoes:
                        # Remove eventuais travessões ou pontuação residual
                        complemento = re.sub(r'^[-\s]+|[-\s]+$', '', linha_limpa)
                        if complemento and not any(k in complemento.upper() for k in ["MOVIMENTO", "PAGINA", "SALDO"]):
                            transacoes[-1]['Descrição'] += f" - {complemento}"
                            # Atualiza a categoria caso o nome do favorecido seja relevante
                            transacoes[-1]['Categoria'] = definir_categoria(transacoes[-1]['Descrição'])
                    continue

                # CASO 2: A linha TEM valor monetário -> É uma nova transação
                if len(valores) >= 2:
                    match_mov = valores[0]
                else:
                    match_mov = valores[-1]

                valor_float = limpar_valor_santander(match_mov.group(1))
                if valor_float == 0.0:
                    continue

                # Identifica se a linha começa com data
                match_data = re.match(r'^(\d{2}/\d{2})', linha_limpa)
                if match_data:
                    dia_str, mes_str = match_data.group(1).split('/')
                    ultimo_dia = dia_str
                    try:
                        mes_ref = int(mes_str)
                    except ValueError:
                        pass
                    desc = linha_limpa[match_data.end():match_mov.start()].strip()
                else:
                    desc = linha_limpa[:match_mov.start()].strip()

                desc = re.sub(r'^[-\s]+|[-\s]+$', '', desc)
                desc = re.sub(r'\b\d{6}\b', '', desc).strip()

                if not desc:
                    desc = "Movimentação Santander"

                data_transacao = datetime(ano_ref, mes_ref, int(ultimo_dia))
                cat = definir_categoria(desc)
                tipo = "Saída" if valor_float < 0 else "Entrada"

                transacoes.append({
                    'Data': data_transacao,
                    'Descrição': desc,
                    'Categoria': cat,
                    'Tipo': tipo,
                    'Valor': valor_float,
                    'Meio de Pagamento': 'Conta - Santander',
                    'Arquivo': os.path.basename(pdf_path)
                })

    return transacoes
    transacoes = []
    dentro_extrato = False
    ultimo_dia = "01"
    
    with pdfplumber.open(pdf_path) as pdf:
        mes_ref, ano_ref = extrair_mes_ano(pdf)
        
        # O extrato com movimentos situa-se nas páginas 2 e 3
        for page in pdf.pages[1:3]:
            texto = page.extract_text()
            if not texto:
                continue

            for linha in texto.split('\n'):
                linha_limpa = linha.strip()
                linha_upper = linha_limpa.upper()

                # Marca de entrada: linha que contém Movimento e Saldo
                if "MOVIMENTO" in linha_upper and "SALDO" in linha_upper:
                    dentro_extrato = True
                    continue

                # Marca de saída: secções seguintes
                if dentro_extrato and any(t in linha_upper for t in [
                    "SALDOS POR PERÍODO", "SALDOS POR PERIODO", "COMPROVANTES DE PAGAMENTO", 
                    "CRÉDITOS CONTRATADOS", "PACOTE DE SERVIÇOS"
                ]):
                    dentro_extrato = False
                    break

                if not dentro_extrato:
                    continue

                # Ignora linhas de cabeçalho residual ou saldos acumulados
                if any(t in linha_upper for t in ["EXTRATO CONSOLIDADO", "SALDO EM", "SALDO DISPONÍVEL", "CHEQUE ESPECIAL"]):
                    continue

                # Captura valores numéricos com decimais e opcional sinal de menos no final
                valores = list(re.finditer(r'(\d{1,3}(?:\.\d{3})*,\d{2}-?)', linha_limpa))
                if not valores:
                    continue

                # Identifica o valor do movimento: se houver dois valores juntos (Movimento e Saldo), o primeiro é o movimento
                if len(valores) >= 2:
                    match_mov = valores[0]
                else:
                    match_mov = valores[-1]

                valor_float = limpar_valor_santander(match_mov.group(1))
                if valor_float == 0.0:
                    continue

                # Verifica se a linha tem data explícita (ex: 29/01)
                match_data = re.match(r'^(\d{2}/\d{2})', linha_limpa)
                if match_data:
                    dia_str, mes_str = match_data.group(1).split('/')
                    ultimo_dia = dia_str
                    try:
                        mes_ref = int(mes_str)
                    except ValueError:
                        pass
                    desc = linha_limpa[match_data.end():match_mov.start()].strip()
                else:
                    desc = linha_limpa[:match_mov.start()].strip()

                # Remove hífen residual e códigos numéricos soltos
                desc = re.sub(r'^[-\s]+|[-\s]+$', '', desc)
                desc = re.sub(r'\b\d{6}\b', '', desc).strip()

                if not desc:
                    desc = "Movimentação Santander"

                data_transacao = datetime(ano_ref, mes_ref, int(ultimo_dia))
                cat = definir_categoria(desc)
                tipo = "Saída" if valor_float < 0 else "Entrada"

                transacoes.append({
                    'Data': data_transacao,
                    'Descrição': desc,
                    'Categoria': cat,
                    'Tipo': tipo,
                    'Valor': valor_float,
                    'Meio de Pagamento': 'Conta - Santander',
                    'Arquivo': os.path.basename(pdf_path)
                })

    return transacoes

def processar_extratos_santander():
    arquivos = glob.glob("*.pdf")
    arquivos_santander = [f for f in arquivos if any(t in f.lower() for t in ["santander", "comprovante", "extrato"])]

    if not arquivos_santander:
        print("Nenhum ficheiro PDF correspondente encontrado.")
        return

    todas_transacoes = []
    print(f"A processar {len(arquivos_santander)} extrato(s) Santander em PDF...\n")

    for arq in tqdm(arquivos_santander, desc="Progresso Santander", colour="red"):
        try:
            txs = parse_santander_pdf(arq)
            todas_transacoes.extend(txs)
        except Exception as e:
            print(f"\nErro ao processar {arq}: {e}")

  ##  if todas_transacoes:
    if todas_transacoes:
        df = pd.DataFrame(todas_transacoes)
        df = df.sort_values(by='Data', ascending=True)

        colunas = ['Data', 'Descrição', 'Categoria', 'Tipo', 'Valor', 'Meio de Pagamento', 'Arquivo']
        df = df[colunas]

        # Determina o período coberto pelo lote
        data_min = df['Data'].min()
        data_max = df['Data'].max()
        periodo_min = data_min.strftime('%m-%Y')
        periodo_max = data_max.strftime('%m-%Y')

        if periodo_min == periodo_max:
            nome_excel = f"Relatorio_Santander_{periodo_min}.xlsx"
        else:
            nome_excel = f"Relatorio_Santander_{periodo_min}_a_{periodo_max}.xlsx"

        with pd.ExcelWriter(nome_excel, engine='xlsxwriter', datetime_format='dd/mm/yyyy') as writer:
            df.to_excel(writer, sheet_name='Extrato_Santander', index=False)
            wb = writer.book
            ws = writer.sheets['Extrato_Santander']
            money_fmt = wb.add_format({'num_format': '#,##0.00'})
            date_fmt = wb.add_format({'num_format': 'dd/mm/yyyy'})

            ws.set_column('A:A', 12, date_fmt)
            ws.set_column('B:B', 45)
            ws.set_column('C:C', 20)
            ws.set_column('E:E', 15, money_fmt)

        print(f"\nSucesso! {len(df)} transações extraídas.")
        print(f"Arquivo gerado: {nome_excel}")
        

if __name__ == "__main__":
    processar_extratos_santander()