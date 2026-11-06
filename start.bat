@echo off
rem Double-click (or use the desktop shortcut) to start "Draw to the Sky".
rem It opens the Sky page and the QR page in your browser.
rem Close this window (or press Ctrl+C) to stop.
title Draw to the Sky
cd /d "%~dp0"
python server.py
if errorlevel 1 pause
