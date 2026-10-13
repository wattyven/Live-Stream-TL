# Live Stream Translations

This is a real-time translation application that uses Vosk and the OpenAI API. It provides a user interface for starting and stopping translations, and supports logging of translations.

## Screenshot (December 2023)

<!-- This screenshot shows the 0.1 interface; the layout changed in 0.2. -->
<img src="https://raw.githubusercontent.com/wattyven/Live-Stream-TL/main/Screenshot.png"/>

## What's new in v0.2 (October 2026)
 
- Speech recognition and translation now run on separate threads, so audio is no longer dropped while a translation is in progress, and words appear live as they're recognised.
- Installed Vosk models are detected automatically, and any model version or variant works. The "v0.22 models only" limitation is gone.
- You can choose the audio input inside the app, and translate into any language, not just English.
- Translations take the previous few lines into account, and the prompt tells the model to expect speech-recognition mistakes.
- Without an API key, the app still works as a live transcriber.
- Errors are shown in the transcript instead of failing silently, the half-finished sentence is kept when you stop, and settings are remembered between launches.
## Prerequisites
 
- Python 3.9 or higher
- A Vosk model for the language you want to translate from
- An OpenAI API key (optional; without one the app transcribes only)
## Installation
 
1. Clone this repository or download the source code.
2. Navigate to the project directory in your terminal.
3. Install the required packages with the following command:
```
    pip install -r requirements.txt
```
 
    On Linux, `sounddevice` also needs PortAudio (`sudo apt install libportaudio2` on Debian/Ubuntu). Windows and macOS don't need anything extra.
 
4. Download one or more Vosk models from https://alphacephei.com/vosk/models and unzip them into a folder named `models` in the project directory. Small models are faster; large models are more accurate but need far more RAM and CPU. The result should look something like this:
```
    Live-Stream-TL/
    ├── translate.py
    ├── requirements.txt
    ├── .env
    └── models/
        ├── vosk-model-small-ja-0.22/
        └── vosk-model-ja-0.22/
```
 
    Models placed directly in the project folder (the 0.1 layout) are found too, and you can use a model stored anywhere else with the **Browse…** button.
 
## Configuration
 
Copy `.env.example` to `.env` in the project directory and fill in your key:
 
    OPENAI_API_KEY=your_api_key_here
    OPENAI_MODEL=gpt-4.1-mini
 
`OPENAI_MODEL` is optional and defaults to `gpt-4.1-mini`. Any OpenAI chat model works. For live use, a fast non-reasoning model is usually the best choice, because it keeps the delay between speech and translation short. Each request includes the previous four lines as context, so each line costs a few more tokens than it did in 0.1, but the translations hold together much better across sentences.
 
## Running the Application
 
To run the application, navigate to the project directory in your terminal and run the following command:
 
    py translate.py
 
Depending on your system, there's a chance you might need to specify `py3` or `python` or `python3` instead of `py`. I don't know what you're using or how it's configured, but this was created on a Windows machine.
 
## Usage
 
When you run the application, you will see a window with these controls:
 
- **Speech model**: lists the Vosk models the app found. The language and size are read from the folder name, so `vosk-model-small-ja-0.22` is the small Japanese model. Use **Browse…** to pick a model folder elsewhere, and **Refresh** to rescan models and audio devices after adding new ones.
- **Microphone**: the audio input to listen to. "System default" uses your operating system's default input.
- **Translate into**: the language to translate into, written the way you'd say it, e.g. "English" or "Brazilian Portuguese". Defaults to English.
- **Translate**: untick this for transcription only. It's greyed out when no API key is set.
- **Save transcript**: saves the session to `logs/transcript_{date}_{time}_{language}.txt`, with a timestamp on every line.
- **Start listening / Stop listening**: starts or stops a session. Each session opens in its own tab, and finished tabs can be closed.
While a session is running, the line under the transcript shows what's being heard so far. When a sentence finishes, it's added to the transcript with a timestamp, and its translation fills in directly underneath as soon as it's ready. The status bar shows what the app is doing, including any audio warnings.
 
### Translating stream and video audio
 
**I highly recommend capturing your system audio with Stereo Mix rather than using a microphone.** Enable Stereo Mix in Windows' recording devices, then select it in the **Microphone** dropdown. It no longer needs to be set as your default input. For noise cancellation (removal of game audio, etc.), you can route a virtual audio cable into NVIDIA Broadcast / RTX Voice or something of the sort, then select the cleaned-up device in the dropdown.
ex:
 
<img src="https://storage.googleapis.com/openscreenshot/2%2Fh%2F-/cXSuLW-h2.png" alt="NVIDIA Broadcast Demo"/>

## Troubleshooting
 
- **"No models found"**: the model has to be unzipped (a folder, not a `.zip`), and its folder name must start with `vosk-model-`. Press **Refresh** after adding it.
- **"Recognition is falling behind real time"**: the model is too heavy for your CPU. Switch to a small model.
- **The same device is listed several times**: on Windows, each device appears once per audio API (MME, DirectSound, WASAPI, WDM-KS). If one won't open, try another.
- **Translation lines show an error**: check your API key and internet connection, and make sure `OPENAI_MODEL` names a model your account can use.
