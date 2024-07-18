# Import important libraries

import os
import gc
import glob
from pydub import AudioSegment
from pprint import pprint

# Get CWD and set it to look in New Sounds
cwd = os.getcwd()
cwd += '/New Sounds'

#Find any supported non-ogg files and convert them to ogg
extension_list = ('*.mp3', '*.wav')
os.chdir(cwd)
#create directory to move original audio files
if (not os.path.exists('Original Audio Files')):
    os.mkdir('Original Audio Files')
for extension in extension_list:
    for audio in glob.glob(extension):
        #use pydub to create the ogg file
        audio_filename = os.path.splitext(os.path.basename(audio))[0] + '.ogg'
        AudioSegment.from_file(audio).export(audio_filename, format='ogg', bitrate="64k")
        #move the original audio file to subdir
        os.rename(os.path.basename(audio), 'Original Audio Files/' + os.path.basename(audio))
os.chdir('..')

# Initialize files array
files = []
# Step through the directory and index every name in an array
for dirname, dirnames, filenames in os.walk(cwd):

    # Strip the .ogg from every file and shove it in the array
    for filename in filenames:
        filename = filename[:-4]
        files.append(filename)

# Change CWD; we're done looking at the filenames.
cwd = os.getcwd()
cwd += '/Spectrum'

# Create a dummy spectrum file for every single file and dump it in Spectrum
for file in files:
    newSpectrum = open(cwd+'/'+file+'.jet', "w")
    newSpectrum.write('{\n\t"Refresh":23,\n\t"Frequencies":[],\n\t"Peak":68\n}')
    newSpectrum.close()

# Changed CWD back
cwd = os.getcwd()

# Now create the new EarwaxAudio.jet
newEarwaxAudio = open(cwd+'/EarwaxAudio.jet', "w")

# Write to it the initial lines 
newEarwaxAudio.write('{\n\t"episodeid":1234,"content":\n\t[\n')

# We need to do a preliminary write here.  Technically we don't, but I don't understand file.seek and why it kept
# stopping the script in its tracks.  You can't have a comma at the end of the .jet file list, or the game never
# knows to stop looking for sounds and just loads nothing.  I tried to delete it but couldn't figure it out,
# and I'm lazy right now, so we're gonna do a preliminary write to get some stuff there so I can just write the comma
# at the beginning of the loop and erase that variable.
newEarwaxAudio.write('\t\t{"x":false,"name":"'+file+'","short":"'+file+'","id":"'+file+'","categories":["household"]}')

# Now write the line for every file.
# What these fields mean: if x is true, it will not show up when family friendly filter is on.
# name and short are the names of the sound.  name is what appears on a player's device; short is in-game.
# id is the filename without the extension.
# categories is used for a few achievements and has no bearing on how the sound is chosen by the game.
for file in files:
    if file == files[0]:
        continue
    newEarwaxAudio.write(',\n\t\t{"x":false,"name":"'+file+'","short":"'+file+'","id":"'+file+'","categories":["household"]}')

# And write the final lines of the jet and close it up!
newEarwaxAudio.write('\n\t]\n}')
newEarwaxAudio.close()

# And collect garbage.
gc.collect()
