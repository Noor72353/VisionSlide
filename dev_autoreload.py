from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WATCH_SUFFIXES = {".py", ".svg", ".qss"}
WATCH_DIRS = {"app", "assets"}
WATCH_FILES = {"main.py"}
IGNORE_DIRS = {".git", ".venv", "__pycache__", "build", "dist", "models"}
POLL_INTERVAL = 0.8
RESTART_DEBOUNCE_SECONDS = 0.6


def iter_watch_files() -> list[Path]:
    files: list[Path] = []

    for file_name in WATCH_FILES:
        file_path = ROOT / file_name
        if file_path.exists():
            files.append(file_path)

    for dir_name in WATCH_DIRS:
        base_dir = ROOT / dir_name
        if not base_dir.exists():
            continue

        for current_root, dir_names, file_names in os.walk(base_dir):
            dir_names[:] = [name for name in dir_names if name not in IGNORE_DIRS]
            current_path = Path(current_root)
            for file_name in file_names:
                file_path = current_path / file_name
                if file_path.suffix.lower() in WATCH_SUFFIXES:
                    files.append(file_path)

    return files


def snapshot_files() -> dict[Path, int]:
    state: dict[Path, int] = {}
    for file_path in iter_watch_files():
        try:
            state[file_path] = file_path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
    return state


def launch_app() -> subprocess.Popen:
    print("Starting VisionSlide...", flush=True)
    return subprocess.Popen([sys.executable, "main.py"], cwd=ROOT)


def stop_app(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    print("VisionSlide auto-restart is watching for saved changes.", flush=True)
    print("Press Ctrl+C in this terminal to stop it.", flush=True)

    process = launch_app()
    previous_state = snapshot_files()
    last_restart_at = 0.0

    try:
        while True:
            time.sleep(POLL_INTERVAL)

            if process is not None and process.poll() is not None:
                print("VisionSlide closed. Waiting for the next file save to restart it.", flush=True)
                process = None

            current_state = snapshot_files()
            if current_state != previous_state:
                previous_state = current_state
                now = time.time()
                if now - last_restart_at < RESTART_DEBOUNCE_SECONDS:
                    continue

                last_restart_at = now
                print("Change detected. Starting VisionSlide...", flush=True)
                stop_app(process)
                process = launch_app()
    except KeyboardInterrupt:
        print("\nStopping VisionSlide auto-restart.", flush=True)
    finally:
        stop_app(process)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
