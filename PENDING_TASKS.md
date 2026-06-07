# VisionSlide Pending Tasks

## Current Status

The project is now a working desktop presentation controller with:

- webcam hand tracking
- control mode gestures
- jump mode finger counting
- offline voice command support
- PowerPoint/slideshow keyboard automation
- local sign-in / sign-up / forgot-password flows
- OTP email verification
- remembered sign-ins with `Remember me`
- in-app lock and security controls
- admin-only user-management tools

## Current Confirmed Gesture Mapping

- Open Palm = Start slideshow
- Fist = Exit slideshow
- Two Fingers = Next slide
- One Finger = Previous slide

## What Is Already Done

- PySide6 GUI created
- live camera preview implemented
- MediaPipe hand detection integrated
- gesture classification integrated
- offline Vosk voice recognition integrated
- settings saved in JSON
- local authentication added with hashed passwords
- polished authentication window with sign in, sign up, and forgot password
- real OTP email verification added
- `Remember me` sign-in behavior added
- saved sign-in suggestions connected to protected local credential storage
- slideshow control through keyboard automation implemented
- admin-only `Manage Users` tooling added
- packaged executable generated

## Important Known Context

- main logic is still concentrated in `app/main_window.py`
- authentication and login UI logic are concentrated in `app/login_window.py`
- `README.md`, `PROJECT_BRIEF.md`, and this file should be updated as the project evolves
- this workspace is not currently a Git repository

## Current Auth / Admin Notes

- sign-in uses **email + password only**
- signup uses OTP email verification
- forgot-password works through registered email
- login suggestions come only from remembered saved sign-ins
- `Remember me` controls whether a sign-in is saved locally
- saved sign-ins are stored in `visionslide_credentials.json`
- admin emails are persisted in `visionslide_admin_emails.json`

Permanent default admin emails:

- `admin@visionslide.local`
- Admin email addresses are managed locally through the application.

These admin emails are protected from removal.

## Likely Pending Work

### Documentation

- keep docs aligned with the current UI and account system
- add screenshots if needed for FYP submission
- add architecture diagram if needed

### Code Structure

- refactor `app/main_window.py` into smaller modules
- separate UI code from gesture/action logic
- reduce duplicated dialog-building logic where practical

### Gesture Improvements

- improve reliability of one-finger detection
- test gesture behavior under different lighting/camera angles
- review accidental trigger risks

### Voice Improvements

- improve microphone selection UX further
- improve feedback when microphone is unavailable
- expand supported command phrases if required
- test recognition accuracy in real presentation conditions

### Device Handling

- continue improving camera/device robustness without breaking runtime stability
- review startup and error messaging around devices

### Jump Mode

- decide whether jump mode should remain 1 to 10 only
- consider better large-slide navigation if required
- verify jump behavior with two hands in real use

### Testing

- test sign-in, signup, forgot-password, and OTP flows carefully
- test `Remember me` and saved sign-in removal logic
- test admin-only actions
- verify SMTP setup instructions on another machine
- add tests for gesture classification helper methods
- add tests for spoken slide number parsing
- add tests for config load/save behavior

### Packaging and Delivery

- verify `.exe` on another Windows machine
- confirm required models are included in packaged output
- confirm SMTP-dependent OTP behavior on deployment machine
- improve release readiness for final FYP demo

## Suggested Next Priorities

1. Stabilize and test the current auth/admin flows.
2. Refactor large logic from `app/main_window.py`.
3. Improve documentation for demo, viva, and future development.
4. Add basic tests for non-UI logic.
5. Validate the packaged application on a clean environment.

## How To Resume In A New Chat

Use a prompt like this:

```text
My FYP project is in C:\Users\PMLS\Desktop\VisionSlide.
Please first read:
- README.md
- PROJECT_BRIEF.md
- PENDING_TASKS.md

Then inspect the codebase and continue from there.
This is VisionSlide, a PySide6 desktop app for presentation control using hand gestures, offline voice commands, and a local authentication/admin system.
```
