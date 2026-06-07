import sys
import os
from pathlib import Path

# Suppress Qt DPI awareness warning on Windows
if os.name == 'nt':
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_int(-4))  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VisionSlide.App")
    except (AttributeError, OSError):
        pass  # Ignore if not available on older Windows versions

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.auth import AuthManager
from app.login_window import LoginWindow
from app.main_window import MainWindow
from app.runtime_paths import resource_path


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("VisionSlide")
    app.setApplicationDisplayName("VisionSlide")
    assets_dir = resource_path("assets")
    app.setWindowIcon(QIcon(str(assets_dir / "visionslide_app_icon.svg")))

    auth_manager = AuthManager()
    auth_manager.ensure_default_admin()

    login_window = LoginWindow(auth_manager)
    login_window.setWindowState(login_window.windowState() | Qt.WindowMaximized)

    runtime: dict[str, object | None] = {
        "main_window": None,
        "login_fade": None,
        "main_fade": None,
    }

    def complete_window_handoff() -> None:
        login_window.hide()
        login_window.setWindowOpacity(1.0)
        app.setQuitOnLastWindowClosed(True)
        main_window = runtime["main_window"]
        if main_window is None:
            return
        main_window.setWindowOpacity(0.0)
        main_window.showMaximized()
        app.processEvents()
        main_fade = QPropertyAnimation(main_window, b"windowOpacity", main_window)
        main_fade.setDuration(300)
        main_fade.setEasingCurve(QEasingCurve.OutCubic)
        main_fade.setStartValue(0.0)
        main_fade.setEndValue(1.0)
        runtime["main_fade"] = main_fade
        main_fade.start()

    def handle_login_success() -> None:
        if runtime["main_window"] is None:
            main_window = MainWindow(
                current_user=login_window.authenticated_username,
                auth_manager=auth_manager,
            )
            main_window.setProperty("skipFadeInTransition", True)
            runtime["main_window"] = main_window

        login_fade = QPropertyAnimation(login_window, b"windowOpacity", login_window)
        login_fade.setDuration(420)
        login_fade.setEasingCurve(QEasingCurve.OutCubic)
        login_fade.setStartValue(1.0)
        login_fade.setEndValue(0.0)
        login_fade.finished.connect(complete_window_handoff)
        runtime["login_fade"] = login_fade
        login_fade.start()

    login_window.login_succeeded.connect(handle_login_success)
    login_window.rejected.connect(app.quit)
    login_window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
