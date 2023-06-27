# Live-Stream-TL
Currently configured for translating audio captured from your computer from JP to EN in real-time, though it works with any VOSK model. 

Requires an OpenAI API key, as well as a local VOSK speech recognition model. 
Make sure `main.py` is located in the same directory as your model. Additionally, you should have a `.env` file with your API key under the variable `OPENAI_API_KEY`. 

By default, the audio to listen to is taken from your default audio input device, so if you're using this like me, you'll *probably* want to set your default audio input to Stereo Mix. (**NOTE: NOT DEFAULT COMMUNICATIONS INPUT. JUST DEFAULT INPUT.**) 

Originally developed for watching Hololive JP streams, then adapted for watching CN donghua. 


## TO DO:

- add a gui
- add timestamps to transcriptions and translations
- implement speaker diarization at some point 
  note: vosk has built-in support for diarization but i haven't figured it out yet
- possibly implement some kind of noise filtering (to filter out game audio, etc. lazy way would be to use nvidia broadcast and a virtual audio cable, but i'd rather bake this in) 
