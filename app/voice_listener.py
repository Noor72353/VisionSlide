import json
import queue
import threading
import time

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model


class VoiceListener:
    _model_cache = {}
    _model_cache_lock = threading.Lock()

    def __init__(self, model_path, device_name, on_command):
        self.model_path = model_path
        self.device_name = device_name
        self.on_command = on_command

        self.commands = [
            "next",
            "next slide",
            "go next",
            "forward",
            "previous",
            "previous slide",
            "go previous",
            "go back",
            "back",
            "start",
            "start slideshow",
            "start slide show",
            "begin slideshow",
            "exit",
            "exit slideshow",
            "exit slide show",
            "stop slideshow",
            "end slideshow",
            "first",
            "first slide",
            "go to first slide",
            "last slide",
            "go to last slide",
        ]

        # Add single number words for direct slide jumping
        number_words = [
            "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
            "twenty", "twenty one", "twenty two", "twenty three", "twenty four", "twenty five", "twenty six", "twenty seven", "twenty eight", "twenty nine",
            "thirty", "thirty one", "thirty two", "thirty three", "thirty four", "thirty five", "thirty six", "thirty seven", "thirty eight", "thirty nine",
            "forty", "forty one", "forty two", "forty three", "forty four", "forty five", "forty six", "forty seven", "forty eight", "forty nine",
            "fifty", "fifty one", "fifty two", "fifty three", "fifty four", "fifty five", "fifty six", "fifty seven", "fifty eight", "fifty nine",
            "sixty", "sixty one", "sixty two", "sixty three", "sixty four", "sixty five", "sixty six", "sixty seven", "sixty eight", "sixty nine",
            "seventy", "seventy one", "seventy two", "seventy three", "seventy four", "seventy five", "seventy six", "seventy seven", "seventy eight", "seventy nine",
            "eighty", "eighty one", "eighty two", "eighty three", "eighty four", "eighty five", "eighty six", "eighty seven", "eighty eight", "eighty nine",
            "ninety", "ninety one", "ninety two", "ninety three", "ninety four", "ninety five", "ninety six", "ninety seven", "ninety eight", "ninety nine",
            "one hundred"
        ]

        # Add all number words as individual commands
        self.commands.extend(number_words)

        # Add "go to slide [number]" commands for numbers 1-10 as examples in quick help
        for number in range(1, 11):
            number_words_cmd = self.number_to_words(number)
            self.commands.append(f"go to slide {number_words_cmd}")
            self.commands.append(f"slide {number_words_cmd}")
            self.commands.append(f"jump to slide {number_words_cmd}")
            self.commands.append(f"go to {number_words_cmd}")

        self.audio_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.startup_event = None
        self.startup_error = ""
        self._last_partial_text = ""
        self._partial_repeat_count = 0
        self._last_emitted_text = ""
        self._last_emit_time = 0.0
        self._last_partial_emitted_text = ""
        self._last_partial_emitted_time = 0.0
        self._command_set = set()
        self._fast_partial_command_set = set()
        self._command_prefixes = set()
        self.fast_partial_commands = [
            "next",
            "next slide",
            "go next",
            "forward",
            "go forward",
            "previous",
            "previous slide",
            "go previous",
            "go back",
            "back",
            "backward",
            "go backward",
            "start",
            "start slideshow",
            "start slide show",
            "begin",
            "begin slideshow",
            "exit",
            "exit slideshow",
            "exit slide show",
            "stop",
            "stop slideshow",
            "end",
            "end slideshow",
            "first",
            "first slide",
            "go to first slide",
            "last slide",
            "final slide",
            "go to last slide",
            "go to final slide",
        ]
        self._refresh_command_cache()

    @classmethod
    def _get_cached_model(cls, model_path):
        with cls._model_cache_lock:
            if model_path not in cls._model_cache:
                cls._model_cache[model_path] = Model(model_path)
            return cls._model_cache[model_path]

    @property
    def commands(self):
        return self._commands

    @commands.setter
    def commands(self, value):
        self._commands = list(value or [])
        self._refresh_command_cache()

    # Convert a number into spoken English words up to 100
    def number_to_words(self, number):
        ones = {
            0: "zero",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
        }

        teens = {
            10: "ten",
            11: "eleven",
            12: "twelve",
            13: "thirteen",
            14: "fourteen",
            15: "fifteen",
            16: "sixteen",
            17: "seventeen",
            18: "eighteen",
            19: "nineteen",
        }

        tens = {
            20: "twenty",
            30: "thirty",
            40: "forty",
            50: "fifty",
            60: "sixty",
            70: "seventy",
            80: "eighty",
            90: "ninety",
        }

        if number < 10:
            return ones[number]

        if 10 <= number < 20:
            return teens[number]

        if number == 100:
            return "one hundred"

        if number in tens:
            return tens[number]

        ten_part = (number // 10) * 10
        one_part = number % 10
        return f"{tens[ten_part]} {ones[one_part]}"

    # Find an input device by matching part of its name or using the system default as fallback
    def find_input_device(self):
        devices = sd.query_devices()
        desired_name = (self.device_name or "").strip().lower()

        if desired_name == "default system microphone":
            # Use the system's default input device
            try:
                default_device = sd.default.device
                if isinstance(default_device, (tuple, list)):
                    input_index = default_device[0]
                else:
                    input_index = default_device
                if input_index is not None and input_index >= 0:
                    default_info = sd.query_devices(input_index)
                    if default_info["max_input_channels"] > 0:
                        return input_index
            except Exception:
                pass

        if desired_name:
            for index, device in enumerate(devices):
                if device["max_input_channels"] > 0:
                    device_name = device["name"].strip().lower()
                    if device_name == desired_name:
                        return index
            for index, device in enumerate(devices):
                if device["max_input_channels"] > 0:
                    device_name = device["name"].strip().lower()
                    if desired_name in device_name:
                        return index

        # Final fallback: use system default
        try:
            default_device = sd.default.device
            if isinstance(default_device, (tuple, list)):
                input_index = default_device[0]
            else:
                input_index = default_device
            if input_index is not None and input_index >= 0:
                default_info = sd.query_devices(input_index)
                if default_info["max_input_channels"] > 0:
                    return input_index
        except Exception:
            pass

        for index, device in enumerate(devices):
            if device["max_input_channels"] > 0:
                return index

        return None

    def test_input_device(self):
        device_index = self.find_input_device()
        if device_index is None:
            return False

        try:
            device_info = sd.query_devices(device_index)
            channels = min(2, max(1, int(device_info.get("max_input_channels", 1))))
            samplerate = int(device_info.get("default_samplerate", 16000))

            old_device = sd.default.device
            try:
                sd.default.device = device_index

                def callback(indata, frames, time, status):
                    pass

                with sd.InputStream(
                    samplerate=samplerate,
                    channels=channels,
                    dtype="int16",
                    device=device_index,
                    callback=callback,
                    blocksize=1024,
                ) as stream:
                    import time
                    time.sleep(0.1)
            finally:
                sd.default.device = old_device
            return True
        except Exception as e:
            print(f"VoiceListener: Device test failed for {self.device_name}: {e}")
            return False

    # Start listening in a background thread
    def start(self):
        self.stop()

        device_index = self.find_input_device()
        if device_index is None:
            print(f"VoiceListener: Cannot start - no suitable device found for {self.device_name}")
            return False

        print(f"VoiceListener: Starting voice listener with device {device_index}")
        self.audio_queue = queue.Queue()
        self.running = True
        self.startup_error = ""
        self.startup_event = threading.Event()
        self.thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.thread.start()
        if not self.startup_event.wait(timeout=3.0):
            print("VoiceListener: Voice listener startup timed out")
            self.running = False
            return False

        if self.startup_error:
            print(f"VoiceListener: Voice listener startup failed: {self.startup_error}")
            self.running = False
            return False

        print("VoiceListener: Voice listener thread started")
        return True

    # Stop listening cleanly
    def stop(self):
        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        self.thread = None
        self.startup_event = None
        self.audio_queue = queue.Queue()

    def _refresh_command_cache(self):
        normalized_commands = {
            str(command or "").strip().lower()
            for command in getattr(self, "_commands", [])
            if str(command or "").strip()
        }
        self._command_set = normalized_commands
        self._fast_partial_command_set = {
            str(command or "").strip().lower()
            for command in getattr(self, "fast_partial_commands", [])
            if str(command or "").strip()
        }
        prefixes = set()
        for command in normalized_commands:
            parts = command.split()
            for count in range(1, len(parts) + 1):
                prefixes.add(" ".join(parts[:count]))
        self._command_prefixes = prefixes

    def _boost_low_volume_audio(self, pcm_bytes):
        if not pcm_bytes:
            return pcm_bytes
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        except Exception:
            return pcm_bytes

        if samples.size == 0:
            return pcm_bytes

        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        if rms <= 0:
            return pcm_bytes

        gain = 1.0
        if rms < 300:
            gain = 5.0
        elif rms < 700:
            gain = 3.2
        elif rms < 1200:
            gain = 2.0
        elif rms < 2000:
            gain = 1.35

        if gain <= 1.0:
            return pcm_bytes

        try:
            boosted = np.clip(samples.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
            return boosted.tobytes()
        except Exception:
            return pcm_bytes

    # Callback from microphone input
    def callback(self, indata, frames, time_info, status):
        if not self.running:
            return

        if status:
            print(f"VoiceListener: Audio callback status: {status}")

        if hasattr(indata, "tobytes"):
            pcm_bytes = indata.tobytes()
        else:
            pcm_bytes = bytes(indata)

        self.audio_queue.put(self._boost_low_volume_audio(pcm_bytes))

    def _reset_partial_tracking(self):
        self._last_partial_text = ""
        self._partial_repeat_count = 0

    def _remember_partial_emit(self, text):
        self._last_partial_emitted_text = str(text or "").strip().lower()
        self._last_partial_emitted_time = time.monotonic()

    def _should_ignore_followup_final(self, text):
        normalized_text = (text or "").strip().lower()
        if not normalized_text or not self._last_partial_emitted_text:
            return False

        if (time.monotonic() - self._last_partial_emitted_time) > 1.0:
            return False

        # If a stable partial command already fired for this utterance,
        # ignore the immediate final result unless it is exactly the same.
        return normalized_text != self._last_partial_emitted_text

    def _emit_command(self, text):
        normalized_text = (text or "").lower().strip()
        if not normalized_text:
            return

        now = time.monotonic()
        if normalized_text == self._last_emitted_text and (now - self._last_emit_time) < 1.0:
            return

        print(f"VoiceListener: Emitting command: '{normalized_text}'")
        self._last_emitted_text = normalized_text
        self._last_emit_time = now
        self.on_command(normalized_text)

    def _is_exact_known_command(self, text):
        normalized_text = (text or "").lower().strip()
        if not normalized_text:
            return False
        return normalized_text in self._fast_partial_command_set

    def _is_known_command_prefix(self, text):
        normalized_text = (text or "").lower().strip()
        if not normalized_text:
            return False
        return normalized_text in self._command_prefixes

    def _partial_emit_threshold(self, text):
        normalized_text = (text or "").lower().strip()
        if not normalized_text:
            return 2
        if len(normalized_text) >= 6:
            return 1
        return 2

    # Main speech recognition loop
    def listen_loop(self):
        device_index = self.find_input_device()
        if device_index is None:
            print(f"VoiceListener: No suitable input device found for {self.device_name}")
            self.running = False
            return

        try:
            print(f"VoiceListener: Loading model from {self.model_path}")
            model = self._get_cached_model(self.model_path)

            device_info = sd.query_devices(device_index)
            samplerate = int(device_info.get("default_samplerate", 16000))
            grammar_commands = sorted(self._command_set)
            recognizer = KaldiRecognizer(
                model,
                samplerate,
                json.dumps(grammar_commands + ["[unk]"]),
            )
            channels = 1
            print(f"VoiceListener: Starting audio stream on device {device_index}: {device_info['name']} (channels: {channels}, samplerate: {samplerate})")

            old_device = sd.default.device
            try:
                sd.default.device = device_index

                with sd.RawInputStream(
                    samplerate=samplerate,
                    blocksize=600,
                    dtype="int16",
                    channels=channels,
                    device=device_index,
                    callback=self.callback,
                ):
                    print("VoiceListener: Audio stream started, listening for commands...")
                    if self.startup_event is not None:
                        self.startup_event.set()
                    while self.running:
                        try:
                            data = self.audio_queue.get(timeout=0.5)
                        except queue.Empty:
                            continue

                        if recognizer.AcceptWaveform(data):
                            result = json.loads(recognizer.Result())
                            text = result.get("text", "").strip()
                            self._reset_partial_tracking()
                            if text:
                                if self._should_ignore_followup_final(text):
                                    print(
                                        "VoiceListener: Ignoring conflicting final result "
                                        f"'{text}' after partial '{self._last_partial_emitted_text}'"
                                    )
                                    continue
                                print(f"VoiceListener: Recognized command: '{text}'")
                                self._emit_command(text)
                            continue

                        partial_result = json.loads(recognizer.PartialResult())
                        partial_text = partial_result.get("partial", "").strip().lower()
                        if not partial_text:
                            self._reset_partial_tracking()
                            continue

                        if partial_text == self._last_partial_text:
                            self._partial_repeat_count += 1
                        else:
                            self._last_partial_text = partial_text
                            self._partial_repeat_count = 1

                        if (
                            self._partial_repeat_count >= self._partial_emit_threshold(partial_text)
                            and self._is_exact_known_command(partial_text)
                        ):
                            print(f"VoiceListener: Stable exact partial command: '{partial_text}'")
                            self._remember_partial_emit(partial_text)
                            self._emit_command(partial_text)
                            self._reset_partial_tracking()
            finally:
                sd.default.device = old_device

        except Exception as e:
            print(f"VoiceListener: Error in listen_loop: {e}")
            self.startup_error = str(e)
            if self.startup_event is not None:
                self.startup_event.set()
        finally:
            if self.startup_event is not None and not self.startup_event.is_set():
                self.startup_event.set()
            print("VoiceListener: Stopping audio stream")
            self.running = False
