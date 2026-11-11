@echo off
rem Launcher for the uplink data generator GUI
cd /d "%~dp0"
"C:\Users\qin\AppData\Local\Programs\Python\Python314\python.exe" uplink_gui.py
if errorlevel 1 (
  echo.
  echo Failed to start GUI. Press any key to exit.
  pause >nul
)
