@echo off
setlocal
pushd "%~dp0" || exit /b 1
".venv\Scripts\python.exe" -X utf8 "test_any2any.py"
pause
popd
