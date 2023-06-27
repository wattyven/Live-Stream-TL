import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import json
import openai
import os
from dotenv import load_dotenv
from datetime import datetime

# change this to the language you want to translate from
# use the two letter code, e.g. "en" for English, "es" for Spanish, etc.
lang_sel = "cn"

def callback(indata, frames, time, status):
    global translation_complete, lang
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
                print(f"{lang}:", result['text'])
                # log it too
                f.write(f"{lang}: {result['text']}\n")  # Modified this line
                try:
                    # gpt3.5-turbo translation, if you have gpt-4 api access it'd be better
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo", # you can change this to gpt-4 if you have access
                        # alternatively, you don't even have to use an openai model, 
                        # you can use a diff service like DeepL or something
                        messages=[
                            {"role": "system", "content": "You are a professional translator. You will reply with nothing but the best translations, and absolutely nothing else."},
                            {"role": "user", "content": f"Translate the following sentence from {lang} to English: {result['text']}"},
                        ],
                    )
                    translated_text = response['choices'][0]['message']['content']
                except:
                    translated_text = "Translation failed. Apologies for the inconvenience." # just in case
                print("EN:", translated_text)
                f.write(f"EN: {translated_text}\n")  # Modified this line
                translation_complete = True # set to true when translation is complete

# open or make a transcription and translation log file
# timestamp the file name
if __name__ == "__main__":
    
    SetLogLevel(0)

    # load api key from .env file
    load_dotenv()
    openai.api_key = os.getenv('OPENAI_API_KEY')

    # initialize audio stream
    stream = sd.InputStream(
        callback=callback, 
        channels=1, 
        samplerate=16000, 
        blocksize=65536)

    # initialize Vosk with model (full size)
    # if you have a weaker machine, i recommend the small model
    # it's faster but only slightly less accurate
    # model = Model("vosk-model-small-{lang}-0.22")
    # these models will have to be downloaded if you don't have them already
    lang = lang_sel.upper()
    print(f"Language: {lang}")
    model = Model(f"vosk-model-{lang}-0.22")

    # recognizer, 16k hz sample rate to match the vosk model
    rec = KaldiRecognizer(model, 16000)

    # global variable to signal when translation is complete
    translation_complete = True

    # make a timestamped log file, then start transcription and translation
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")
    with open(f"transcription_log_{timestamp}.txt", "a", encoding='utf-8') as f:
        # audio stream buffer is 65536 bytes, 16000 hz sample rate, 1 channel
        # by default, sd.InputStream uses the default input device
        # I have this set to Stereo Mix. You can use a virtual audio cable as well, 
        # or even a physical cable if you have the right hardware
        with stream:
            while True:
                pass
