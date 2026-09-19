import pandas as pd
import glob
import os
import shutil
import re
import io 
from ofxparse import OfxParser
from tqdm import tqdm

# --- CONFIGURAÇÕES ---

PASTA_ENTRADA = os.getenv(".")
PASTA_SAIDA = os.getenv(".")

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
    desc_upper = descricao.upper()
    for categoria, palavras_chave in CATEGORIAS_DICT.items():
        for palavra in palavras_chave:
            if palavra in desc_upper:
                return categoria
    return "Outros"

def ler_ofx_seguro(caminho_arquivo):
    # 1. Lê o arquivo como bytes brutos (sem tentar decodificar ainda)
    with open(caminho_arquivo, 'rb') as f:
        raw_bytes = f.read()
        
    # 2. Tenta decodificar. Se der o erro do 0xc1 (UnicodeDecodeError), 
    # sabemos que o banco enviou como Latin-1.
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
            # Remove os espaços em branco que quebram a leitura
            valor = valor.strip().replace(' ', '')
            
            # Força o cabeçalho a dizer a verdade: vamos converter tudo para UTF-8 real
            if chave == 'ENCODING':
                valor = 'UTF-8'
                
            linhas_corrigidas.append(f"{chave}:{valor}")
        else:
            linhas_corrigidas.append(linha)

    conteudo_final = '\n'.join(linhas_corrigidas)

    arquivo_memoria = io.BytesIO(conteudo_final.encode('utf-8'))
    
    return OfxParser.parse(arquivo_memoria)
    
    # 3. O pulo do gato: Transforma o texto corrigido de volta em bytes, 
    # mas agora garantindo que seja um UTF-8 real e perfeito.
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
            banco_nome = conta.institution.organization if conta.institution else "Banco Desconhecido"
            
            # =====================================================================
            # CÓDIGO COMENTADO: EXTRAÇÃO DO SALDO FINAL DO EXTRATO
            # =====================================================================
            # saldo_final = conta.statement.balance
            # data_saldo = conta.statement.balance_date
            # print(f"\n[INFO] Conta {banco_nome} - Saldo em {data_saldo}: R$ {saldo_final}")
            # =====================================================================

            for transacao in conta.statement.transactions:
                # Mantendo o sinal original do OFX: Positivo = Entrada, Negativo = Saída
                valor_ofx = float(transacao.amount)
                tipo = "Entrada" if valor_ofx > 0 else "Saída"
                descricao = transacao.memo.strip()
                cat = definir_categoria(descricao)

                # Mantém o objeto datetime puro (removendo fuso horário para não dar conflito no Excel)
                data_real = transacao.date.replace(tzinfo=None)

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
            
            # Formatações Visuais
            money_fmt = workbook.add_format({'num_format': '#,##0.00'})
            date_fmt = workbook.add_format({'num_format': 'dd/mm/yyyy'})
            
            # Ajustando a largura e o formato das colunas
            worksheet.set_column('A:A', 12, date_fmt)   # Coluna Data
            worksheet.set_column('B:B', 35)             # Coluna Descrição (mais larga para caber os textos)
            worksheet.set_column('C:C', 18)             # Coluna Categoria
            worksheet.set_column('E:E', 15, money_fmt)  # Coluna Valor
        
        print(f"\n\nSucesso! Arquivo gerado: {output_file}")
        
        print("Movendo arquivos processados...")
        for arquivo in arquivos_ofx:
            nome_arquivo = os.path.basename(arquivo)
            destino = os.path.join(PASTA_SAIDA, nome_arquivo)
            
            if os.path.exists(destino):
                os.remove(destino)
                
            shutil.move(arquivo, destino)
            
        print(f"Arquivos movidos para a pasta '{PASTA_SAIDA}' com sucesso!")

    else:
        print("\nNenhuma transação encontrada nos arquivos OFX.")

if __name__ == "__main__":
    processar_ofx()