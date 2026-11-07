@echo off
setlocal
cd /d "%~dp0"

echo Starting League Advisor - Personal Companion...

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py %*
) else if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" main.py %*
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 main.py %*
  ) else (
    python main.py %*
  )
)

if errorlevel 1 (
  echo.
  echo App exited with an error. Press any key to close.
  pause >nul
)
