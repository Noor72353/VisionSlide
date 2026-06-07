# VisionSlide

VisionSlide is a Python desktop application for controlling presentation slides using hand gestures and offline voice commands.

It is built as a Final Year Project and currently combines:

- PySide6 for the desktop GUI
- OpenCV for camera access
- MediaPipe for hand tracking
- Vosk for offline speech recognition
- PyAutoGUI for slideshow keyboard control

## FYP Context

VisionSlide is designed as a touchless presentation-control system for Windows. The project focuses on practical human-computer interaction for presentations, reducing reliance on physical input devices during slide delivery.

## Main Idea

The app lets a presenter control slideshow navigation without touching the keyboard or mouse.

Current end-to-end flow:

- sign in through a local lock screen
- open the main presentation-control app
- start camera tracking
- use gestures and/or offline voice commands to control slides

## Current User Features

VisionSlide currently supports:

- starting a slideshow
- moving to the next slide
- moving to the previous slide
- exiting the slideshow
- jumping directly to a slide number
- offline voice control
- login authentication before opening the main app
- OTP-based email verification during signup
- in-app account security management
- admin-only user management tools

## Current Gesture Mapping

- Open Palm = Start slideshow
- Fist = Exit slideshow
- Two Fingers = Next slide
- One Finger = Previous slide

## Jump Mode

In jump mode, the app counts raised fingers across up to two hands and jumps to that slide number after the required hold duration.

Current jump range:

- 1 to 10

## Voice Commands

Voice control is offline and uses the local Vosk model.

Examples of supported commands:

- next
- next slide
- previous
- previous slide
- start slideshow
- exit slideshow
- first slide
- last slide
- go to slide five

## Authentication and Account System

VisionSlide now includes a full local authentication layer before the main app opens.

Current behavior:

- sign-in is **email + password only**
- signup includes **email OTP verification**
- forgot-password flow resets password by **registered email**
- passwords are stored as secure PBKDF2 hashes in `visionslide_auth.db`
- login suggestions come from the saved sign-in store, not from all registered users
- `Remember me` controls whether a successful login stays in saved suggestions

If `Remember me` is checked:

- the sign-in email/password is saved locally using Windows-protected storage

If `Remember me` is unchecked:

- that sign-in is not kept in suggestions
- if the email was saved before, it is removed from saved sign-ins after successful login

## Admin Features

The app now includes admin-only tools inside the main app utility menu.

Admin-only capabilities currently include:

- `Manage Users`
- `Manage Admin`
- `Reset User Password`
- `Delete User Account`
- `Remove Saved Sign-In`

Important admin behavior:

- only registered emails can be added as admins
- removing a saved sign-in clears it from all saved-account lists and lock-screen suggestions
- if that user signs in manually again later with `Remember me` enabled, the account appears again normally

Permanent default admin emails:

- `admin@visionslide.local`
- Add admin email addresses from the in-app admin management options.

These default admin emails cannot be removed from the admin list.

Default first-run admin account:

- Username: `admin`
- Email: `admin@visionslide.local`
- Password: `VisionSlide@123`

## Main App UI

The main app currently includes:

- left control panel
- right camera preview panel
- utility side drawer
- live status area
- lock and security window
- quick help window
- about window
- logout / saved-account switcher

The utility drawer currently includes:

- `Lock & Security`
- `👤 Manage Users` for admins only
- `Reset Settings`
- `Quick Help`
- `About VisionSlide`
- `Logout`

## Completed Features

These features are currently implemented in the codebase:

- PySide6 desktop GUI
- live camera preview
- MediaPipe-based hand landmark detection
- gesture classification for control mode
- jump mode using finger counting
- offline voice recognition using Vosk
- slideshow keyboard automation using PyAutoGUI
- optional auto-focus for slideshow windows
- JSON-based settings persistence
- local SQLite-based authentication
- hashed password storage using PBKDF2
- signup OTP verification through SMTP
- Windows-protected local saved sign-ins
- `Remember me` sign-in control
- in-app password, username, and email security management
- admin-only user management tools
- PyInstaller build configuration
- packaged executable output

