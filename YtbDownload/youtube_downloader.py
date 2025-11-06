
import yt_dlp

def download_video(url, output_path='.'):
    ydl_opts = {
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

if __name__ == "__main__":
    video_url = "https://www.youtube.com/watch?v=kPa7bsKwL-c&list=PLhio793SKAfQH1TXkQpLmZyrWVfGAJ3bs&index=4&pp=gAQBiAQB8AUB"
    download_video(video_url, output_path=r"C:\Users\ailam\OneDrive\BACKUP\HOME\SCRAPT_PY\YtbDownload")
