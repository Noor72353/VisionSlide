# VisionSlide Project Brief

## Project Identity

**Project name:** VisionSlide

**Current type:** Python desktop application for touchless presentation control

**Primary purpose:** Let a presenter control slideshow navigation using hand gestures and offline voice commands, while protecting app access through a local account system.

## Core Idea

VisionSlide is a Windows desktop app built with PySide6. It combines:

- webcam-based hand tracking
- gesture classification
- offline speech recognition
- keyboard automation for slideshow control
- local authentication and account management

The app is designed for PowerPoint-style presentation scenarios. It can start a slideshow, move forward, move backward, exit the slideshow, and jump to a specific slide.

## Current Tech Stack

- **Language:** Python
- **GUI:** PySide6
- **Computer vision:** OpenCV
- **Hand detection:** MediaPipe Hand Landmarker
- **Voice recognition:** Vosk
- **Audio input:** sounddevice
- **Presentation automation:** pyautogui
- **Window targeting:** pygetwindow
- **Packaging:** PyInstaller
- **Database:** SQLite

## Main Entry Point

- `main.py`

Current startup flow:

1. Create the Qt app.
2. Ensure the default admin exists.
3. Open the login window in maximized state.
4. After successful authentication, open the main window in maximized state.

## Main Modules

### `app/main_window.py`

This is still the main application controller and largest file in the project.

Responsibilities include:

- building the main app UI
- utility menu and dialogs
- lock and security window
- admin-only management windows
- starting and stopping the camera
- processing live video frames
- switching between control mode and jump mode
- reacting to recognized gestures
- reacting to recognized voice commands
- updating live status labels
- loading and saving user settings

### `app/login_window.py`

Handles the full lock-screen experience before the main app opens.

Responsibilities:

- sign in
- sign up
- forgot password
- signup OTP verification
- saved sign-in suggestions
- remember-me behavior
- inline validation and feedback

### `app/auth.py`

Handles local authentication using SQLite and PBKDF2 password hashing.

Current responsibilities:

- create and maintain the `users` table
- create the first-run default admin
- authenticate by email/password
- create users
- check username/email existence
- reset passwords
- update usernames
- manage persistent admin emails
- protect default admin emails from removal

### `app/credential_store.py`

Stores remembered sign-ins using Windows-protected encryption.

Current responsibilities:

- save remembered passwords by email
- load remembered passwords
- delete saved sign-ins
- return saved identities for suggestion lists
- normalize identities case-insensitively

### `app/email_service.py`

Handles SMTP-based email sending for OTP flows.

### `app/otp_service.py`

Handles OTP generation, expiry, and verification rules.

### `app/camera_manager.py`

Handles webcam access.

### `app/hand_detector.py`

Wraps MediaPipe hand tracking using:

- `models/hand_landmarker.task`

### `app/gesture_classifier.py`

Contains gesture recognition rules based on landmark positions.

### `app/slide_controller.py`

Sends keyboard commands to control slides.

### `app/voice_listener.py`

Runs offline speech recognition in a background thread using the local Vosk model.

### `app/config.py`

Loads and saves app settings from:

- `visionside_settings.json`

## Current User-Facing Features

### 1. Main presentation app

The GUI already has:

- left sidebar for controls and settings
- right camera preview panel
- live status strip
- utility side drawer

### 2. Control mode

Current gestures:

- Open Palm -> Start slideshow
- Fist -> Exit slideshow
- Two Fingers -> Next slide
- One Finger -> Previous slide

Stable gesture hold is required before triggering actions.

### 3. Jump mode

Current behavior:

- valid range is 1 to 10 fingers
- user holds the finger count for a configured duration
- app jumps to that slide number

### 4. Voice control

Offline speech recognition is implemented using Vosk.

Current command support includes:

- next
- previous
- start slideshow
- exit slideshow
- first slide
- last slide
- spoken slide numbers
- phrases like `go to slide five`

### 5. Local authentication

The app now requires login before access to the main window.

Current behavior:

