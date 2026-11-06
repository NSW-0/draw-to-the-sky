@echo off
rem Double-click (or use the desktop shortcut) to start "Draw to the Sky".
rem It opens the Sky page and the QR page in your browser.
rem
rem The server runs in its own window (not inside this batch file), so pressing
rem Ctrl+C there stops it right away without Windows asking
rem "Terminate batch job (Y/N)?". If it fails to start, the window stays open
rem so you can read the error.
start "Draw to the Sky" /d "%~dp0" cmd /c "python server.py || pause"
