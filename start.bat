@echo off
title Futebol Live Overlay
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" launcher.py --check
if errorlevel 1 goto end
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist .env copy .env.example .env >nul
".venv\Scripts\python.exe" launcher.py
goto end
:failed
echo Falha ao preparar o programa. Confira a mensagem acima.
:end
pause
