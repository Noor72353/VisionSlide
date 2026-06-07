@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

if exist ".venv\Scripts\pyinstaller.exe" (
    set "PYINSTALLER=.venv\Scripts\pyinstaller.exe"
) else (
    set "PYINSTALLER=pyinstaller"
)

echo Building VisionSlide with PyInstaller...
"%PYINSTALLER%" --clean --noconfirm main.spec

if errorlevel 1 (
    echo.
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete.
echo Output folder: %ROOT%dist\VisionSlide
endlocal
