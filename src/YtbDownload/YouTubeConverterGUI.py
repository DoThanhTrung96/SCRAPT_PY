import os
import yt_dlp
from pydub import AudioSegment
import customtkinter as ctk
from tkinter import filedialog, messagebox

def download_video(url, output_path='.'):
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        # yt-dlp returns the full path of the downloaded file
        # We need to find the actual filename from the info_dict
        # This can be tricky as it might be a merged file
        # For simplicity, let's assume it's in the output_path with a common naming convention
        # A more robust solution would involve parsing the output of ydl.download
        # For now, let's return a placeholder or try to infer the name
        # A better approach is to use the 'filepath' from the info_dict if available
        if 'filepath' in info_dict:
            return info_dict['filepath']
        else:
            # Fallback if 'filepath' is not directly available
            # This might not be accurate for all cases, especially merged formats
            return os.path.join(output_path, f"{info_dict.get('title', 'downloaded_video')}.mp4")

import subprocess

def download_video(url, output_path='.'):
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        if 'filepath' in info_dict:
            return info_dict['filepath']
        else:
            return os.path.join(output_path, f"{info_dict.get('title', 'downloaded_video')}.mp4")

class YouTubeConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader & Converter")
        self.geometry("700x400")

        # Configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4), weight=1)

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

        # Status Label
        self.status_label = ctk.CTkLabel(self, text="", wraplength=600)
        self.status_label.grid(row=4, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        self.last_downloaded_file = None

    def browse_output_path(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_path_entry.delete(0, ctk.END)
            self.output_path_entry.insert(0, folder_selected)

    def update_status(self, message, color="white"):
        self.status_label.configure(text=message, text_color=color)

    def start_download(self):
        url = self.url_entry.get()
        output_dir = self.output_path_entry.get()

        if not url:
            self.update_status("Please enter a YouTube URL.", "red")
            return
        if not output_dir:
            self.update_status("Please select an output directory.", "red")
            return

        self.update_status("Downloading video... This may take a while.", "yellow")
        self.download_button.configure(state="disabled")
        self.convert_button.configure(state="disabled")

        try:
            downloaded_filepath = download_video(url, output_dir)
            if downloaded_filepath:
                self.last_downloaded_file = downloaded_filepath
                self.update_status(f"Download complete: {os.path.basename(downloaded_filepath)}", "green")
            else:
                self.update_status("Download failed or file path could not be determined.", "red")
        except Exception as e:
            self.update_status(f"Download error: {e}", "red")
        finally:
            self.download_button.configure(state="normal")
            self.convert_button.configure(state="normal")

    def start_conversion(self):
        if not self.last_downloaded_file:
            self.update_status("No video downloaded yet to convert.", "red")
            return

        output_dir = self.output_path_entry.get()
        if not output_dir:
            self.update_status("Please select an output directory for MP3.", "red")
            return

        self.update_status("Converting to MP3...", "yellow")
        self.download_button.configure(state="disabled")
        self.convert_button.configure(state="disabled")

        try:
            # Go up two levels to find the project root from the current script location
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            python_executable = os.path.join(project_root, ".venv", "Scripts", "python.exe")
            video_converter_script = os.path.join(project_root, "src", "YtbDownload", "VideoConverter.py")
            
            # Ensure the python executable exists
            if not os.path.exists(python_executable):
                # Fallback to the system's python if not found in .venv
                python_executable = "python"

            result = subprocess.run([python_executable, video_converter_script, self.last_downloaded_file, output_dir], capture_output=True, text=True, check=True)
            
            if result.returncode == 0:
                self.update_status(f"Conversion complete: {os.path.basename(self.last_downloaded_file).replace('.mp4', '.mp3')}", "green")
            else:
                self.update_status(f"Conversion error: {result.stderr}", "red")
        except subprocess.CalledProcessError as e:
            self.update_status(f"Conversion failed: {e.stderr}", "red")
        except Exception as e:
            self.update_status(f"An unexpected error occurred: {e}", "red")
        finally:
            self.download_button.configure(state="normal")
            self.convert_button.configure(state="normal")

if __name__ == "__main__":
    ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
    ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

    app = YouTubeConverterApp()
    app.mainloop()
