#!/usr/bin/env python3
"""
drive_downloader_robust_gui.py

Robust Google Drive folder downloader with resume (.part), retries, exponential backoff,
per-file progress, and skip-if-complete (size/md5) logic. Uses interactive OAuth (token.json).
Set CLIENT_SECRETS env var to point to your client_secrets.json.
"""

import os
import io
import sys
import re
import threading
import time
import socket
import hashlib
from pathlib import Path
from datetime import datetime
import traceback

import customtkinter as ctk
from tkinter import filedialog, messagebox

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

# --- Configuration ---
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Determine project root for token.json and other assets
if getattr(sys, 'frozen', False):
    # Running as a bundled executable
    project_root = os.path.dirname(sys.executable)
else:
    # Running as a normal script
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

CLIENT_SECRETS_PATH_ENV = os.environ.get('CLIENT_SECRETS')
TOKEN_PATH = os.path.join(project_root, 'token.json')

# Download retry/backoff tunables
CHUNK_SIZE = 8 * 1024 * 1024        # 8 MiB per chunk (tunable)
MAX_CHUNK_RETRIES = 5               # per-chunk retries
MAX_FILE_RETRIES = 5                # whole-file retries
INITIAL_BACKOFF = 1.0               # seconds
BACKOFF_FACTOR = 2.0
MAX_BACKOFF_SECONDS = 120.0

# Behavior toggles
FORCE_REEXPORT_NATIVE = False       # if True, re-export Google Docs/Sheets/Slides even if output exists
FAILED_ITEMS_PATH = "failed_downloads.txt"

# --- Utilities ---
def _safe_sleep_backoff(attempt, http_status=None):
    base = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
    if http_status is not None and (http_status == 429 or 500 <= http_status < 600):
        base *= 2.0
    delay = min(base, MAX_BACKOFF_SECONDS)
    time.sleep(delay)

def md5_of_file(path: Path, chunk=8192):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()

# --- Auth ---
def get_credentials():
    creds = None
    if not CLIENT_SECRETS_PATH_ENV or not os.path.exists(CLIENT_SECRETS_PATH_ENV):
        raise FileNotFoundError("CLIENT_SECRETS environment variable not set or path is invalid.")
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH_ENV, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return creds

# --- Drive helpers ---
def extract_file_id(drive_url_or_id: str) -> str:
    s = drive_url_or_id.strip()
    if re.match(r'^[a-zA-Z0-9_-]{10,}$', s):
        return s
    m = re.search(r'/folders/([a-zA-Z0-9_-]+)', s)
    if m: return m.group(1)
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', s)
    if m: return m.group(1)
    m = re.search(r'id=([a-zA-Z0-9_-]+)', s)
    if m: return m.group(1)
    raise ValueError("Could not extract file or folder id from input")

def list_folder_children(service, folder_id):
    page_token = None
    q = f"'{folder_id}' in parents and trashed = false"
    fields = "nextPageToken, files(id, name, mimeType, size, md5Checksum)"
    while True:
        resp = service.files().list(q=q, spaces='drive', fields=fields, pageToken=page_token, pageSize=1000).execute()
        for f in resp.get('files', []):
            yield f
        page_token = resp.get('nextPageToken')
        if not page_token:
            break

def get_file_metadata(service, file_id):
    fields = 'id,name,mimeType,size,md5Checksum'
    return service.files().get(fileId=file_id, fields=fields).execute()

# --- Skip / resume checks ---
def should_skip_binary_file(local_path: Path, drive_size, drive_md5, log_callback):
    if not local_path.exists():
        return False
    try:
        local_size = local_path.stat().st_size
    except Exception:
        return False
    drive_size_int = None
    if drive_size is not None:
        try:
            drive_size_int = int(drive_size)
        except Exception:
            drive_size_int = None
    if drive_size_int is not None and local_size == drive_size_int:
        log_callback(f"Skipping {local_path.name} (size matches: {local_size} bytes)")
        return True
    if drive_md5:
        try:
            local_md5 = md5_of_file(local_path)
            if local_md5 == drive_md5:
                log_callback(f"Skipping {local_path.name} (md5 matches)")
                return True
        except Exception as e:
            log_callback(f"Could not compute md5 for {local_path.name}: {e}")
    return False

