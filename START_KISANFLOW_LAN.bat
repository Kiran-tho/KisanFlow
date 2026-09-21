@echo off
cd /d "%~dp0"
echo Starting KisanFlow...
echo.
echo Laptop IP addresses:
ipconfig | findstr /C:"IPv4 Address"
echo.
echo Open the shown Wi-Fi IPv4 address on phones as: http://YOUR_IP:5000
echo.
.\venv\Scripts\python.exe app.py
pause
