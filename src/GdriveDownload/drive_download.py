import os
import io
import sys
import re
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# If modifying scopes, delete token.json
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
# Read the client secrets path from an environment variable
CLIENT_SECRETS_PATH = os.environ.get('CLIENT_SECRETS')
TOKEN_PATH = 'token.json'

def get_credentials():
    creds = None
    if not CLIENT_SECRETS_PATH or not os.path.exists(CLIENT_SECRETS_PATH):
        print("Error: CLIENT_SECRETS environment variable not set or path is invalid.")
        sys.exit(1)
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request=None)  # google-auth will refresh automatically via client library if needed
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # save for next run
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds

def extract_file_id(drive_url_or_id: str) -> str:
    # Accept raw id or typical Drive share/view URLs
    # Examples supported:
    # - 1abcDEFghiJkL...
    # - https://drive.google.com/file/d/FILE_ID/view?usp=...
    # - https://drive.google.com/open?id=FILE_ID
    s = drive_url_or_id.strip()
    # if looks like an id already (typical length and chars)
    if re.match(r'^[a-zA-Z0-9_-]{10,}$', s):
        return s
    # try patterns
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', s)
    if m:
        return m.group(1)
    m = re.search(r'id=([a-zA-Z0-9_-]+)', s)
    if m:
        return m.group(1)
    raise ValueError("Could not extract file id from input")

def download_file(service, file_id: str, out_dir: str):
    # Get metadata
    meta = service.files().get(fileId=file_id, fields='id,name,mimeType,size').execute()
    filename = meta.get('name') or f'download_{file_id}'
    out_path = Path(out_dir) / filename
    mime = meta.get('mimeType', '')

    print(f"File id: {file_id}")
    print(f"Filename from Drive: {filename}")
    print(f"MIME type: {mime}")
    # For Google Workspace native files (Docs, Sheets, Slides) you must export
    if mime == 'application/vnd.google-apps.document':
        request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        out_path = out_path.with_suffix('.pdf')
    elif mime == 'application/vnd.google-apps.spreadsheet':
        request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        out_path = out_path.with_suffix('.xlsx')
    elif mime == 'application/vnd.google-apps.presentation':
        request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        out_path = out_path.with_suffix('.pdf')
    else:
        # Regular binary file: download via media endpoint
        request = service.files().get_media(fileId=file_id)

    # Download with chunks (works for large files)
    fh = io.FileIO(out_path, mode='wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    try:
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"Download progress: {int(status.progress() * 100)}%")
        print(f"Saved to: {out_path}")
    finally:
        fh.close()
    return str(out_path)

def main():
    if len(sys.argv) < 3:
        print("Usage: python drive_download.py <drive_url_or_file_id> <output_folder>")
        sys.exit(1)
    input_id_or_url = sys.argv[1]
    out_dir = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)

    try:
        file_id = extract_file_id(input_id_or_url)
    except ValueError as e:
        print("Error:", e)
        sys.exit(1)

    try:
        downloaded = download_file(service, file_id, out_dir)
        print("Download complete:", downloaded)
    except Exception as e:
        print("Download failed:", e)
        sys.exit(1)

if __name__ == '__main__':
    main()
