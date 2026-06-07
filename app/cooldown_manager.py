import time


class CooldownManager:
    def __init__(self):
        self.last_trigger_times = {}

    def can_trigger(self, action_name):
        current_time = time.time()
        cooldown_seconds = self.get_cooldown(action_name)
        last_time = self.last_trigger_times.get(action_name, 0)

        if current_time - last_time >= cooldown_seconds:
            self.last_trigger_times[action_name] = current_time
            return True

        return False

    def get_cooldown(self, action_name):
        if action_name == "next_slide":
            return 1.0

        if action_name == "previous_slide":
            return 1.0

        if action_name == "start_slideshow":
            return 1.0

        if action_name == "exit_slideshow":
            return 2.0

        if action_name == "unrecognized_gesture":
            return 2.0

        if action_name.startswith("jump_"):
            return 0.8

        return 1.0
