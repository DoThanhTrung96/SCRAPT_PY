import os
from pydub import AudioSegment

def convert_single_mp4_to_mp3(input_filepath, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    filename = os.path.basename(input_filepath)
    mp3_filename = os.path.splitext(filename)[0] + ".mp3"
    mp3_filepath = os.path.join(output_folder, mp3_filename)

    print(f"Converting {filename} to MP3...")
    try:
        audio = AudioSegment.from_file(input_filepath, format="webm")
        audio.export(mp3_filepath, format="mp3")
        print(f"Successfully converted {filename}")
    except Exception as e:
        print(f"Error converting {filename}: {e}")

if __name__ == "__main__":
    input_file = r"C:\Users\ailam\OneDrive\BACKUP\HOME\SCRAPT_PY\YtbDownload\Lady Gaga, Bruno Mars - Die With A Smile (Official Music Video).webm"
    output_directory = r"C:\Users\ailam\OneDrive\BACKUP\HOME\SCRAPT_PY\YtbDownload\mp3_converted"
    convert_single_mp4_to_mp3(input_file, output_directory)
