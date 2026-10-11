@echo off
setlocal
pushd "%~dp0" || exit /b 1
".venv\Scripts\python.exe" -X utf8 "test_any2any.py"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 "test_extra_formats.py"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 "test_lab_formats.py"
if errorlevel 1 goto failed
echo All checks passed.
pause
popd
exit /b 0
:failed
pause
popd
exit /b 1
