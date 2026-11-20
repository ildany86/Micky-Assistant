@echo off
rem Miky · arranque normal (sin ventana de consola)
rem Usa el supervisor: si la app se cae, la vuelve a levantar sola.
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo No encontre el entorno .venv.
    echo Corre primero: instalar.bat
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m miky supervise
