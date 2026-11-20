@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Miky - instalacion (una sola vez)
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [x] No encontre Python en el PATH.
    echo     Instalalo desde https://www.python.org/downloads/ y marca
    echo     "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/6] Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 goto :error
) else (
    echo [1/6] Entorno virtual ya existe.
)

echo [2/6] Actualizando pip...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip

echo [3/6] Instalando dependencias (puede tardar varios minutos)...
".venv\Scripts\python.exe" -m pip install --quiet -e ".[voice]"
if errorlevel 1 goto :error

echo [4/6] Preparando el logo y el puente...
if exist "Micky-clear.png" (
    ".venv\Scripts\python.exe" tools\prepare_logo.py
)
".venv\Scripts\python.exe" tools\build_lua.py
if errorlevel 1 goto :error

echo [5/6] Instalando el puente en REAPER...
".venv\Scripts\python.exe" -m miky install-bridge

echo [6/6] Diagnostico:
".venv\Scripts\python.exe" -m miky doctor

echo.
echo Listo. Para usar Miky: doble clic en run_miky.bat
echo La primera vez, clic derecho en el icono -^> Ajustes, y pega tu API key de Gemini
echo (se saca gratis en https://aistudio.google.com/apikey).
echo.
pause
exit /b 0

:error
echo.
echo [x] Algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1