# --- Robust download functions ---
def download_file_to_path_with_retries(service, file_meta, out_path: Path, log_callback, progress_percent_callback):
    """
    file_meta: dict from get_file_metadata/list folder listing
    out_path: final Path
    """
    file_id = file_meta['id']
    filename = file_meta.get('name') or file_id
    drive_size = file_meta.get('size')
    drive_md5 = file_meta.get('md5Checksum')

    # Skip if final file matches Drive (size or md5)
    if should_skip_binary_file(out_path, drive_size, drive_md5, log_callback):
        progress_percent_callback(100)
        return str(out_path)

    temp_path = out_path.with_suffix(out_path.suffix + ".part") if out_path.suffix else Path(str(out_path) + ".part")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for file_attempt in range(1, MAX_FILE_RETRIES + 1):
        try:
            mode = "r+b" if temp_path.exists() else "wb"
            with open(temp_path, mode) as fh:
                if mode == "r+b":
                    fh.seek(0, os.SEEK_END)
                request = service.files().get_media(fileId=file_id)
                downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)
                done = False
                chunk_attempt = 0
                last_pct = -1
                while not done:
                    try:
                        status, done = downloader.next_chunk()
                        chunk_attempt = 0
                        if status:
                            pct = int(status.progress() * 100)
                            if pct != last_pct:
                                last_pct = pct
                                log_callback(f"Downloading {filename}: {pct}%")
                                progress_percent_callback(pct)
                    except HttpError as exc:
                        status_code = None
                        try:
                            status_code = int(exc.resp.status)
                        except Exception:
                            pass
                        chunk_attempt += 1
                        log_callback(f"HttpError chunk ({chunk_attempt}/{MAX_CHUNK_RETRIES}) for {filename}: status={status_code} error={exc}")
                        if chunk_attempt > MAX_CHUNK_RETRIES:
                            raise
                        _safe_sleep_backoff(chunk_attempt, http_status=status_code)
                        # recreate downloader to resume from file pointer
                        request = service.files().get_media(fileId=file_id)
                        downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)
                        continue
                    except (socket.timeout, socket.error, OSError) as exc:
                        chunk_attempt += 1
                        log_callback(f"Network error chunk ({chunk_attempt}/{MAX_CHUNK_RETRIES}) for {filename}: {exc}")
                        if chunk_attempt > MAX_CHUNK_RETRIES:
                            raise
                        _safe_sleep_backoff(chunk_attempt)
                        request = service.files().get_media(fileId=file_id)
                        downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)
                        continue

            # finished, move temp to final
            temp_path.replace(out_path)
            log_callback(f"Saved: {out_path}")
            progress_percent_callback(100)
            # optional integrity check
            if drive_md5:
                try:
                    local_md5 = md5_of_file(out_path)
                    if local_md5 != drive_md5:
                        log_callback(f"Warning: md5 mismatch for {out_path.name}")
                except Exception:
                    pass
            return str(out_path)

        except Exception as e:
            log_callback(f"Failed attempt {file_attempt}/{MAX_FILE_RETRIES} for {filename}: {e}")
            if file_attempt >= MAX_FILE_RETRIES:
                raise
            _safe_sleep_backoff(file_attempt)

def export_google_workspace_file_with_retries(service, file_meta, mime_type, out_path: Path, log_callback, progress_percent_callback):
    file_id = file_meta['id']
    filename = file_meta.get('name') or file_id

    # Skip if exists and not forced
    if out_path.exists() and not FORCE_REEXPORT_NATIVE:
        log_callback(f"Skipping export {out_path.name} (already exists)")
        progress_percent_callback(100)
        return str(out_path)

    temp_path = out_path.with_suffix(out_path.suffix + ".part") if out_path.suffix else Path(str(out_path) + ".part")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for file_attempt in range(1, MAX_FILE_RETRIES + 1):
        try:
            mode = "r+b" if temp_path.exists() else "wb"
            with open(temp_path, mode) as fh:
                if mode == "r+b":
                    fh.seek(0, os.SEEK_END)
                request = service.files().export_media(fileId=file_id, mimeType=mime_type)
                downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)
                done = False
                chunk_attempt = 0
                last_pct = -1
                while not done:
                    try:
                        status, done = downloader.next_chunk()
                        chunk_attempt = 0
                        if status:
                            pct = int(status.progress() * 100)
                            if pct != last_pct:
                                last_pct = pct
                                log_callback(f"Exporting {out_path.name}: {pct}%")
                                progress_percent_callback(pct)
                    except HttpError as exc:
                        status_code = None
                        try:
                            status_code = int(exc.resp.status)
                        except Exception:
                            pass
                        chunk_attempt += 1
                        log_callback(f"HttpError export chunk ({chunk_attempt}/{MAX_CHUNK_RETRIES}) for {out_path.name}: status={status_code} error={exc}")
                        if chunk_attempt > MAX_CHUNK_RETRIES:
                            raise
                        _safe_sleep_backoff(chunk_attempt, http_status=status_code)
                        request = service.files().export_media(fileId=file_id, mimeType=mime_type)
                        downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)
                        continue
                    except (socket.timeout, socket.error, OSError) as exc:
                        chunk_attempt += 1
                        log_callback(f"Network error export chunk ({chunk_attempt}/{MAX_CHUNK_RETRIES}) for {out_path.name}: {exc}")
                        if chunk_attempt > MAX_CHUNK_RETRIES:
                            raise
                        _safe_sleep_backoff(chunk_attempt)
                        request = service.files().export_media(fileId=file_id, mimeType=mime_type)
                        downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNK_SIZE)
                        continue

            temp_path.replace(out_path)
            log_callback(f"Exported: {out_path}")
            progress_percent_callback(100)
            return str(out_path)

        except Exception as e:
            log_callback(f"Failed export attempt {file_attempt}/{MAX_FILE_RETRIES} for {out_path.name}: {e}")
            if file_attempt >= MAX_FILE_RETRIES:
                raise
            _safe_sleep_backoff(file_attempt)

