@echo off
rem Miky · arranque con consola visible (para ver errores y logs en vivo)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No encontre el entorno .venv.
    echo Corre primero: instalar.bat
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m miky run
pause
