import pandas as pd
import glob
import os
import shutil
import re
import io 
from ofxparse import OfxParser
from tqdm import tqdm

# ### Configs ###

PASTA_ENTRADA = "." # Removed the path to use the current folder for the running
PASTA_SAIDA = "."

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
        'ELETRO', 'ENERGIA', 'LUZ', 'AGUA', 'INTERNET', 'CLARO', 'VIVO', 'ALUGUEL', 'CONDOMINIO'
    ],
    'Saúde': [
        'FARMACIA', 'DROGARIA', 'HOSPITAL', 'MEDICO', 'DENTISTA'
    ],
    'Investimentos': [
        'CORRETORA', 'XP', 'BTG', 'APLICACAO', 'INVESTIMENTO'
    ],
    'Salário': [
        'SALARIO', 'PROVENTOS', 'REMUNERACAO'
    ],
    'Transferências/Pix': [
        'PIX', 'TRANSF', 'TEV', 'DOC', 'TED'
    ]
}

def definir_categoria(descricao):
    desc_upper = str(descricao).upper()
    for categoria, palavras_chave in CATEGORIAS_DICT.items():
        for palavra in palavras_chave:
            if palavra in desc_upper:
                return categoria
    return "Outros"

def ler_ofx_seguro(caminho_arquivo):
    # 1. Opening the file
    with open(caminho_arquivo, 'rb') as f:
        raw_bytes = f.read()
        
    # 2. Trying to decode and in case of error mark the enconding as latin-1 which is the other possibility mapped
    try:
        conteudo = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        conteudo = raw_bytes.decode('latin-1') 

    linhas = conteudo.splitlines()
    linhas_corrigidas = []
    
    for linha in linhas:
        if linha.startswith('<OFX>'):
            inicio_xml = conteudo.find('<OFX>')
            linhas_corrigidas.append(conteudo[inicio_xml:])
            break
        elif ':' in linha and not linha.startswith('<'):
            chave, valor = linha.split(':', 1)
            chave = chave.strip()
            # Remove empty spaces (which could brake the extraction or give wrong data)
            valor = valor.strip().replace(' ', '')
            
            # Convert to UTF-8
            if chave == 'ENCODING':
                valor = 'UTF-8'
                
            linhas_corrigidas.append(f"{chave}:{valor}")
        else:
            linhas_corrigidas.append(linha)

    conteudo_final = '\n'.join(linhas_corrigidas)

    # Injeta LEDGERBAL dummy caso o banco (ex: Caixa) não envie a tag (suporta SGML e XML)
    if "<LEDGERBAL>" not in conteudo_final.upper():
        dummy_bal = "\n<LEDGERBAL>\n<BALAMT>0.00</BALAMT>\n<DTASOF>20260101</DTASOF>\n</LEDGERBAL>\n"
        if "</STMTRS>" in conteudo_final.upper():
            conteudo_final = re.sub(r'</STMTRS>', dummy_bal + "</STMTRS>", conteudo_final, flags=re.IGNORECASE)
        elif "</BANKTRANLIST>" in conteudo_final.upper():
            conteudo_final = re.sub(r'</BANKTRANLIST>', "</BANKTRANLIST>" + dummy_bal, conteudo_final, flags=re.IGNORECASE)
        else:
            # Padrão SGML puro da Caixa (sem tags de fechamento com barra)
            conteudo_final += dummy_bal

    # 3. Convert data back to bytes after ensuring it's in utf-8 encoding
    arquivo_memoria = io.BytesIO(conteudo_final.encode('utf-8'))
    return OfxParser.parse(arquivo_memoria)

