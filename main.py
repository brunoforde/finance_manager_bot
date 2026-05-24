import telebot
from telebot import types
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from datetime import datetime
import re
import os
from dotenv import load_dotenv 
import tempfile # Usado para criar arquivos temporários na memória/disco

# --- CARREGA AS VARIÁVEIS DE AMBIENTE (.env) ---
load_dotenv()

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
SPREADSHEET_NAME = os.getenv('SPREADSHEET_NAME')
DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')
JSON_CREDENTIALS = os.getenv('JSON_CREDENTIALS')

WORKSHEET_DADOS = 'Dados'   # Nome da aba onde entram os lançamentos
WORKSHEET_DASH = 'Dashboard' # Nome da aba onde estão os cálculos

# --- DICIONÁRIO DE CATEGORIAS INTELIGENTE ---
# Adapte este dicionário conforme seus gastos!
KEYWORD_MAP = {
    'uber': 'Transporte',
    '99': 'Transporte',
    'posto': 'Transporte',
    'mercado': 'Alimentação/Lazer',
    'ifood': 'Alimentação/Lazer',
    'aluguel': 'Moradia',
    'salario': 'Salário',
    'investimento': 'Investimentos'
}

CATEGORIAS_PADRAO = ['Salário', 'Moradia', 'Alimentação/Lazer', 'Transporte', 'Investimentos', 'Outros']


# Verifica se as chaves cruciais foram carregadas
if not all([TELEGRAM_TOKEN, SPREADSHEET_NAME, DRIVE_FOLDER_ID, JSON_CREDENTIALS]):
    print("ERRO: Uma ou mais variáveis cruciais estão faltando no arquivo .env.")
    print("Verifique se o arquivo .env existe e está preenchido.")
    exit()

# --- CONFIGURAÇÃO DAS APIS GOOGLE ---
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    # AUTENTICAÇÃO: ESTA LINHA DÁ ERRO SE O JSON ESTIVER VAZIO/INVÁLIDO
    creds = Credentials.from_service_account_file(JSON_CREDENTIALS, scopes=scope)
    client_sheets = gspread.authorize(creds)
    service_drive = build('drive', 'v3', credentials=creds)
except Exception as e:
    print(f"ERRO CRÍTICO na autenticação do Google: {e}")
    print("Verifique se o arquivo 'credentials.json' está correto e na pasta raiz.")
    exit()


# --- INICIALIZAÇÃO DO BOT ---
bot = telebot.TeleBot(TELEGRAM_TOKEN)
user_data = {}


# --- FUNÇÕES DE SERVIÇO (DRIVE E SHEETS) ---

def upload_to_drive(file_path, file_name):
    """Sobe o arquivo para o Drive e retorna o Link de visualização."""
    file_metadata = {
        'name': file_name,
        'parents': [DRIVE_FOLDER_ID]
    }
    # MIME type para JPEGs
    media = MediaFileUpload(file_path, mimetype='image/jpeg') 
    
    file = service_drive.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    return file.get('webViewLink')

def salvar_sheets(chat_id, categoria):
    """Salva os dados coletados na planilha."""
    if chat_id not in user_data: 
        return False
    
    dados = user_data[chat_id]
    
    # Ordem das colunas: Data | Descrição | Categoria | Tipo | Valor | Meio de Pagamento | Link Comprovante
    row = [
        dados['data'], 
        dados['descricao'], 
        categoria, 
        dados['tipo'],
        dados['valor'], 
        dados['meio de pagamento'],
        dados.get('link_drive', '')
    ]
    
    try:
        sheet = client_sheets.open(SPREADSHEET_NAME).worksheet(WORKSHEET_DADOS)
        sheet.append_row(row)
        del user_data[chat_id]
        return True
    except Exception as e:
        print(f"ERRO SHEETS: Falha ao adicionar linha. {e}")
        return False

# --- LÓGICA DE PARSE E CATEGORIZAÇÃO ---

def parse_message(text):
    """Extrai valor e descrição da mensagem."""
    # Tenta encontrar um valor numérico (aceita 10,50 ou 10.50)
    match = re.search(r'(\d+[\.,]?\d*)', text)
    if match:
        valor_str = match.group(1).replace(',', '.')
        valor = float(valor_str)
        descricao = text.replace(match.group(1), '').strip()
        return valor, descricao
    return None, text

def processar_lancamento(chat_id, texto, link_comprovante=''):
    """Processa o texto ou legenda e prepara os dados para salvar."""
    valor, descricao = parse_message(texto)
    
    if valor is None:
        return False, "Não entendi o valor. Tente: '50.00 Pizza'"

    # Tenta categorizar automaticamente
    categoria_detectada = 'Outros'
    found = False
    for key, cat in KEYWORD_MAP.items():
        if key.lower() in descricao.lower():
            categoria_detectada = cat
            found = True
            break
    
    # Salva temporariamente os dados
    user_data[chat_id] = {
        'data': datetime.now().strftime('%d/%m/%Y'),
        'descricao': descricao,
        'valor': valor,
        'categoria': categoria_detectada,
        'link_drive': link_comprovante
    }
    return True, categoria_detectada if found else None

