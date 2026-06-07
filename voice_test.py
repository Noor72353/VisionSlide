import json
import queue

import sounddevice as sd
from vosk import KaldiRecognizer, Model


MODEL_PATH = "models/vosk-model-small-en-us-0.15"

# Change this value to test different microphones
# Example:
# "External Microphone"
# "Microphone Array"
VOICE_DEVICE_NAME = "External Microphone"

COMMANDS = [
    "next slide",
    "previous slide",
    "start slideshow",
    "exit slideshow",
    "go to slide one",
    "go to slide two",
    "go to slide three",
    "go to slide four",
    "go to slide five",
    "go to slide six",
    "go to slide seven",
    "go to slide eight",
    "go to slide nine",
    "go to slide ten",
]

audio_queue = queue.Queue()
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, 16000, json.dumps(COMMANDS))
last_partial = ""


# Find an input microphone by matching part of its name
def find_input_device(device_name_part):
    devices = sd.query_devices()

    for index, device in enumerate(devices):
        if (
            device["max_input_channels"] > 0
            and device_name_part.lower() in device["name"].lower()
        ):
            return index, device

    return None, None


DEVICE_INDEX, DEVICE_INFO = find_input_device(VOICE_DEVICE_NAME)

if DEVICE_INDEX is None:
    raise RuntimeError(f"Input device containing '{VOICE_DEVICE_NAME}' not found")

print("Using device:", DEVICE_INDEX, DEVICE_INFO["name"])


def callback(indata, frames, time, status):
    if status:
        print(status)
    audio_queue.put(bytes(indata))


with sd.RawInputStream(
    samplerate=16000,
    blocksize=2000,
    dtype="int16",
    channels=1,
    device=DEVICE_INDEX,
    callback=callback,
):
    print("Listening... say presentation commands clearly")

    while True:
        data = audio_queue.get()

        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            text = result.get("text", "").strip()
            if text:
                print("Recognized:", text)
                last_partial = ""
        else:
            partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
            if partial and partial != last_partial:
                print("Hearing:", partial)
                last_partial = partial
