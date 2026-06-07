import cv2


class CameraManager:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.cap = None

    def start(self):
        if self.cap is None:
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)

            if not self.cap.isOpened():
                self.cap.release()
                self.cap = cv2.VideoCapture(self.camera_index)

            if self.cap is not None and self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def read_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return None

        success, frame = self.cap.read()
        if not success:
            return None

        return frame

    def stop(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
