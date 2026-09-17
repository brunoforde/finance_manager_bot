import os
import shutil
import glob
from drive_client import get_drive_service, list_files, download_file, upload_file
import parser_faturas_cartao
import parser_extratos_ofx

PASTA_TMP_ENTRADA = "./temp_entrada"
PASTA_TMP_SAIDA = "./temp_saida"

def run_pipeline():
    # 1. Obter variáveis de ambiente
    input_folder_id = os.environ.get("DRIVE_INPUT_FOLDER_ID")
    output_folder_id = os.environ.get("DRIVE_OUTPUT_FOLDER_ID")

    if not input_folder_id or not output_folder_id:
        print("[ERRO] Variáveis DRIVE_INPUT_FOLDER_ID ou DRIVE_OUTPUT_FOLDER_ID não configuradas.")
        return

    # 2. Criar pastas temporárias de trabalho
    os.makedirs(PASTA_TMP_ENTRADA, exist_ok=True)
    os.makedirs(PASTA_TMP_SAIDA, exist_ok=True)

    print("Conectando ao Google Drive...")
    service = get_drive_service()

    # 3. Listar arquivos presentes na pasta de entrada do Drive
    arquivos_drive = list_files(service, input_folder_id)
    if not arquivos_drive:
        print("Nenhum arquivo encontrado na pasta de entrada do Google Drive.")
        return

    print(f"Foram encontrados {len(arquivos_drive)} arquivos no Drive. Baixando...")
    for item in arquivos_drive:
        destino = os.path.join(PASTA_TMP_ENTRADA, item['name'])
        print(f" -> Baixando: {item['name']}")
        download_file(service, item['id'], destino)

    # 4. Processar PDFs (Faturas de Cartão)
    pdfs = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.pdf"))
    if pdfs:
        print(f"\n--- Processando {len(pdfs)} fatura(s) PDF ---")
        # Muda temporariamente o diretório de trabalho para a pasta de entrada
        pasta_original = os.getcwd()
        os.chdir(PASTA_TMP_ENTRADA)
        try:
            parser_faturas_cartao.processar_faturas()
        finally:
            os.chdir(pasta_original)

    # 5. Processar OFX (Extratos Bancários)
    ofxs = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.ofx"))
    if ofxs:
        print(f"\n--- Processando {len(ofxs)} extrato(s) OFX ---")
        # Ajusta pastas dinamicamente para o script OFX
        parser_extratos_ofx.PASTA_ENTRADA = PASTA_TMP_ENTRADA
        parser_extratos_ofx.PASTA_SAIDA = os.path.join(PASTA_TMP_ENTRADA, "processados_ofx")
        pasta_original = os.getcwd()
        os.chdir(PASTA_TMP_ENTRADA)
        try:
            parser_extratos_ofx.processar_ofx()
        finally:
            os.chdir(pasta_original)

    # 6. Procurar os arquivos Excel gerados e subir para o Google Drive
    arquivos_excel = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.xlsx"))
    if not arquivos_excel:
        print("\nNenhum relatório .xlsx gerado para upload.")
    else:
        print(f"\n--- Fazendo upload de {len(arquivos_excel)} relatório(s) para o Google Drive ---")
        for excel_path in arquivos_excel:
            nome_excel = os.path.basename(excel_path)
            print(f" -> Enviando: {nome_excel}")
            upload_file(service, output_folder_id, excel_path, nome_excel)

    # 7. Limpeza do ambiente temporário
    shutil.rmtree(PASTA_TMP_ENTRADA, ignore_errors=True)
    shutil.rmtree(PASTA_TMP_SAIDA, ignore_errors=True)
    print("\nExecução concluída com sucesso!")

if __name__ == "__main__":
    run_pipeline()