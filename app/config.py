import json
from pathlib import Path

from app.runtime_paths import data_path
from app.validators import (
    sanitize_bool,
    sanitize_camera_index,
    sanitize_control_hold_frames,
    sanitize_jump_hold_seconds,
    sanitize_total_slides,
    sanitize_voice_device_name,
)


DEFAULT_SETTINGS = {
    "camera_index": 0,
    "control_hold_frames": 3,
    "jump_hold_seconds": 0.1,
    "sound_enabled": True,
    "auto_focus_presentation": True,
    "gesture_enabled": True,
    "voice_enabled": False,
    "voice_device_name": "Default System Microphone",
    "total_slides": 100,
    "last_login_identity": "",
    "recent_presentations": [],
    "command_history": [],
    "practice_mode": False,
    "custom_voice_commands": {},
    "custom_gesture_actions": {},
    "gesture_profile": "Normal",
    "voice_feedback_mode": "unknown_only",
    "voice_feedback_beep_style": "standard",
    "show_camera_overlays": True,
    "user_preferences": {},
    "admin_activity_log": [],
    "auto_lock_minutes": 0,
    "keyboard_shortcuts_enabled": True,
}

SETTINGS_FILE = data_path("visionside_settings.json")


class AppConfig:
    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        if not SETTINGS_FILE.exists():
            return

        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
                loaded_settings = json.load(file)

            self.settings["camera_index"] = sanitize_camera_index(
                loaded_settings.get("camera_index"),
                DEFAULT_SETTINGS["camera_index"],
            )
            self.settings["control_hold_frames"] = sanitize_control_hold_frames(
                loaded_settings.get("control_hold_frames"),
                DEFAULT_SETTINGS["control_hold_frames"],
            )
            self.settings["jump_hold_seconds"] = sanitize_jump_hold_seconds(
                loaded_settings.get("jump_hold_seconds"),
                DEFAULT_SETTINGS["jump_hold_seconds"],
            )
            self.settings["sound_enabled"] = sanitize_bool(
                loaded_settings.get("sound_enabled"),
                DEFAULT_SETTINGS["sound_enabled"],
            )
            self.settings["auto_focus_presentation"] = sanitize_bool(
                loaded_settings.get("auto_focus_presentation"),
                DEFAULT_SETTINGS["auto_focus_presentation"],
            )
            self.settings["gesture_enabled"] = sanitize_bool(
                loaded_settings.get("gesture_enabled"),
                DEFAULT_SETTINGS["gesture_enabled"],
            )
            self.settings["voice_enabled"] = sanitize_bool(
                loaded_settings.get("voice_enabled"),
                DEFAULT_SETTINGS["voice_enabled"],
            )
            self.settings["voice_device_name"] = sanitize_voice_device_name(
                loaded_settings.get("voice_device_name"),
                default=DEFAULT_SETTINGS["voice_device_name"],
            )
            self.settings["total_slides"] = sanitize_total_slides(
                loaded_settings.get("total_slides"),
                DEFAULT_SETTINGS["total_slides"],
            )
            self.settings["last_login_identity"] = str(
                loaded_settings.get("last_login_identity", DEFAULT_SETTINGS["last_login_identity"])
            ).strip()
            self.settings["recent_presentations"] = list(
                loaded_settings.get("recent_presentations", DEFAULT_SETTINGS["recent_presentations"])
            )
            self.settings["command_history"] = list(
                loaded_settings.get("command_history", DEFAULT_SETTINGS["command_history"])
            )
            self.settings["practice_mode"] = sanitize_bool(
                loaded_settings.get("practice_mode"),
                DEFAULT_SETTINGS["practice_mode"],
            )
            self.settings["custom_voice_commands"] = dict(
                loaded_settings.get("custom_voice_commands", DEFAULT_SETTINGS["custom_voice_commands"])
            )
            self.settings["custom_gesture_actions"] = dict(
                loaded_settings.get("custom_gesture_actions", DEFAULT_SETTINGS["custom_gesture_actions"])
            )
            self.settings["gesture_profile"] = str(
                loaded_settings.get("gesture_profile", DEFAULT_SETTINGS["gesture_profile"])
            ).strip() or DEFAULT_SETTINGS["gesture_profile"]
            self.settings["voice_feedback_mode"] = str(
                loaded_settings.get("voice_feedback_mode", DEFAULT_SETTINGS["voice_feedback_mode"])
            ).strip() or DEFAULT_SETTINGS["voice_feedback_mode"]
            self.settings["voice_feedback_beep_style"] = str(
                loaded_settings.get("voice_feedback_beep_style", DEFAULT_SETTINGS["voice_feedback_beep_style"])
            ).strip() or DEFAULT_SETTINGS["voice_feedback_beep_style"]
            self.settings["show_camera_overlays"] = sanitize_bool(
                loaded_settings.get("show_camera_overlays"),
                DEFAULT_SETTINGS["show_camera_overlays"],
            )
            self.settings["user_preferences"] = dict(
                loaded_settings.get("user_preferences", DEFAULT_SETTINGS["user_preferences"])
            )
            self.settings["admin_activity_log"] = list(
                loaded_settings.get("admin_activity_log", DEFAULT_SETTINGS["admin_activity_log"])
            )
            try:
                self.settings["auto_lock_minutes"] = max(
                    0, int(loaded_settings.get("auto_lock_minutes", DEFAULT_SETTINGS["auto_lock_minutes"]))
                )
            except Exception:
                self.settings["auto_lock_minutes"] = DEFAULT_SETTINGS["auto_lock_minutes"]
            self.settings["keyboard_shortcuts_enabled"] = sanitize_bool(
                loaded_settings.get("keyboard_shortcuts_enabled"),
                DEFAULT_SETTINGS["keyboard_shortcuts_enabled"],
            )

        except Exception:
            self.settings = DEFAULT_SETTINGS.copy()

    def save(self):
        with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
            json.dump(self.settings, file, indent=4)

    def get(self, key):
        return self.settings.get(key, DEFAULT_SETTINGS[key])

    def set(self, key, value):
        if key == "camera_index":
            value = sanitize_camera_index(value, DEFAULT_SETTINGS["camera_index"])
        elif key == "control_hold_frames":
            value = sanitize_control_hold_frames(value, DEFAULT_SETTINGS["control_hold_frames"])
        elif key == "jump_hold_seconds":
            value = sanitize_jump_hold_seconds(value, DEFAULT_SETTINGS["jump_hold_seconds"])
        elif key == "sound_enabled":
            value = sanitize_bool(value, DEFAULT_SETTINGS["sound_enabled"])
        elif key == "auto_focus_presentation":
            value = sanitize_bool(value, DEFAULT_SETTINGS["auto_focus_presentation"])
        elif key == "gesture_enabled":
            value = sanitize_bool(value, DEFAULT_SETTINGS["gesture_enabled"])
        elif key == "voice_enabled":
            value = sanitize_bool(value, DEFAULT_SETTINGS["voice_enabled"])
        elif key == "voice_device_name":
            value = sanitize_voice_device_name(value, default=DEFAULT_SETTINGS["voice_device_name"])
        elif key == "total_slides":
            value = sanitize_total_slides(value, DEFAULT_SETTINGS["total_slides"])
        elif key == "last_login_identity":
            value = str(value or "").strip()
        elif key == "recent_presentations":
            value = list(value or [])
        elif key == "command_history":
            value = list(value or [])
        elif key == "practice_mode":
            value = sanitize_bool(value, DEFAULT_SETTINGS["practice_mode"])
        elif key == "custom_voice_commands":
            value = dict(value or {})
        elif key == "custom_gesture_actions":
            value = dict(value or {})
        elif key == "gesture_profile":
            value = str(value or DEFAULT_SETTINGS["gesture_profile"]).strip() or DEFAULT_SETTINGS["gesture_profile"]
        elif key == "voice_feedback_mode":
            value = str(value or DEFAULT_SETTINGS["voice_feedback_mode"]).strip() or DEFAULT_SETTINGS["voice_feedback_mode"]
        elif key == "voice_feedback_beep_style":
            value = str(value or DEFAULT_SETTINGS["voice_feedback_beep_style"]).strip() or DEFAULT_SETTINGS["voice_feedback_beep_style"]
        elif key == "show_camera_overlays":
            value = sanitize_bool(value, DEFAULT_SETTINGS["show_camera_overlays"])
        elif key == "user_preferences":
            value = dict(value or {})
        elif key == "admin_activity_log":
            value = list(value or [])
        elif key == "auto_lock_minutes":
            try:
                value = max(0, int(value))
            except Exception:
                value = DEFAULT_SETTINGS["auto_lock_minutes"]
        elif key == "keyboard_shortcuts_enabled":
            value = sanitize_bool(value, DEFAULT_SETTINGS["keyboard_shortcuts_enabled"])

        self.settings[key] = value
        self.save()