- sign-in is email-only
- signup includes OTP verification by email
- forgot-password works through registered email
- passwords are hashed with PBKDF2
- remembered sign-ins use Windows-protected local storage
- saved email suggestions come from remembered sign-ins, not all users
- `Remember me` controls whether a login stays in saved suggestions

### 6. Lock & Security

Inside the main app, users can manage:

- current account view
- username changes
- email changes with OTP
- password changes

### 7. Utility menu

The utility side drawer currently includes:

- `Lock & Security`
- `👤 Manage Users` for admins only
- `Reset Settings`
- `Quick Help`
- `About VisionSlide`
- `Logout`

### 8. Admin-only management

Admin accounts can open `Manage Users` and access separate windows for:

- `Manage Admin`
- `Reset User Password`
- `Delete User Account`
- `Remove Saved Sign-In`

Current admin rules:

- only registered emails can be promoted to admin
- default admin emails are permanent
- admin accounts are excluded from non-admin delete/remove flows

Permanent default admin emails:

- `admin@visionslide.local`
- Admin email addresses are managed locally through the application.

### 9. Logout and account switching

The logout dialog now acts as a saved-account switcher.

Current behavior:

- shows current account and other saved accounts
- current account is marked but not switchable
- saved accounts can be clicked for account switching
- `+ Add Another Account` lets the user go back to lock screen and add another account

### 10. OTP email verification

The app can send OTP verification codes during:

- signup
- in-app email change

Current behavior:

- OTP codes are generated locally with expiry
- email delivery uses SMTP
- environment variables are used for the sender credentials

## Current Runtime Flow

1. App starts from `main.py`.
2. Login window opens maximized.
3. User signs in, signs up, or resets password.
4. After successful authentication, `MainWindow` is created.
5. Settings are loaded from JSON.
6. Camera, hand detection, slide control, cooldown, and voice components are initialized.
7. User starts camera.
8. Timer updates frames continuously.
9. Hand landmarks are detected from the live frame.
10. Depending on selected mode:
   - control gestures are classified and mapped to slide actions, or
   - finger count is used for jump mode
11. If voice is enabled, speech recognition runs in a background thread and triggers slide actions.
12. Camera preview and status labels update continuously.

## Models and Assets

### Hand tracking model

- `models/hand_landmarker.task`

### Voice model

- `models/vosk-model-small-en-us-0.15`

### Current notable UI assets

- `assets/visionslide_app_icon.svg`
- `assets/password_eye_windows.svg`
- `assets/password_eye_windows_off.svg`
- `assets/lock_security_icon.svg`
- `assets/camera_placeholder.svg`
- `assets/checkbox_checked_soft.svg`

## Current Strengths

- clear FYP purpose
- working desktop GUI
- gesture pipeline is connected end to end
- offline voice control is integrated
- local authentication system is now substantial
- admin-only account management is present
- remembered sign-ins are under user control through `Remember me`
- packaged executable already exists

## Current Limitations

### 1. `app/main_window.py` is still very large

UI, dialogs, state, camera logic, gesture logic, voice logic, and many helper behaviors remain concentrated in one file.

### 2. Documentation must keep being updated

The app has changed a lot, especially in authentication and admin features, so docs need to stay aligned as the project evolves.

### 3. Runtime device behavior is intentionally conservative

The project currently favors stability over aggressive runtime device refresh.

### 4. No formal automated test suite is present

There are still no unit or integration tests in the repo.

### 5. Workspace is not under Git

This folder is not currently a Git repository, so version history is still missing.

### 6. OTP portability depends on machine setup

OTP works only where the SMTP environment variables are configured unless a future in-app sender-config system is added.

## Likely Near-Term Next Steps

Recommended next work areas:

1. Refactor `app/main_window.py` into smaller modules.
2. Add automated tests for auth, config, OTP, and non-UI helpers.
3. Validate the packaged `.exe` on another clean Windows machine.
4. Keep README and project notes aligned with the current UI.
5. Initialize Git if safer version tracking is needed.

## Working Memory Note

This file is meant to preserve project context so future work can continue even if chat history is lost.

Use this brief together with:

- `README.md`
- `PENDING_TASKS.md`
- the actual codebase

as the current source of truth.
