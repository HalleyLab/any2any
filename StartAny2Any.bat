@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\pythonw.exe" (
    echo Python environment missing. Please read README.md.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -X utf8 "web_app.py"
popd
