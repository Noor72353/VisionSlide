@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "dist\VisionSlide\VisionSlide.exe" (
    echo VisionSlide build not found. Run build_exe.bat first.
    exit /b 1
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo Inno Setup compiler not found at:
    echo %ISCC%
    echo Install Inno Setup 6, then run this file again.
    exit /b 1
)

echo Building VisionSlide installer...
"%ISCC%" "VisionSlideInstaller.iss"

if errorlevel 1 (
    echo.
    echo Installer build failed.
    exit /b 1
)

echo.
echo Installer build complete.
echo Output folder: %ROOT%installer
endlocal
