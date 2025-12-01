#!/usr/bin/env python3
"""
Debug script to test YouTube download with a long video
"""

import os
import sys
import yt_dlp
from pathlib import Path
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

url = "https://www.youtube.com/watch?v=Dtx4kNXj0OQ"
output_path = r"C:\Users\ailam\OneDrive\BACKUP\HOME\SCRAPT_PY\YtbDownload"

print("[MOVIE] Testing YouTube download...")
print(f"URL: {url}")
print(f"Output path: {output_path}")
print(f"Video length: >30 mins")
print("-" * 80)

# Ensure output directory exists
os.makedirs(output_path, exist_ok=True)

class ProgressHook:
    """yt-dlp progress hook"""
    def __call__(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', 'N/A').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()
            total = d.get('_total_bytes_str', 'N/A').strip()
            print(f"[DOWNLOADING] {percent} | Speed: {speed} | Total: {total} | ETA: {eta}", end='\r')
        elif d['status'] == 'finished':
            print("\n[OK] Download finished, processing...")
        elif d['status'] == 'error':
            print(f"\n[ERROR] {d}")

try:
    print("\n[INFO] Fetching video info...")
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'format': 'bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': False,
        'no_warnings': False,
        'windowsfilenames': True,  # KEY FIX: Sanitize filenames for Windows
        'merge_output_format': 'mp4',
        'progress_hooks': [ProgressHook()],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("[INFO] Starting download...")
        info_dict = ydl.extract_info(url, download=True)
        
        # Use yt-dlp's prepare_filename to get the actual filepath
        filepath = ydl.prepare_filename(info_dict)
        print(f"\n[INFO] Expected filepath: {filepath}")
        
        # Check if file exists at expected path
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath) / (1024 * 1024)
            print(f"[SUCCESS] File saved: {filepath}")
            print(f"[SIZE] File size: {file_size:.1f} MB")
            print(f"[TITLE] Title: {info_dict.get('title', 'N/A')}")
            print(f"[DURATION] Duration: {info_dict.get('duration', 0) / 60:.1f} minutes")
        else:
            # Search for the actual file
            import glob
            mp4_files = glob.glob(os.path.join(output_path, "*.mp4"))
            if mp4_files:
                actual_file = max(mp4_files, key=os.path.getmtime)
                file_size = os.path.getsize(actual_file) / (1024 * 1024)
                print(f"[SUCCESS] File found at: {actual_file}")
                print(f"[SIZE] File size: {file_size:.1f} MB")
            else:
                print(f"[ERROR] No MP4 files found in {output_path}")
            
except Exception as e:
    print(f"\n[CRITICAL] {type(e).__name__}")
    print(f"[ERROR MESSAGE] {str(e)}")
    import traceback
    print("\n[TRACEBACK]")
    traceback.print_exc()
    sys.exit(1)