# --- Recursive folder download with failure logging ---
def download_folder_recursive(service, folder_id, target_dir, log_callback, progress_percent_callback, failed_items):
    meta = service.files().get(fileId=folder_id, fields='id,name,mimeType').execute()
    folder_name = meta.get('name') or folder_id
    base_path = Path(target_dir) / folder_name
    log_callback(f"Starting folder: {folder_name}")
    _download_folder_contents(service, folder_id, base_path, log_callback, progress_percent_callback, failed_items)

def _download_folder_contents(service, folder_id, current_path: Path, log_callback, progress_percent_callback, failed_items):
    current_path.mkdir(parents=True, exist_ok=True)
    for item in list_folder_children(service, folder_id):
        item_id = item['id']
        name = item['name']
        mime = item.get('mimeType', '')
        try:
            meta = get_file_metadata(service, item_id)
            if meta.get('mimeType') == 'application/vnd.google-apps.folder':
                log_callback(f"Entering folder: {name}")
                _download_folder_contents(service, item_id, current_path / name, log_callback, progress_percent_callback, failed_items)
            else:
                if meta.get('mimeType') == 'application/vnd.google-apps.document':
                    out_file = current_path / f"{name}.pdf"
                    log_callback(f"Exporting Google Doc: {name}")
                    export_google_workspace_file_with_retries(service, meta, 'application/pdf', out_file, log_callback, progress_percent_callback)
                elif meta.get('mimeType') == 'application/vnd.google-apps.spreadsheet':
                    out_file = current_path / f"{name}.xlsx"
                    log_callback(f"Exporting Google Sheet: {name}")
                    export_google_workspace_file_with_retries(service, meta, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', out_file, log_callback, progress_percent_callback)
                elif meta.get('mimeType') == 'application/vnd.google-apps.presentation':
                    out_file = current_path / f"{name}.pdf"
                    log_callback(f"Exporting Google Slide: {name}")
                    export_google_workspace_file_with_retries(service, meta, 'application/pdf', out_file, log_callback, progress_percent_callback)
                else:
                    out_file = current_path / name
                    log_callback(f"Downloading file: {name}")
                    download_file_to_path_with_retries(service, meta, out_file, log_callback, progress_percent_callback)
                # small pause between files to reduce throttling
                time.sleep(0.2)
        except Exception as e:
            log_callback(f"ERROR downloading {name}: {e}")
            failed_items.append({'id': item_id, 'name': name, 'error': str(e)})
            # continue with other files

# --- GUI ---
class GdriveDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Google Drive Downloader — robust resume & backoff")
        self.geometry("900x600")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure((0,1,2,3,4,5), weight=1)

        self.url_label = ctk.CTkLabel(self, text="Google Drive Folder URL or ID:")
        self.url_label.grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.url_entry = ctk.CTkEntry(self, placeholder_text="Enter folder URL or folder id")
        self.url_entry.grid(row=0, column=1, padx=10, pady=6, sticky="ew", columnspan=2)

        self.output_path_label = ctk.CTkLabel(self, text="Output Directory:")
        self.output_path_label.grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.output_path_entry = ctk.CTkEntry(self, placeholder_text="Select output directory")
        self.output_path_entry.grid(row=1, column=1, padx=10, pady=6, sticky="ew")
        self.browse_button = ctk.CTkButton(self, text="Browse", command=self.browse_output_path)
        self.browse_button.grid(row=1, column=2, padx=10, pady=6, sticky="e")

        self.download_button = ctk.CTkButton(self, text="Download Folder", command=self.start_download_thread)
        self.download_button.grid(row=2, column=0, columnspan=3, padx=10, pady=8, sticky="ew")

        # options
        self.force_export_var = ctk.StringVar(value=str(FORCE_REEXPORT_NATIVE))
        self.force_export_check = ctk.CTkCheckBox(self, text="Force re-export native Google files (Docs/Sheets/Slides)", command=self.toggle_force_export)
        self.force_export_check.grid(row=3, column=0, columnspan=3, padx=12, pady=4, sticky="w")
        if FORCE_REEXPORT_NATIVE:
            self.force_export_check.select()

        self.status_label = ctk.CTkLabel(self, text="", wraplength=860, anchor="w", justify="left")
        self.status_label.grid(row=4, column=0, columnspan=3, padx=12, pady=6, sticky="nsew")

        self.progress = ctk.CTkProgressBar(self, width=860)
        self.progress.grid(row=5, column=0, columnspan=3, padx=12, pady=6, sticky="ew")
        self.progress.set(0.0)

        self.log_box = ctk.CTkTextbox(self, width=880, height=300)
        self.log_box.grid(row=6, column=0, columnspan=3, padx=12, pady=8, sticky="nsew")
        self.log_box.configure(state="disabled")

    def toggle_force_export(self):
        global FORCE_REEXPORT_NATIVE
        FORCE_REEXPORT_NATIVE = not FORCE_REEXPORT_NATIVE
        self.append_log(f"Force re-export native set to {FORCE_REEXPORT_NATIVE}")

    def browse_output_path(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_path_entry.delete(0, ctk.END)
            self.output_path_entry.insert(0, folder_selected)

    def append_log(self, message, color="black"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        def _append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{timestamp}] {message}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
            self.status_label.configure(text=message)
        self.after(0, _append)

    def set_progress_percent(self, pct):
        def _set():
            self.progress.set(max(0.0, min(1.0, pct / 100.0)))
        self.after(0, _set)

    def start_download_thread(self):
        t = threading.Thread(target=self.download_logic, daemon=True)
        t.start()

    def download_logic(self):
        self.download_button.configure(state="disabled")
        failed_items = []
        try:
            url = self.url_entry.get().strip()
            out_dir = self.output_path_entry.get().strip()
            if not url or not out_dir:
                self.append_log("Folder URL/ID and output directory are required.", "red")
                messagebox.showwarning("Input required", "Folder URL/ID and output directory are required.")
                return
            self.append_log("Authenticating...")
            creds = get_credentials()
            service = build('drive', 'v3', credentials=creds, cache_discovery=False)

            try:
                folder_id = extract_file_id(url)
            except ValueError as e:
                self.append_log(f"Invalid folder URL/ID: {e}", "red")
                messagebox.showerror("Invalid URL/ID", str(e))
                return

            self.append_log(f"Starting download for folder id: {folder_id}")
            download_folder_recursive(service, folder_id, out_dir, lambda msg: self.append_log(msg), lambda pct: self.set_progress_percent(pct), failed_items)
            self.append_log("Folder download finished.")
        except FileNotFoundError as e:
            self.append_log(str(e), "red")
            messagebox.showerror("Configuration error", str(e))
        except Exception as e:
            tb = traceback.format_exc()
            self.append_log(f"An unexpected error occurred: {e}\n{tb}", "red")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        finally:
            # Write failed items log if any
            if failed_items:
                try:
                    with open(FAILED_ITEMS_PATH, 'w', encoding='utf-8') as f:
                        for it in failed_items:
                            f.write(f"{it.get('id')}\t{it.get('name')}\t{it.get('error')}\n")
                    self.append_log(f"Wrote failed items to {FAILED_ITEMS_PATH}")
                except Exception as e:
                    self.append_log(f"Could not write failed items file: {e}")
            self.download_button.configure(state="normal")
            self.after(800, lambda: self.set_progress_percent(0))

# --- Run ---
if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = GdriveDownloaderApp()
    app.mainloop()
