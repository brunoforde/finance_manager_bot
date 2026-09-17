import io
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    sa_info = json.loads(os.environ["GCP_SA_KEY"])
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def list_files(service, folder_id):
    """Lista apenas arquivos válidos, ignorando pastas ou itens na lixeira."""
    query = (
        f"'{folder_id}' in parents and "
        f"trashed = false and "
        f"mimeType != 'application/vnd.google-apps.folder'"
    )
    results = service.files().list(
        q=query, 
        fields="files(id, name, mimeType)"
    ).execute()
    return results.get('files', [])

def download_file(service, file_id, destination_path):
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(destination_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

def upload_file(service, folder_id, file_path, file_name):
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(
        file_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

def move_file(service, file_id, current_folder_id, target_folder_id):
    """Move um arquivo da pasta de entrada para a pasta de processadas no Drive."""
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=current_folder_id,
        fields='id, parents'
    ).execute()
