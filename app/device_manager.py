import cv2
import sounddevice as sd


class DeviceManager:
    # Detect available camera indexes by trying a small range
    def get_camera_devices(self, max_index=5):
        camera_devices = []

        for index in range(max_index + 1):
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(index)

            if cap.isOpened():
                camera_devices.append((index, f"Camera {index}"))
                cap.release()

        return camera_devices

    def _query_devices(self):
        """Force reinitialization and query the current audio devices."""
        try:
            if hasattr(sd, '_terminate'):
                sd._terminate()
        except Exception:
            pass

        try:
            if hasattr(sd, '_initialize'):
                sd._initialize()
        except Exception:
            pass

        try:
            return sd.query_devices()
        except Exception:
            return []

    # Return useful microphone names only, deduplicated
    def get_microphone_devices(self):
        devices = self._query_devices()
        microphone_names = []
        seen_names = set()

        ignored_words = ["speaker", "stereo mix", "output"]

        for device in devices:
            if device["max_input_channels"] > 0:
                device_name = device["name"].strip()

                if any(word in device_name.lower() for word in ignored_words):
                    continue

                # Deduplicate: only add if we haven't seen this exact name before
                name_lower = device_name.lower()
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    microphone_names.append(device_name)

        return microphone_names

    # Get the actual system default microphone name
    def get_default_microphone_name(self):
        devices = self._query_devices()
        default_name = None

        # First, try the system default input device
        try:
            default_device = sd.default.device
            if isinstance(default_device, (tuple, list)):
                input_index = default_device[0]
            else:
                input_index = default_device
            if input_index is not None and input_index >= 0:
                device_info = sd.query_devices(input_index)
                if device_info["max_input_channels"] > 0:
                    default_name = device_info["name"].strip()
        except Exception:
            pass

        if default_name:
            return default_name

        # Prefer Realtek mic if system default is not available
        for device in devices:
            if device["max_input_channels"] > 0:
                device_name = device["name"].strip()
                if "realtek" in device_name.lower() and "mic" in device_name.lower():
                    return device_name

        # Otherwise, return the first valid input device
        for device in devices:
            if device["max_input_channels"] > 0:
                return device["name"].strip()

        return None
