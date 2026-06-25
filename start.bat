@echo off
title AES Stoerungsmanagement
cd /d "%~dp0"

:: Python pruefen
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo FEHLER: Python nicht gefunden. Bitte Python 3.10+ installieren.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Abhaengigkeiten installieren (nur beim ersten Start oder bei Updates)
python -m pip install -q -r requirements.txt

:: Datenbank initialisieren (falls noch nicht vorhanden)
python -c "from app import app, init_db; app.app_context().__enter__(); init_db()"

:: App starten
echo.
echo  AES Stoerungsmanagement laeuft auf http://localhost:5000
echo  Im Netzwerk erreichbar unter http://%COMPUTERNAME%:5000
echo.
echo  Zum Beenden: Dieses Fenster schliessen
echo.
python app.py
pause
