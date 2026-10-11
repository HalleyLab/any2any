@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. Please read README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 "any2any.py"
if errorlevel 1 pause
popd