## Tools and Technologies

Main technologies used in the project:

- Python
- PySide6
- OpenCV
- MediaPipe
- Vosk
- sounddevice
- PyAutoGUI
- pygetwindow
- PyInstaller

## Project Structure

- `main.py` -> application entry point
- `app/main_window.py` -> main GUI and control logic
- `app/login_window.py` -> sign-in, sign-up, forgot-password UI
- `app/auth.py` -> SQLite auth, password hashing, admin email management
- `app/credential_store.py` -> Windows-protected saved sign-ins
- `app/email_service.py` -> SMTP email sending
- `app/otp_service.py` -> OTP generation, expiry, verification
- `app/validators.py` -> form validation rules
- `app/camera_manager.py` -> webcam handling
- `app/hand_detector.py` -> MediaPipe hand detection
- `app/gesture_classifier.py` -> gesture recognition rules
- `app/slide_controller.py` -> slideshow keyboard automation
- `app/voice_listener.py` -> offline speech recognition
- `app/config.py` -> saved settings
- `visionside_settings.json` -> local user settings file, ignored by Git
- `visionslide_auth.db` -> local user database, ignored by Git
- `visionslide_credentials.json` -> saved remembered sign-ins, ignored by Git
- `visionslide_admin_emails.json` -> persistent admin email list, ignored by Git
- `models/` -> hand and voice recognition models

## Requirements

Install dependencies from:

- `requirements.txt`

Important libraries used:

- PySide6
- mediapipe
- opencv-python
- opencv-contrib-python
- pyautogui
- pygetwindow
- sounddevice

## How To Run

From the project folder:

```powershell
python main.py
```

If needed, use the local virtual environment:

```powershell
.venv\Scripts\python.exe main.py
```

## Auto-Restart Development Workflow

For UI work and faster iteration, the project also includes an auto-restart watcher.

Start it once per coding session:

```powershell
.\run_dev.bat
```

Then:

- keep that terminal open
- edit code
- save files
- the app restarts automatically

Related files:

- `dev_autoreload.py`
- `run_dev.bat`
- `.vscode/tasks.json`

## Build

PyInstaller packaging is configured in:

- `main.spec`

Current packaged output:

- `dist/VisionSlide.exe`

## Settings

The app stores settings in:

- `visionside_settings.json`

Current settings include:

- camera index
- control hold frames
- jump hold seconds
- sound enabled
- auto focus presentation
- gesture enabled
- voice enabled
- voice device name
- total slides

## OTP Email Setup

VisionSlide can send real OTP verification emails during signup and in-app email change flows.

To enable OTP delivery, configure these Windows user environment variables:

- `VISIONSLIDE_SMTP_EMAIL`
- `VISIONSLIDE_SMTP_PASSWORD`

Recommended Gmail setup:

- use a separate Gmail account for sending OTP emails
- enable 2-Step Verification on that Gmail account
- generate a Gmail App Password
- store the Gmail address in `VISIONSLIDE_SMTP_EMAIL`
- store the Gmail App Password in `VISIONSLIDE_SMTP_PASSWORD`

Once these are configured and a new terminal is opened, the app can send OTP codes.

## Current Limitations

- `app/main_window.py` is still very large and handles many responsibilities
- runtime device-management logic is still conservative
- there is no formal automated test suite yet
- the workspace is not currently a Git repository
- OTP email sending still depends on local SMTP setup on that machine

## Future Scope

Possible future improvements for the project include:

- refactoring large UI/controller files into smaller modules
- adding automated tests
- improving gesture robustness in difficult lighting
- improving microphone and device UX further
- validating packaged deployment on clean Windows machines
- expanding final documentation and FYP demo material

## Notes For Future Chats

If project chat history is lost, read these files first:

- `README.md`
- `PROJECT_BRIEF.md`
- `PENDING_TASKS.md`

`PROJECT_BRIEF.md` contains deeper project memory and architecture notes.

`PENDING_TASKS.md` contains current status, risks, and likely next work.
