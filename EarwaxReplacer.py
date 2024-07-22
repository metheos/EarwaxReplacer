# Import important libraries

import os
import gc
import glob
import json
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft, lfilter, butter
from pydub import AudioSegment
from TTS.api import TTS


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


# def convert_audio(input_audio_data):
#     temp_audio = input_audio_data.astype(float)

#     return np.array(temp_audio, dtype='int16')


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
cwd = os.getcwd()
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
        # move the original audio file to subdir
        os.rename(os.path.basename(audio),
                  'Original Audio Files/' + os.path.basename(audio))
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
            os.rename(os.path.basename(audio),
                      'Original Audio Files/' + os.path.basename(audio))

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

    # Init TTS Variable
    tts = None

    # process each non-empty line of the file into a prompt
    promptID = 0
    with open("prompts.txt", "r") as a_file:
        for line in a_file:
            stripped_line = line.strip()
            if stripped_line != '':
                print("Generating Prompt:", stripped_line)
                # generate a prompt ID
                thisPromptID = 10000+promptID

                # generate prompt audio
                outputTTSFile = "EarwaxPrompts/" + str(thisPromptID)+".wav"
                outputOGGFile = "EarwaxPrompts/" + str(thisPromptID)+".ogg"

                if not (os.path.exists(outputOGGFile)):
                    if tts is None:
                        # Init TTS Engine
                        tts = TTS(
                            "tts_models/multilingual/multi-dataset/xtts_v2")

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
                wavfile.write(outputMODFile, fs, np.array(
                    filtered_signal, dtype=np.int16))

                # Convert the final wav to ogg for Jackbox
                AudioSegment.from_file(outputMODFile).export(
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

print("Complete!")

# And collect garbage.
gc.collect()
