import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import json
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

SetLogLevel(0)
# load api key from .env file
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

# initialize Vosk with Japanese model (full size)
# if you have a weaker machine, i recommend the small model
# it's faster but only slightly less accurate
# model = Model("vosk-model-small-ja-0.22")
model = Model("vosk-model-ja-0.22")

# recognizer, 16k hz sample rate to match the vosk model
rec = KaldiRecognizer(model, 16000)

# global variable to signal when translation is complete
translation_complete = True

# open or make a transcription and translation log file
# timestamp the file name
now = datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")

def callback(indata, frames, time, status):
    global translation_complete
    if status:
        print(status)
    else:
        if translation_complete: # only print "Listening..." when translation is complete
            print("\nListening...")
        int_data = (indata[:, 0] * 32767).astype('int16')
        if rec.AcceptWaveform(int_data.tobytes()):
            translation_complete = False # set to false when starting translation
            print("\nTranslating...")
            result = json.loads(rec.Result())
            if result['text'].strip(): # only print if there is text
                # was originally messing up the first transcription of every session
                print("Japanese:", result['text'])
                # log it too
                f.write(f"Japanese: {result['text']}\n")  # Modified this line
                try:
                    # gpt3.5-turbo translation, if you have gpt-4 api access it'd be better
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo", # you can change this to gpt-4 if you have access
                        # alternatively, you don't even have to use an openai model, 
                        # you can use a diff service like DeepL or something
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant."},
                            {"role": "user", "content": f"Translate the following Japanese sentence to English: {result['text']}"},
                        ],
                    )
                    translated_text = response['choices'][0]['message']['content']
                except:
                    translated_text = "Translation failed. Apologies for the inconvenience." # just in case
                print("English:", translated_text)
                f.write(f"English: {translated_text}\n")  # Modified this line
                translation_complete = True # set to true when translation is complete

# open or make a transcription and translation log file
# timestamp the file name
with open(f"transcription_log_{timestamp}.txt", "a", encoding='utf-8') as f:
    # audio stream buffer is 65536 bytes, 16000 hz sample rate, 1 channel
    with sd.InputStream(callback=callback, channels=1, samplerate=16000, blocksize=65536):
        while True:
            pass
