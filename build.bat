@echo off
cd /d "%~dp0"
echo Building ContextClipboard...
pyinstaller --name="ContextClipboard" --windowed --onedir --noconfirm --clean ^
    --hidden-import=win32api ^
    --hidden-import=win32gui ^
    --hidden-import=win32clipboard ^
    --hidden-import=win32con ^
    --hidden-import=win32process ^
    --hidden-import=win32ui ^
    --hidden-import=pystray._win32 ^
    --hidden-import=PIL._tkinter_finder ^
    clipboard_gui.py

if %ERRORLEVEL% neq 0 (
    echo Build failed!
    pause
    exit /b 1
)

echo Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Context Clipboard.lnk'); $s.TargetPath = '%CD%\dist\ContextClipboard\ContextClipboard.exe'; $s.WorkingDirectory = '%CD%\dist\ContextClipboard'; $s.IconLocation = '%CD%\dist\ContextClipboard\ContextClipboard.exe'; $s.Save()"

echo.
echo Done. Shortcut created on Desktop.
echo Executable location: dist\ContextClipboard\ContextClipboard.exe
pause
