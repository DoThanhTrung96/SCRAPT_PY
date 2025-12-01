import os
import re
import glob
import threading
import yt_dlp
from pydub import AudioSegment
import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess

class ProgressHook:
    """yt-dlp progress hook to update GUI in real-time"""
    def __init__(self, update_callback):
        self.update_callback = update_callback
    
    def __call__(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', 'N/A').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()
            msg = f"Downloading: {percent} | Speed: {speed} | ETA: {eta}"
            self.update_callback(msg, "yellow")
        elif d['status'] == 'finished':
            self.update_callback("Download finished, processing...", "yellow")

def download_video(url, output_path='.', progress_callback=None):
    """Download video with real-time progress updates - optimized to avoid filename issues"""
    
    # Strategy: Use windowsfilenames=True to automatically sanitize filenames for Windows
    # Force H.264 codec for maximum compatibility (AV1 not supported by many players)
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'format': 'bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': False,
        'no_warnings': False,
        'windowsfilenames': True,  # Sanitize filenames for Windows compatibility
        'merge_output_format': 'mp4',  # Ensure merged output is mp4
    }
    
    if progress_callback:
        ydl_opts['progress_hooks'] = [ProgressHook(progress_callback)]
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            
            # Get the sanitized title that was actually used
            title = ydl.prepare_filename(info_dict)
            
            # Check if file exists
            if os.path.exists(title):
                return title
            
            # Fallback: find the most recently created mp4 file
            mp4_files = glob.glob(os.path.join(output_path, "*.mp4"))
            if mp4_files:
                return max(mp4_files, key=os.path.getmtime)
            
            return None
    except Exception as e:
        raise Exception(f"Download failed: {str(e)}")

class YouTubeConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader & Converter")
        self.geometry("800x500")

        # Configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # URL Input
        self.url_label = ctk.CTkLabel(self, text="YouTube URL:")
        self.url_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.url_entry = ctk.CTkEntry(self, placeholder_text="Enter YouTube video URL")
        self.url_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # Output Path Input
        self.output_path_label = ctk.CTkLabel(self, text="Output Directory:")
        self.output_path_label.grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.output_path_entry = ctk.CTkEntry(self, placeholder_text="Select output directory")
        self.output_path_entry.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.browse_button = ctk.CTkButton(self, text="Browse", command=self.browse_output_path)
        self.browse_button.grid(row=1, column=2, padx=10, pady=10, sticky="e")

        # Download Button
        self.download_button = ctk.CTkButton(self, text="Download Video", command=self.start_download)
        self.download_button.grid(row=2, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        # Convert Button
        self.convert_button = ctk.CTkButton(self, text="Convert Last Downloaded to MP3", command=self.start_conversion)
        self.convert_button.grid(row=3, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        # Progress Bar
        self.progress_label = ctk.CTkLabel(self, text="Progress:", text_color="gray")
        self.progress_label.grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.progress_bar = ctk.CTkProgressBar(self, mode='determinate')
        self.progress_bar.set(0)
        self.progress_bar.grid(row=4, column=1, columnspan=2, padx=10, pady=5, sticky="ew")

        # Status Label
        self.status_label = ctk.CTkLabel(self, text="Ready", wraplength=700, justify="left")
        self.status_label.grid(row=5, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        self.last_downloaded_file = None
        self.is_downloading = False
        self.is_converting = False

    def browse_output_path(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_path_entry.delete(0, ctk.END)
            self.output_path_entry.insert(0, folder_selected)

    def update_status(self, message, color="white"):
        self.status_label.configure(text=message, text_color=color)
        self.update()  # Force GUI refresh

    def start_download(self):
        url = self.url_entry.get()
        output_dir = self.output_path_entry.get()

        if not url:
            self.update_status("❌ Please enter a YouTube URL.", "red")
            return
        if not output_dir:
            self.update_status("❌ Please select an output directory.", "red")
            return

        if self.is_downloading or self.is_converting:
            self.update_status("⚠️ Operation already in progress. Please wait.", "orange")
            return

        self.is_downloading = True
        self.download_button.configure(state="disabled")
        self.convert_button.configure(state="disabled")
        self.progress_bar.set(0)

        # Run download in a separate thread
        thread = threading.Thread(target=self._download_worker, args=(url, output_dir), daemon=True)
        thread.start()

    def _download_worker(self, url, output_dir):
        """Worker thread for downloading"""
        try:
            self.update_status("📥 Downloading video... This may take a while.", "yellow")
            downloaded_filepath = download_video(url, output_dir, progress_callback=self.update_status)
            
            if downloaded_filepath and os.path.exists(downloaded_filepath):
                self.last_downloaded_file = downloaded_filepath
                file_size = os.path.getsize(downloaded_filepath) / (1024 * 1024)  # MB
                self.progress_bar.set(1.0)
                self.update_status(f"✅ Download complete: {os.path.basename(downloaded_filepath)} ({file_size:.1f} MB)", "green")
            else:
                self.update_status("❌ Download failed or file path could not be determined.", "red")
                self.progress_bar.set(0)
        except Exception as e:
            self.update_status(f"❌ Download error: {str(e)}", "red")
            self.progress_bar.set(0)
        finally:
            self.is_downloading = False
            self.download_button.configure(state="normal")
            self.convert_button.configure(state="normal")

    def start_conversion(self):
        if not self.last_downloaded_file:
            self.update_status("❌ No video downloaded yet to convert.", "red")
            return

        output_dir = self.output_path_entry.get()
        if not output_dir:
            self.update_status("❌ Please select an output directory for MP3.", "red")
            return

        if self.is_downloading or self.is_converting:
            self.update_status("⚠️ Operation already in progress. Please wait.", "orange")
            return

        self.is_converting = True
        self.download_button.configure(state="disabled")
        self.convert_button.configure(state="disabled")
        self.progress_bar.set(0)

        # Run conversion in a separate thread
        thread = threading.Thread(target=self._conversion_worker, args=(output_dir,), daemon=True)
        thread.start()

    def _conversion_worker(self, output_dir):
        """Worker thread for converting to MP3"""
        try:
            self.update_status("🎵 Converting to MP3... This may take a few moments.", "yellow")
            
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            python_executable = os.path.join(project_root, ".venv", "Scripts", "python.exe")
            video_converter_script = os.path.join(project_root, "src", "YtbDownload", "VideoConverter.py")
            
            if not os.path.exists(python_executable):
                python_executable = "python"

            result = subprocess.run(
                [python_executable, video_converter_script, self.last_downloaded_file, output_dir],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                mp3_name = os.path.basename(self.last_downloaded_file).replace('.mp4', '.mp3')
                mp3_path = os.path.join(output_dir, mp3_name)
                mp3_size = os.path.getsize(mp3_path) / (1024 * 1024) if os.path.exists(mp3_path) else 0
                self.progress_bar.set(1.0)
                self.update_status(f"✅ Conversion complete: {mp3_name} ({mp3_size:.1f} MB)", "green")
            else:
                error_msg = result.stderr if result.stderr else "Unknown error"
                self.update_status(f"❌ Conversion error: {error_msg}", "red")
                self.progress_bar.set(0)
        except Exception as e:
            self.update_status(f"❌ Conversion failed: {str(e)}", "red")
            self.progress_bar.set(0)
        finally:
            self.is_converting = False
            self.download_button.configure(state="normal")
            self.convert_button.configure(state="normal")

if __name__ == "__main__":
    ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
    ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

    app = YouTubeConverterApp()
    app.mainloop()
