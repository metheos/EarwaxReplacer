# Import important libraries

import os
import gc
import glob
import json
import numpy as np
import torch
import soundfile as sf
import pyrubberband as pyrb
import winreg
from scipy.io import wavfile
from scipy.signal import stft, lfilter, butter
from pydub import AudioSegment
from TTS.api import TTS
import sys
import re

cwd = os.getcwd()

def get_steam_libraries():
    libraries = []
    try:
        # Open the Steam registry key
        steam_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(steam_key, "InstallPath")
        libraries.append(os.path.join(steam_path, "steamapps"))
        winreg.CloseKey(steam_key)

        # Check for additional Steam libraries
        library_folders_file = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.exists(library_folders_file):
            with open(library_folders_file, 'r') as f:
                for line in f:
                    if 'path' in line:
                        path = line.split('"')[3].replace('\\\\', '\\')
                        libraries.append(os.path.join(path, "steamapps"))
    except Exception as e:
        print(f"Error finding Steam libraries: {e}")
    return libraries

def find_jackbox_party_pack_2(libraries):
    for library in libraries:
        appmanifest_path = os.path.join(library, "appmanifest_397460.acf")
        if os.path.exists(appmanifest_path):
            with open(appmanifest_path, 'r') as f:
                for line in f:
                    if '"installdir"' in line:
                        install_dir = line.split('"')[3]
                        game_path = os.path.join(library, "common", install_dir)
                        return game_path
    return None

# Locate the installation path for The Jackbox Party Pack 2
steam_libraries = get_steam_libraries()
jackbox_path = find_jackbox_party_pack_2(steam_libraries)
if jackbox_path:
    print(f"The Jackbox Party Pack 2 is installed at: {jackbox_path}")
else:
    print("The Jackbox Party Pack 2 installation path could not be found.")
    prompt = input("Please enter the installation path for The Jackbox Party Pack 2: ")
    jackbox_path = prompt.strip()

earwax_content = os.path.join(jackbox_path, "games", "Earwax", "content")
if earwax_content:
    print(f"Earwax content path found at: {earwax_content}")
else:
    print("The Earwax Content path could not be found. Exiting.")
    sys.exit()

# Create backups of EarwaxAudio.jet and EarwaxPrompts.jet if they don't already exist
backup_files = ["EarwaxAudio.jet", "EarwaxPrompts.jet"]
for backup_file in backup_files:
    original_file = os.path.join(earwax_content, backup_file)
    backup_file_path = os.path.join(earwax_content, backup_file + ".bak")
    if os.path.exists(original_file) and not os.path.exists(backup_file_path):
        print(f"Creating backup for {backup_file}")
        with open(original_file, 'rb') as f_src:
            with open(backup_file_path, 'wb') as f_dst:
                f_dst.write(f_src.read())

# Check for missing prompt files in the local source_voice folder
earwax_prompts_path = os.path.join(earwax_content, "EarwaxPrompts")
local_source_voice_path = os.path.join(cwd, "source_voice")

if not os.path.exists(local_source_voice_path):
    os.mkdir(local_source_voice_path)

for filename in os.listdir(earwax_prompts_path):
    if filename.endswith(".ogg") and re.match(r"^\d+_[a-zA-Z0-9]+", filename):
        local_file_path = os.path.join(local_source_voice_path, filename)
        wav_filename = os.path.splitext(filename)[0] + ".wav"
        local_wav_path = os.path.join(local_source_voice_path, wav_filename)
        if not os.path.exists(local_file_path) and not os.path.exists(local_wav_path):
            print(f"Copying {filename} to local source_voice folder")
            source_file_path = os.path.join(earwax_prompts_path, filename)
            with open(source_file_path, 'rb') as src_file:
                with open(local_file_path, 'wb') as dst_file:
                    dst_file.write(src_file.read())

def butter_params(low_freq, high_freq, fs, order=5):
    nyq = 0.5 * fs
    low = low_freq / nyq
    high = high_freq / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a


def butter_bandpass_filter(data, low_freq, high_freq, fs, order=5):
    b, a = butter_params(low_freq, high_freq, fs, order=order)
    y = lfilter(b, a, data)
    return y

