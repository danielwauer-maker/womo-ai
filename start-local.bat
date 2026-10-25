@echo off
setlocal
cd /d %~dp0

echo ======================================
echo   Womo AI - Lokaler Start

echo ======================================

where python >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden.
  echo Bitte Python 3.12 installieren und "Add Python to PATH" aktivieren.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo [1/3] Virtuelle Umgebung wird erstellt...
  python -m venv .venv
  if errorlevel 1 goto :error
)

echo [2/3] Abhaengigkeiten werden geprueft...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :error

if not exist data mkdir data
set DATA_DIR=data

echo [3/3] Womo AI startet lokal auf http://127.0.0.1:8000
start "" http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
exit /b 0

:error
echo.
echo Start fehlgeschlagen. Bitte die Fehlermeldung oben kopieren oder fotografieren.
pause
exit /b 1
