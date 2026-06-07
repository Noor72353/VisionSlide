import time

import pyautogui
import pygetwindow as gw


class SlideController:
    def __init__(self):
        pyautogui.FAILSAFE = False
        self.auto_focus_enabled = False

    # Turn automatic PowerPoint focusing on or off
    def set_auto_focus_enabled(self, enabled):
        self.auto_focus_enabled = enabled

    # Try to focus a PowerPoint-related window before sending shortcuts
    def focus_presentation_window(self):
        title_keywords = [
            "powerpoint",
            "slide show",
            "slideshow",
            "presenter view",
        ]

        all_titles = gw.getAllTitles()
        matching_titles = [
            title
            for title in all_titles
            if title and any(keyword in title.lower() for keyword in title_keywords)
        ]

        if not matching_titles:
            return False

        for title in matching_titles:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                continue

            window = windows[0]

            try:
                if window.isMinimized:
                    window.restore()
                    time.sleep(0.2)

                window.activate()
                time.sleep(0.2)
                return True
            except Exception:
                continue

        return False

    def presentation_window_exists(self):
        title_keywords = [
            "powerpoint",
            "slide show",
            "slideshow",
            "presenter view",
        ]
        all_titles = gw.getAllTitles()
        return any(
            title and any(keyword in title.lower() for keyword in title_keywords)
            for title in all_titles
        )

    def presentation_window_is_active(self):
        title_keywords = [
            "powerpoint",
            "slide show",
            "slideshow",
            "presenter view",
        ]
        try:
            active_window = gw.getActiveWindow()
            active_title = (active_window.title or "").strip().lower() if active_window else ""
        except Exception:
            active_title = ""

        return bool(active_title) and any(keyword in active_title for keyword in title_keywords)

    # If auto focus is enabled, try focusing PowerPoint first.
    # If auto focus is disabled, only allow commands when a presentation is already active.
    def prepare_window(self):
        if not self.presentation_window_exists():
            return False
        if not self.auto_focus_enabled:
            return self.presentation_window_is_active()
        return self.focus_presentation_window()

    # Move to the next slide
    def next_slide(self):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.press("right")
        return ready

    # Move to the previous slide
    def previous_slide(self):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.press("left")
        return ready

    # Start the slideshow
    def start_slideshow(self):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.press("f5")
        return ready

    # Exit the slideshow
    def exit_slideshow(self):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.press("esc")
        return ready

    # Jump to the first slide in the presentation
    def first_slide(self):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.press("home")
        return ready

    # Jump to the last slide in the presentation
    def last_slide(self):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.press("end")
        return ready

    # Jump directly to a specific slide number
    def jump_to_slide(self, slide_number):
        ready = self.prepare_window()
        if not ready:
            return False
        pyautogui.write(str(slide_number), interval=0.05)
        pyautogui.press("enter")
        return ready






"""import pyautogui

class SlideController:
    def __init__(self):
        pyautogui.FAILSAFE = False

    def next_slide(self):
        pyautogui.press("right")

    def previous_slide(self):
        pyautogui.press("left")

    def start_slideshow(self):
        pyautogui.press("f5")

    def exit_slideshow(self):
        pyautogui.press("esc")

    def jump_to_slide(self, slide_number):
        pyautogui.write(str(slide_number), interval=0.05)
        pyautogui.press("enter")"""
