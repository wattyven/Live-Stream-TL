# Live Stream Translations - Alpha

This is a real-time translation application that uses the Vosk library and OpenAI API. It also provides an optional (though highly recommended) graphical user interface for starting and stopping translations, and supports logging of translations.

## Prerequisites

- Python 3.8 or higher
- An OpenAI API key

## Installation

1. Clone this repository or download the source code.
2. Navigate to the project directory in your terminal.
3. Install the required packages with the following command:

    ```
    pip install -r requirements.txt
    ```

## Configuration

Before running the application, you need to set your OpenAI API key. You can do this by creating a `.env` file in the project directory with the following content:
    
    OPENAI_API_KEY=your_api_key_here
   
## Running the Application

To run the application, navigate to the project directory in your terminal and run the following command:
    
    py "GUI Alpha.py"
    
You can also run the CLI version, if you're so inclined, with the following:


    py "CLI main.py"


Depending on your system, there's a chance you might need to specify `py3` or `python` or `python3` instead of `py`. I don't know what you're using or how it's configured, but this was created on a Windows machine. 

## Usage

When you run the application, you will see a window with several controls:

- **Language code input field**: Enter the two-letter code of the language you want to translate from, e.g., "en" for English, "es" for Spanish, etc. Change the translation prompt if you're translating from English to another language!
**You'll need the corresponding Vosk model as well!** To look up letter codes and model details, please visit the Vosk model page at https://alphacephei.com/vosk/models
- **Model selector**: Choose whether to prefer the small or large model for the Vosk API. The small model is faster but slightly less accurate.
- **Logging checkbox**: Check this box to enable logging of translations. The translations will be saved in a file named `transcription_log_{timestamp}_{language}.txt` in the project directory.
- **Start Translation button**: Click this button to start the translation. The application will start listening for audio input and display the translations in the output tab.
- **Stop Translation button**: Click this button to stop the translation. If logging is enabled, the application will save the translations in a log file and display the filename in the output tab.

Translations are currently done by the gpt-3.5-turbo model. If you have API access to gpt-4, gpt-4's translations are of far higher quality. However, tokens do cost more. 

**I highly recommend using Stereo Mix set as your <u>default input</u> (*NOT* default <u>communications</u> input) when running this program. For noise cancellation (removal of game audio, etc), you can also route a virtual audio cable into Nvidia Broadcast / RTX voice or something of the sort.** 
ex: 

<img src="https://storage.googleapis.com/openscreenshot/2%2Fh%2F-/cXSuLW-h2.png" alt="NVIDIA Broadcast Demo"/>

## To Do

I do intend on adding background noise removal directly into the project, though I'd like for the implementation to be open source, and I haven't started working on that yet.

I also intend on implementing some kind of speaker diarization to distinguish between multiple speakers (such as when there are collab streams, or multiple people are talking in a show), but though it's possible to do so with Vosk, I haven't quite figured it out yet as this is ultimately still just a hobby project. It'll come eventually, though. 

The last feature I'd like to implement for now is some kind of timestamping to sync up with streams and videos. While this can be relatively easily done with livestreams, I still have to figure out how to account for videos and shows etc, as well as ensure that the text actually matches up to the audio perfectly, so it's still some ways away as well. 