def speedUpAudio(filename, rate):
    y, sr = sf.read(filename)
    y_stretch = pyrb.time_stretch(y, sr, rate)
    y_shift = pyrb.pitch_shift(y, sr, rate)
    return y_stretch, sr


def set_echo(fs, data, delay):
    # Applies an echo that is 0...<input audio duration in seconds> seconds from the beginning
    output_audio = np.zeros(len(data))
    output_delay = delay * fs

    for count, e in enumerate(data):

        output_audio[count] = (e * 0.5) + \
            (data[count - int(output_delay)] * 0.5)

    return output_audio


def getChannelScaled(ChannelData):
    # Compute the Short-Time Fourier Transform (STFT)
    frequencies, times, Zxx = stft(ChannelData, fs=fs, nperseg=64)

    # Zxx contains the complex STFT results
    # Convert to magnitude spectrum
    magnitude_spectra = np.abs(Zxx)

    # Downsample to 32 frequency values
    num_bins = 32
    current_bins = magnitude_spectra.shape[0]

    # Trim the magnitude_spectra to a size that is divisible by num_bins
    trimmed_bins = (current_bins // num_bins) * num_bins
    trimmed_magnitude_spectra = magnitude_spectra[:trimmed_bins, :]

    # Calculate bin size after trimming
    bin_size = trimmed_bins // num_bins

    # Average the magnitude spectra in bins
    reduced_magnitude_spectra = np.mean(
        trimmed_magnitude_spectra.reshape((num_bins, bin_size, -1)), axis=1)

    # Convert the reduced magnitude spectra to decibels
    # reduced_magnitude_spectra_db = 20 * np.log10(np.maximum(reduced_magnitude_spectra, 1e-10))  # Adding a small value to avoid log(0)

    max_output_val = 100
    # Scale the reduced magnitude spectra to 0-max_val range
    min_val = np.min(reduced_magnitude_spectra)
    max_val = np.max(reduced_magnitude_spectra)
    scaled_reduced_magnitude_spectra = max_output_val * \
        (reduced_magnitude_spectra - min_val) / (max_val - min_val)

    # Round the scaled values to the nearest integer and convert to integer type
    integer_scaled_reduced_magnitude_spectra = np.round(
        scaled_reduced_magnitude_spectra).astype(int)

    # Print some details
    # print("Sampling Frequency:", fs)
    # print("Original Shape of Magnitude Spectra:", magnitude_spectra.shape)
    # print("Trimmed Shape of Magnitude Spectra:", trimmed_magnitude_spectra.shape)
    # print("Reduced Shape of Magnitude Spectra:", reduced_magnitude_spectra.shape)
    # print("Frequencies Shape:", frequencies.shape)
    # print("Times Shape:", times.shape)
    # print("Reduced Magnitude Spectra in dB Shape:", reduced_magnitude_spectra_db.shape)
    # print("Scaled Reduced Magnitude Spectra Shape:", scaled_reduced_magnitude_spectra.shape)
    # print("Integer Scaled Reduced Magnitude Spectra Shape:", integer_scaled_reduced_magnitude_spectra.shape)

    return integer_scaled_reduced_magnitude_spectra

# Get CWD and set it to look in New Sounds
cwd += '/New Sounds'

# Find any supported non-ogg files and convert them to ogg
extension_list = ('*.mp3', '*.wav')
os.chdir(cwd)
# create directory to move original audio files
if (not os.path.exists('Original Audio Files')):
    os.mkdir('Original Audio Files')
for extension in extension_list:
    for audio in glob.glob(extension):
        print("Converting", os.path.basename(audio), "to ogg")
        # use pydub to create the ogg file
        audio_filename = os.path.splitext(os.path.basename(audio))[0] + '.ogg'
        AudioSegment.from_file(audio).export(
            audio_filename, format='ogg', bitrate="64k")
        # move the original audio file to subdir, overwrite if exists
        destination_path = 'Original Audio Files/' + os.path.basename(audio)
        if os.path.exists(destination_path):
            os.remove(destination_path)
        os.rename(os.path.basename(audio), destination_path)
os.chdir('..')

# Initialize files array
files = []
# Step through the directory and index every name in an array
for dirname, dirnames, filenames in os.walk(cwd):

    # Strip the .ogg from every .ogg file and shove it in the array
    for filename in filenames:
        if filename.endswith(".ogg"):
            filename = filename[:-4]
            files.append(filename)

# Create spectrum folder if not present
if (not os.path.exists(cwd + "/../Spectrum/")):
    os.mkdir(cwd + "/../Spectrum/")

# Generate a spectrum file for each audio file
for file in files:
    AudioName = file  # Audio File
    AudioWavFile = cwd + "/" + AudioName + ".wav"
    AudioOggFile = cwd + "/" + AudioName + ".ogg"
    AudioSpectrumFile = cwd + "/../Spectrum/" + AudioName + ".jet"

    if (os.path.exists(AudioSpectrumFile)):
        print("Spectrum File Already Exists for", os.path.basename(file))
        continue

    print("Generating Spectrum File for", os.path.basename(file))

    # Convert ogg to wav for analysis
    try:
        audio = AudioSegment.from_file(AudioOggFile)
        audio = audio.set_frame_rate(1376)
        audio.export(AudioWavFile, format='wav')

        # Analyze WAV file
        fs, Audiodata = wavfile.read(AudioWavFile)

        # Do this spectrum analysis for each Channel
        # print(len(Audiodata.shape))
        if len(Audiodata.shape) > 1:
            # Stereo
            AudiodataLeft = Audiodata[:, 0]
            AudiodataRight = Audiodata[:, 1]
        else:
            # Copy Channel Data for Mono files
            AudiodataLeft = Audiodata
            AudiodataRight = Audiodata

        LeftData = getChannelScaled(AudiodataLeft)
        RightData = getChannelScaled(AudiodataRight)

        # Create output json for the Spectrum .jet file
        output_data = {'Refresh': 23, 'Frequencies': [], 'Peak': 100}
        for i in range(LeftData.shape[1]):
            thisRow = {'left': [], 'right': []}
            for j in range(len(LeftData)):
                # Convert the arrays to lists of native Python integers
                LeftData_list = LeftData.tolist()
                RightData_list = RightData.tolist()
                thisRow['left'].append(LeftData_list[j][i])
                thisRow['right'].append(RightData_list[j][i])
            output_data['Frequencies'].append(thisRow)

        # Write the Spectrum file
        with open(AudioSpectrumFile, 'w') as f:
            json.dump(output_data, f)
    except Exception as e:
        print(e)

    # Cleanup!
    try:
        os.remove(AudioWavFile)
    except Exception as e:
        print(e)

# Changed CWD back
cwd = os.getcwd()

# TTS

source_voice = []
# See if there are files in source_voice
if (os.path.exists("source_voice")):
    # Get CWD and set it to look in source_voice
    cwd = os.getcwd()
    cwd += '/source_voice'

    # Convert any ogg or mp3 to wav
    extension_list = ('*.ogg', '*.mp3')
    os.chdir(cwd)
    # create directory to move original audio files
    if (not os.path.exists('Original Audio Files')):
        os.mkdir('Original Audio Files')
    for extension in extension_list:
        for audio in glob.glob(extension):
            print("Converting", os.path.basename(audio), "to wav")
            # use pydub to create the wav file
            audio_filename = os.path.splitext(
                os.path.basename(audio))[0] + '.wav'
            AudioSegment.from_file(audio).export(
                audio_filename, format='wav')
            # move the original audio file to subdir
            destination_path = 'Original Audio Files/' + os.path.basename(audio)
            if os.path.exists(destination_path):
                os.remove(destination_path)
            os.rename(os.path.basename(audio), destination_path)

    # save list of .wav files to use for speech cloning
    for audio in glob.glob("*.wav"):
        source_voice.append("source_voice/"+audio)

    # print(source_voice)

    os.chdir('..')

# Changed CWD back
cwd = os.getcwd()

# See if there is a prompts.txt file present and we have a source voice
if (os.path.exists("prompts.txt") and len(source_voice) > 0):
    # create initial object structure for prompt json
    output_data = {'content': []}

    # create output folder for prompt audio
    if (not os.path.exists(cwd+"/EarwaxPrompts")):
        os.mkdir(cwd+"/EarwaxPrompts")

    # Init TTS Variables
    tts = None
    # Get device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # print(device)
    # print(torch.cuda.is_available())

    # process each non-empty line of the file into a prompt
    promptID = 0
    with open("prompts.txt", "r") as a_file:
        for line in a_file:
            stripped_line = line.strip()
            if stripped_line != '':
                print("Generating Prompt:", stripped_line, "id:", promptID)
                # generate a prompt ID
                thisPromptID = 10000+promptID

                # generate prompt audio
                outputTTSFile = "EarwaxPrompts/" + str(thisPromptID)+".wav"
                outputOGGFile = "EarwaxPrompts/" + str(thisPromptID)+".ogg"

                if not (os.path.exists(outputOGGFile)):
                    if tts is None:
                        # Init TTS Engine
                        tts = TTS(
                            "tts_models/multilingual/multi-dataset/xtts_v2").to(device)

                    ttsString = stripped_line.replace(
                        "<ANY>", 'this player').replace("<i>", "").replace("</i>", "")
                    tts.tts_to_file(text=ttsString,
                                    file_path=outputTTSFile,
                                    speaker_wav=source_voice,
                                    language="en")

                    # Add distortions to make the voice sound like M.O.T.H.E.R.
                    fs, audio = wavfile.read(outputTTSFile)
                    low_freq = 200.0
                    high_freq = 5000.0
                    filtered_signal = butter_bandpass_filter(
                        audio, low_freq, high_freq, fs, order=6)

                    # audio = convert_audio(audio)
                    filtered_signal = set_echo(fs, audio, 0.01)

                    outputMODFile = outputTTSFile.split('.wav')[0] + '_modded.wav'
                    wavfile.write(outputMODFile, fs, np.array(filtered_signal, dtype=np.int16))
                    
                    sped_up_signal, sr = speedUpAudio(outputMODFile, 1.125)
                    sf.write(outputMODFile, sped_up_signal, sr, format='wav')

                    # Convert the final wav to ogg for Jackbox
                    final_audio = AudioSegment.from_file(outputMODFile)
                    #increase volume to match original game audio level
                    final_audio = final_audio + 6
                    final_audio.export(
                        outputOGGFile, format='ogg', bitrate="64k")

                    # Delete the intermediate files
                    os.unlink(outputTTSFile)
                    os.unlink(outputMODFile)

                # generate prompt object data
                promptData = {"id": thisPromptID, "x": False,
                              "PromptAudio": thisPromptID, "name": stripped_line}
                output_data['content'].append(promptData)

                promptID += 1

    # save prompts json to EarwaxPrompts.jet
    with open("EarwaxPrompts.jet", 'w') as f:
        json.dump(output_data, f)


# Now create the new EarwaxAudio.jet
print("Creating EarwaxAudio.jet")
newEarwaxAudio = open(cwd+'/EarwaxAudio.jet', "w")

# Write to it the initial lines
newEarwaxAudio.write('{\n\t"episodeid":1234,"content":\n\t[\n')

# We need to do a preliminary write here.  Technically we don't, but I don't understand file.seek and why it kept
# stopping the script in its tracks.  You can't have a comma at the end of the .jet file list, or the game never
# knows to stop looking for sounds and just loads nothing.  I tried to delete it but couldn't figure it out,
# and I'm lazy right now, so we're gonna do a preliminary write to get some stuff there so I can just write the comma
# at the beginning of the loop and erase that variable.
newEarwaxAudio.write('\t\t{"x":false,"name":"'+file+'","short":"' +
                     file+'","id":"'+file+'","categories":["household"]}')

# Now write the line for every file.
# What these fields mean: if x is true, it will not show up when family friendly filter is on.
# name and short are the names of the sound.  name is what appears on a player's device; short is in-game.
# id is the filename without the extension.
# categories is used for a few achievements and has no bearing on how the sound is chosen by the game.
for file in files:
    if file == files[0]:
        continue
    newEarwaxAudio.write(',\n\t\t{"x":false,"name":"'+file+'","short":"' +
                         file+'","id":"'+file+'","categories":["household"]}')

# And write the final lines of the jet and close it up!
newEarwaxAudio.write('\n\t]\n}')
newEarwaxAudio.close()

print("Generation Complete!")

# Copy all .ogg files from the local New Sounds folder to earwax_content\EarwaxAudio\Audio
new_sounds_path = os.path.join(cwd, "New Sounds")
earwax_audio_path = os.path.join(earwax_content, "EarwaxAudio", "Audio")

for filename in os.listdir(new_sounds_path):
    if filename.endswith(".ogg"):
        source_file_path = os.path.join(new_sounds_path, filename)
        destination_file_path = os.path.join(earwax_audio_path, filename)
        print(f"Copying {filename} to EarwaxAudio/Audio folder")
        with open(source_file_path, 'rb') as src_file:
            with open(destination_file_path, 'wb') as dst_file:
                dst_file.write(src_file.read())

# Copy all .jet files from the local Spectrum folder to earwax_content\EarwaxAudio\Spectrum
spectrum_path = os.path.join(cwd, "Spectrum")
earwax_spectrum_path = os.path.join(earwax_content, "EarwaxAudio", "Spectrum")

for filename in os.listdir(spectrum_path):
    if filename.endswith(".jet"):
        source_file_path = os.path.join(spectrum_path, filename)
        destination_file_path = os.path.join(earwax_spectrum_path, filename)
        print(f"Copying {filename} to EarwaxAudio/Spectrum folder")
        with open(source_file_path, 'rb') as src_file:
            with open(destination_file_path, 'wb') as dst_file:
                dst_file.write(src_file.read())


# Copy all .ogg files from the local EarwaxPrompts folder to earwax_content\EarwaxPrompts
local_earwax_prompts_path = os.path.join(cwd, "EarwaxPrompts")
earwax_prompts_destination_path = os.path.join(earwax_content, "EarwaxPrompts")

for filename in os.listdir(local_earwax_prompts_path):
    if filename.endswith(".ogg"):
        source_file_path = os.path.join(local_earwax_prompts_path, filename)
        destination_file_path = os.path.join(earwax_prompts_destination_path, filename)
        print(f"Copying {filename} to EarwaxPrompts folder")
        with open(source_file_path, 'rb') as src_file:
            with open(destination_file_path, 'wb') as dst_file:
                dst_file.write(src_file.read())


# Merge the content of the new EarwaxAudio.jet file into the existing EarwaxAudio.jet file in the earwax_content folder
existing_earwax_audio_path = os.path.join(earwax_content, "EarwaxAudio.jet")
print(f"Merging content from {os.path.join(cwd, 'EarwaxAudio.jet')} into {existing_earwax_audio_path}")
try:
    with open(existing_earwax_audio_path, 'r', encoding='utf-8') as existing_file:
        existing_data = json.load(existing_file)
except FileNotFoundError:
    existing_data = {"episodeid": 1234, "content": []}

with open(os.path.join(cwd, "EarwaxAudio.jet"), 'r', encoding='utf-8') as new_file:
    new_data = json.load(new_file)

# Merge the content
existing_data["content"].extend(new_data["content"])

# Remove duplicates based on 'id'
unique_content = {item['id']: item for item in existing_data["content"]}.values()
existing_data["content"] = list(unique_content)

# Write the merged content back to the existing EarwaxAudio.jet file
with open(existing_earwax_audio_path, 'w', encoding='utf-8') as merged_file:
    json.dump(existing_data, merged_file, indent=4)


# Merge the content of the new EarwaxPrompts.jet file into the existing EarwaxPrompts.jet file in the earwax_content folder
existing_earwax_prompts_path = os.path.join(earwax_content, "EarwaxPrompts.jet")
print(f"Merging content from {os.path.join(cwd, 'EarwaxPrompts.jet')} into {existing_earwax_prompts_path}")
try:
    with open(existing_earwax_prompts_path, 'r', encoding='utf-8') as existing_file:
        existing_prompts_data = json.load(existing_file)
except FileNotFoundError:
    existing_prompts_data = {"content": []}

with open(os.path.join(cwd, "EarwaxPrompts.jet"), 'r', encoding='utf-8') as new_file:
    new_prompts_data = json.load(new_file)

# Merge the content
existing_prompts_data["content"].extend(new_prompts_data["content"])

# Remove duplicates based on 'id'
unique_prompts_content = {item['id']: item for item in existing_prompts_data["content"]}.values()
existing_prompts_data["content"] = list(unique_prompts_content)

# Write the merged content back to the existing EarwaxPrompts.jet file
with open(existing_earwax_prompts_path, 'w', encoding='utf-8') as merged_file:
    json.dump(existing_prompts_data, merged_file, indent=4)

print("Complete!")

# And collect garbage.
gc.collect()
