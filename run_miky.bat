@echo off
rem Miky · arranque normal (sin ventana de consola)
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo No encontre el entorno .venv.
    echo Corre primero: instalar.bat
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m miky run
