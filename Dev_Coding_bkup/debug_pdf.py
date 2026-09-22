import pdfplumber
import glob

arquivos = glob.glob("*.pdf")
print(f"Ficheiros encontrados: {arquivos}")

if arquivos:
    with pdfplumber.open(arquivos[0]) as pdf:
        print(f"Total de páginas: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            texto = page.extract_text() or ""
            print(f"\n--- PÁGINA {i+1} (Primeiros 300 caracteres) ---")
            print(texto[:300])
            if "Conta Corrente" in texto or "CONTA CORRENTE" in texto:
                print(f"-> 'Conta Corrente' ENCONTRADO na página {i+1}!")