@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Inicie start.bat uma vez para preparar o programa.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-voice.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m tools.setup_voice
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m tools.setup_natural_voice
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Nao foi possivel instalar a voz. Confira a mensagem acima e sua conexao.
pause
exit /b 1
