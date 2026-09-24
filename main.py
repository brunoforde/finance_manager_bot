import os
import shutil
import glob
from drive_client import get_drive_service, list_files, download_file, upload_file, move_file
import parser_faturas_cartao
import parser_extratos_ofx
import parser_extratos_santander_pdf

PASTA_TMP_ENTRADA = "./temp_entrada"

def run_pipeline():
    input_folder_id = os.environ.get("DRIVE_INPUT_FOLDER_ID")
    report_output_folder_id = os.environ.get("DRIVE_REPORT_OUTPUT_FOLDER_ID")
    processed_folder_id = os.environ.get("DRIVE_PROCESSED_FOLDER_ID")
    tipo_processamento = os.environ.get("TIPO_PROCESSAMENTO", "todos")

    if not input_folder_id or not report_output_folder_id:
        print("[ERRO] Variáveis de ambiente obrigatórias não configuradas.")
        return

    os.makedirs(PASTA_TMP_ENTRADA, exist_ok=True)

    print("Conectando ao Google Drive...")
    service = get_drive_service()

    # 1. Listar arquivos na entrada
    arquivos_drive = list_files(service, input_folder_id)
    if not arquivos_drive:
        print("Nenhum arquivo para processar na pasta de entrada.")
        return

    print(f"Modo de execução selecionado: '{tipo_processamento}'")
    print(f"Foram encontrados {len(arquivos_drive)} arquivo(s). Baixando...")
    for item in arquivos_drive:
        destino = os.path.join(PASTA_TMP_ENTRADA, item['name'])
        print(f" -> Baixando: {item['name']}")
        download_file(service, item['id'], destino)

    # 2. Processar Faturas de Cartão (PDF)
    if tipo_processamento in ["todos", "faturas_cartao"]:
        pdfs = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.pdf"))
        if pdfs:
            print(f"\n--- Processando {len(pdfs)} fatura(s) PDF ---")
            pasta_original = os.getcwd()
            os.chdir(PASTA_TMP_ENTRADA)
            try:
                parser_faturas_cartao.processar_faturas()
            finally:
                os.chdir(pasta_original)
        else:
            print("\nNenhum arquivo .pdf encontrado para faturas.")

    # 3. Processar Extratos Bancários (OFX)
    if tipo_processamento in ["todos", "extratos_bancarios"]:
        ofxs = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.ofx"))
        if ofxs:
            print(f"\n--- Processando {len(ofxs)} extrato(s) OFX ---")
            pasta_original = os.getcwd()
            os.chdir(PASTA_TMP_ENTRADA)
            try:
                parser_extratos_ofx.PASTA_ENTRADA = "."
                parser_extratos_ofx.PASTA_SAIDA = "./processados_local"
                ##parser_extratos_ofx.processar_ofx()
                arquivos_sucesso_ofx = parser_extratos_ofx.processar_ofx()
            finally:
                os.chdir(pasta_original)
        else:
            print("\nNenhum arquivo .ofx encontrado para extratos.")

    # 4. Processamento Histórico Santander (PDF)
    if tipo_processamento in ["todos", "santander_pdf"]:
        pdfs = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.pdf"))
        pdfs_santander = [p for p in pdfs if any(k in os.path.basename(p).lower() for k in ["santander", "comprovante"])]
        
        if pdfs_santander:
            print(f"\n--- Processando {len(pdfs_santander)} extrato(s) Santander em PDF ---")
            pasta_original = os.getcwd()
            os.chdir(PASTA_TMP_ENTRADA)
            try:
                parser_extratos_santander_pdf.processar_extratos_santander()
            finally:
                os.chdir(pasta_original)
        else:
            print("Nenhum PDF do Santander identificado para processamento.")

    # 5. Upload dos relatórios gerados (.xlsx)
    arquivos_excel = glob.glob(os.path.join(PASTA_TMP_ENTRADA, "*.xlsx"))
    if arquivos_excel:
        print(f"\n--- Enviando {len(arquivos_excel)} relatório(s) para o Google Drive ---")
        for excel_path in arquivos_excel:
            nome_excel = os.path.basename(excel_path)
            print(f" -> Enviando: {nome_excel}")
            upload_file(service, report_output_folder_id, excel_path, nome_excel)
    else:
        print("\nNenhum arquivo Excel gerado.")

    # 6. Mover arquivos originais para 'Processadas' no Drive
    for item in arquivos_drive:
            print(f" -> Movendo: {item['name']}")
            move_file(service, item['id'], input_folder_id, processed_folder_id)
            
    # 7. Limpeza do ambiente temporário
    shutil.rmtree(PASTA_TMP_ENTRADA, ignore_errors=True)
    print("\nProcesso concluído com sucesso!")

if __name__ == "__main__":
    run_pipeline()
