try:
    import winsound
except ImportError:
    winsound = None


class AudioFeedback:
    def __init__(self):
        self.enabled = True
        self.beep_style = "standard"

    def set_enabled(self, enabled):
        self.enabled = enabled

    def set_beep_style(self, style_name):
        self.beep_style = str(style_name or "standard").strip().lower() or "standard"

    def _play_tone_sequence(self, sequence):
        if not (self.enabled and winsound is not None):
            return
        for frequency, duration in sequence:
            winsound.Beep(int(frequency), int(duration))

    def _play_system_sound(self, alias_name):
        if not (self.enabled and winsound is not None):
            return
        try:
            winsound.PlaySound(alias_name, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            winsound.MessageBeep()

    def _play_standard_success_sound(self):
        if not (self.enabled and winsound is not None):
            return
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            self._play_tone_sequence([(820, 60), (980, 75)])

    def play_unrecognized_gesture(self):
        if not (self.enabled and winsound is not None):
            return
        if self.beep_style == "soft":
            self._play_tone_sequence([(620, 90), (520, 110)])
            return
        if self.beep_style == "crisp":
            self._play_tone_sequence([(820, 70), (680, 80)])
            return
        if self.beep_style == "chime":
            self._play_tone_sequence([(720, 75), (610, 85)])
            return
        if self.beep_style == "pulse":
            self._play_tone_sequence([(760, 45), (640, 45), (760, 45)])
            return
        if self.beep_style == "bright":
            self._play_tone_sequence([(980, 55), (760, 85)])
            return
        if self.beep_style == "mellow":
            self._play_tone_sequence([(540, 100), (460, 120)])
            return
        self._play_system_sound("SystemExclamation")

    def play_slide_change(self):
        if not (self.enabled and winsound is not None):
            return
        if self.beep_style == "soft":
            self._play_tone_sequence([(680, 75), (780, 90)])
            return
        if self.beep_style == "crisp":
            self._play_tone_sequence([(900, 65), (1040, 70)])
            return
        if self.beep_style == "chime":
            self._play_tone_sequence([(760, 70), (920, 90)])
            return
        if self.beep_style == "pulse":
            self._play_tone_sequence([(700, 45), (820, 45), (940, 55)])
            return
        if self.beep_style == "bright":
            self._play_tone_sequence([(1040, 55), (1220, 70)])
            return
        if self.beep_style == "mellow":
            self._play_tone_sequence([(560, 90), (660, 110)])
            return
        self._play_standard_success_sound()

    def preview_beep(self, style_name=None, success=True):
        if winsound is None:
            return
        original_enabled = self.enabled
        original_style = self.beep_style
        try:
            self.enabled = True
            if style_name is not None:
                self.set_beep_style(style_name)
            if success:
                self.play_slide_change()
            else:
                self.play_unrecognized_gesture()
        finally:
            self.enabled = original_enabled
            self.beep_style = original_style

