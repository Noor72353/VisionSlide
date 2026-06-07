class GestureClassifier:
    def classify(self, landmarks):
        if not landmarks or len(landmarks) < 21:
            return "No gesture"

        if self.is_open_palm(landmarks):
            return "Open Palm"

        if self.is_two_fingers(landmarks):
            return "Two Fingers"

        if self.is_one_finger(landmarks):
            return "One Finger"

        if self.is_hidden_thumb_fist(landmarks):
            return "Fist"

        return "Unknown"


    def is_open_palm(self, landmarks):
        return (
            self.is_index_up(landmarks)
            and self.is_middle_up(landmarks)
            and self.is_ring_up(landmarks)
            and self.is_pinky_up(landmarks)
            and self.is_thumb_extended(landmarks)
        )

    def is_thumb_extended(self, landmarks):
        thumb_tip = landmarks[4]
        thumb_ip = landmarks[3]
        thumb_mcp = landmarks[2]
        wrist = landmarks[0]

        horizontal_extension = abs(thumb_tip.x - thumb_ip.x) > 0.02
        outward_reach = self.distance(thumb_tip, wrist) > self.distance(thumb_mcp, wrist) + 0.02

        return horizontal_extension or outward_reach

    def is_two_fingers(self, landmarks):
        return (
            self.is_index_up(landmarks)
            and self.is_middle_up(landmarks)
            and self.is_ring_down(landmarks)
            and self.is_pinky_down(landmarks)
        )

    def is_one_finger(self, landmarks):
     return (
        self.is_index_up(landmarks)
        and self.is_middle_down(landmarks)
        and self.is_ring_down(landmarks)
        and self.is_pinky_down(landmarks)
    )



    def is_thumb_right(self, landmarks):
        thumb_extension = landmarks[4].x - landmarks[3].x
        return (
            self.two_or_more_fingers_down(landmarks)
            and thumb_extension > 0.035
        )

    def is_thumb_left(self, landmarks):
        thumb_extension = landmarks[3].x - landmarks[4].x
        return (
            self.two_or_more_fingers_down(landmarks)
            and thumb_extension > 0.035
        )

    def is_hidden_thumb_fist(self, landmarks):
        thumb_extension = abs(landmarks[4].x - landmarks[3].x)

        return (
            self.all_four_fingers_down(landmarks)
            and thumb_extension < 0.06
        )



    def two_or_more_fingers_down(self, landmarks):
        count = 0
        if self.is_index_down(landmarks):
            count += 1
        if self.is_middle_down(landmarks):
            count += 1
        if self.is_ring_down(landmarks):
            count += 1
        if self.is_pinky_down(landmarks):
            count += 1
        return count >= 2



    def three_or_more_fingers_down(self, landmarks):
        count = 0
        if self.is_index_down(landmarks):
            count += 1
        if self.is_middle_down(landmarks):
            count += 1
        if self.is_ring_down(landmarks):
            count += 1
        if self.is_pinky_down(landmarks):
            count += 1
        return count >= 3

    def all_four_fingers_down(self, landmarks):
        return (
            self.is_index_down(landmarks)
            and self.is_middle_down(landmarks)
            and self.is_ring_down(landmarks)
            and self.is_pinky_down(landmarks)
        )

    def thumb_tip_is_low(self, landmarks):
        return landmarks[4].y > landmarks[5].y

    def is_index_up(self, landmarks):
        return landmarks[8].y < landmarks[6].y

    def is_middle_up(self, landmarks):
        return landmarks[12].y < landmarks[10].y

    def is_ring_up(self, landmarks):
        return landmarks[16].y < landmarks[14].y

    def is_pinky_up(self, landmarks):
        return landmarks[20].y < landmarks[18].y

    def is_index_down(self, landmarks):
        return landmarks[8].y > landmarks[6].y

    def is_middle_down(self, landmarks):
        return landmarks[12].y > landmarks[10].y

    def is_ring_down(self, landmarks):
        return landmarks[16].y > landmarks[14].y

    def is_pinky_down(self, landmarks):
        return landmarks[20].y > landmarks[18].y

    def distance(self, first, second):
        dx = first.x - second.x
        dy = first.y - second.y
        return (dx * dx + dy * dy) ** 0.5