def processar_ofx():
    os.makedirs(PASTA_ENTRADA, exist_ok=True)
    os.makedirs(PASTA_SAIDA, exist_ok=True)

    caminho_busca = os.path.join(PASTA_ENTRADA, "*.ofx")
    arquivos_ofx = glob.glob(caminho_busca)
    
    if not arquivos_ofx:
        print(f"Nenhum arquivo OFX encontrado na pasta '{PASTA_ENTRADA}'.")
        return

    todas_transacoes = []
    periodos_encontrados = set() 
    processados_com_sucesso = []
    
    padrao_periodo = re.compile(r'(\d{2}[a-zA-Z]{3}-\d{2}[a-zA-Z]{3})')

    print(f"Processando {len(arquivos_ofx)} arquivos OFX...\n")
    pbar = tqdm(arquivos_ofx, desc="Progresso", unit="extrato", colour="blue")

    for arquivo in pbar:
        nome_arquivo = os.path.basename(arquivo)
        
        match = padrao_periodo.search(nome_arquivo)
        if match:
            periodos_encontrados.add(match.group(1))

        try:
            pbar.set_description(f"Lendo {nome_arquivo[:15]}...")
            
            ofx = ler_ofx_seguro(arquivo)
            conta = ofx.account
            banco_nome = conta.institution.organization if (conta and conta.institution and conta.institution.organization) else "Banco Desconhecido"

            # Identificação alternativa de banco via nome de arquivo caso a tag venha genérica
            if banco_nome == "Banco Desconhecido":
                if "caixa" in nome_arquivo.lower():
                    banco_nome = "Caixa Econômica"
                elif "itau" in nome_arquivo.lower():
                    banco_nome = "Itaú"
                elif "inter" in nome_arquivo.lower():
                    banco_nome = "Inter"

            # Code deprecated, used to validate the final results
            # =====================================================================
            # EXTRAÇÃO DO SALDO FINAL DO EXTRATO - Total balance extraction
            # =====================================================================
            # saldo_final = conta.statement.balance
            # data_saldo = conta.statement.balance_date
            # print(f"\n[INFO] Conta {banco_nome} - Saldo em {data_saldo}: R$ {saldo_final}")
            # =====================================================================

            if conta and hasattr(conta, 'statement') and conta.statement and conta.statement.transactions:
                for transacao in conta.statement.transactions:
                    # Keep original signals from the files ([+] -> Inflow; [-] -> Outflow)
                    valor_ofx = float(transacao.amount)
                    tipo = "Entrada" if valor_ofx > 0 else "Saída"
                    descricao = (transacao.memo or transacao.payee or "Transação sem descrição").strip()
                    cat = definir_categoria(descricao)

                    data_real = transacao.date
                    if hasattr(data_real, 'tzinfo') and data_real.tzinfo:
                        data_real = data_real.replace(tzinfo=None)

                    todas_transacoes.append({
                        'Data': data_real,
                        'Descrição': descricao,
                        'Categoria': cat,
                        'Tipo': tipo,
                        'Valor': valor_ofx,
                        'Meio de Pagamento': f'Conta - {banco_nome}',
                        'Arquivo': nome_arquivo,
                        'ID Transação': transacao.id 
                    })
            processados_com_sucesso.append(nome_arquivo)  
             
        except Exception as e:
            tqdm.write(f"Erro no arquivo {arquivo}: {e}")

    if todas_transacoes:
        df = pd.DataFrame(todas_transacoes)
        colunas_finais = ['Data', 'Descrição', 'Categoria', 'Tipo', 'Valor', 'Meio de Pagamento', 'Arquivo', 'ID Transação']
        df = df[colunas_finais]

        if periodos_encontrados:
            sufixo_data = "_".join(list(periodos_encontrados))
            output_file = f'Relatorio_Extratos_OFX_{sufixo_data}.xlsx'
        else:
            output_file = 'Relatorio_Extratos_OFX.xlsx'

        with pd.ExcelWriter(output_file, engine='xlsxwriter', datetime_format='dd/mm/yyyy') as writer:
            df.to_excel(writer, sheet_name='Extrato_Bancario', index=False)
            
            workbook = writer.book
            worksheet = writer.sheets['Extrato_Bancario']
            
            # Format amount/values 
            money_fmt = workbook.add_format({'num_format': '#,##0.00'})
            # Format date
            date_fmt = workbook.add_format({'num_format': 'dd/mm/yyyy'})
            
            # Set collumns layout in the spreadsheet
            worksheet.set_column('A:A', 12, date_fmt)   # Date column
            worksheet.set_column('B:B', 35)             # Description column
            worksheet.set_column('C:C', 18)             # Category column
            worksheet.set_column('E:E', 15, money_fmt)  # Amount column
        
        print(f"\n\nSucesso! Arquivo gerado: {output_file}")

    else:
        print("\nNenhuma transação encontrada nos arquivos OFX.")

if __name__ == "__main__":
    processar_ofx()