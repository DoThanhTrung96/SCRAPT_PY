import os
from pydub import AudioSegment

import argparse

def convert_mp4_to_mp3(input_file, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    filename = os.path.basename(input_file)
    if filename.endswith(".mp4"):
        mp3_filename = os.path.splitext(filename)[0] + ".mp3"
        mp3_filepath = os.path.join(output_folder, mp3_filename)

        print(f"Converting {filename} to MP3...")
        try:
            audio = AudioSegment.from_file(input_file, format="mp4")
            audio.export(mp3_filepath, format="mp3")
            print(f"Successfully converted {filename}")
        except Exception as e:
            print(f"Error converting {filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a single MP4 file to MP3.")
    parser.add_argument("input_file", help="The input MP4 file to convert.")
    parser.add_argument("output_folder", help="The folder to save the converted MP3 file.")
    args = parser.parse_args()

    convert_mp4_to_mp3(args.input_file, args.output_folder)
