@echo off
setlocal
cd /d %~dp0

echo ======================================
echo   Womo AI - Lokale Datenbank leeren
echo ======================================
echo.
echo ACHTUNG: Alle lokal gespeicherten Inserate, Captures, Bilder-Referenzen,
echo Preisverlaeufe und Suchdaten in data\womo-ai.db werden geloescht.
echo.
set /p CONFIRM=Zum Fortfahren LOESCHEN eingeben: 
if /I not "%CONFIRM%"=="LOESCHEN" (
  echo Abgebrochen. Es wurde nichts geloescht.
  pause
  exit /b 0
)

if exist data\womo-ai.db (
  del /f /q data\womo-ai.db
  if errorlevel 1 (
    echo.
    echo Loeschen fehlgeschlagen. Bitte Womo AI zuerst beenden und erneut versuchen.
    pause
    exit /b 1
  )
  echo.
  echo Datenbank wurde geloescht.
) else (
  echo.
  echo Keine lokale Datenbank gefunden. Nichts zu loeschen.
)

echo Beim naechsten Start legt Womo AI automatisch eine neue leere Datenbank an.
pause