# --- HANDLERS DO BOT ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Olá! Envie o gasto no formato: 'Valor Descrição' ou uma foto com a legenda.")

@bot.message_handler(commands=['saldo', 'resumo'])
def ver_saldo(message):
    bot.reply_to(message, "🔄 Buscando informações atualizadas...")
    try:
        sheet = client_sheets.open(SPREADSHEET_NAME).worksheet(WORKSHEET_DASH)
        
        # AJUSTE AQUI AS CÉLULAS DA SUA ABA DASHBOARD!
        # Ex: B2=Total Gasto, C2=Saldo Atual, D2=Gasto Alimentação
        valores = sheet.get('B2:D2') 
        
        if valores and valores[0]:
            total_gasto = valores[0][0]
            saldo_atual = valores[0][1]
            gasto_alim = valores[0][2]
            
            resposta = (
                f"*Resumo Financeiro*\n\n"
                f"Total Gasto: R$ {total_gasto}\n"
                f"Saldo Atual: R$ {saldo_atual}\n"
                f"Alimentação: R$ {gasto_alim}"
            )
            bot.reply_to(message, resposta, parse_mode='Markdown')
        else:
            bot.reply_to(message, "Não encontrei os valores na aba Dashboard. Verifique as fórmulas.")
            
    except Exception as e:
        print(f"ERRO SALDO: {e}")
        bot.reply_to(message, "Erro ao buscar saldo. Verifique a aba 'Dashboard'.")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    legenda = message.caption if message.caption else ""
    
    if not legenda:
        bot.reply_to(message, "Recebi a foto! Por favor, edite a foto ou envie uma mensagem com o valor e a descrição.")
        return

    bot.send_message(chat_id, "⏳ Recebido! Subindo comprovante para o Google Drive...")

    try:
        # 1. Baixa a foto para um arquivo temporário
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Cria um arquivo temporário no sistema
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
            temp_file.write(downloaded_file)
            temp_path = temp_file.name
        
        # 2. Sobe pro Drive
        nome_drive = f"Recibo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{legenda[:20].strip()}.jpg"
        link = upload_to_drive(temp_path, nome_drive)
        
        # 3. Deleta o temporário
        os.remove(temp_path)

        # 4. Processa os dados da legenda
        sucesso, categoria_detectada = processar_lancamento(chat_id, legenda, link)
        
        if sucesso:
            if categoria_detectada:
                finalizar_salvamento(chat_id, categoria_detectada, message)
            else:
                enviar_botoes_categoria(chat_id, user_data[chat_id]['valor'], user_data[chat_id]['descricao'])
        
    except Exception as e:
        print(f"ERRO UPLOAD FOTO/PROCESSAMENTO: {e}")
        bot.send_message(chat_id, f"❌ Erro ao processar a foto. Tente novamente ou use texto.")


@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    
    # Ignora comandos que já têm handler específico
    if message.text.startswith('/'):
        return
        
    sucesso, resultado = processar_lancamento(chat_id, message.text)
    
    if not sucesso:
        bot.reply_to(message, resultado)
        return

    # Se a categoria foi detectada automaticamente (resultado = categoria_detectada)
    if resultado: 
        finalizar_salvamento(chat_id, resultado, message)
    # Se a categoria não foi detectada (resultado = None), pede o botão
    else: 
        enviar_botoes_categoria(chat_id, user_data[chat_id]['valor'], user_data[chat_id]['descricao'])


# --- CALLBACKS E FINALIZAÇÃO ---

def enviar_botoes_categoria(chat_id, valor, desc):
    """Envia a mensagem com os botões de categorias."""
    markup = types.InlineKeyboardMarkup()
    for c in CATEGORIAS_PADRAO:
        markup.add(types.InlineKeyboardButton(c, callback_data=f"cat_{c}"))
    bot.send_message(chat_id, f"R$ {valor:.2f} - {desc}\nQual a categoria?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def callback_cat(call):
    categoria = call.data.split('_')[1]
    chat_id = call.message.chat.id
    
    if salvar_sheets(chat_id, categoria):
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, 
                              text=f"✅ Registrado em {categoria}!")
    else:
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, 
                              text="❌ Erro ao salvar na planilha.")

def finalizar_salvamento(chat_id, categoria, message_obj):
    """Função final para salvar na planilha após categorização automática."""
    if salvar_sheets(chat_id, categoria):
        link = user_data.get(chat_id, {}).get('link_drive', 'Nenhum')
        bot.reply_to(message_obj, f"✅ Salvo em {categoria}!\nLink Comprovante: {link}")
    else:
        bot.reply_to(message_obj, "❌ Erro ao salvar na planilha.")


# --- RODAR O BOT ---
print("Bot Rodando...")
bot.polling(none_stop=True)