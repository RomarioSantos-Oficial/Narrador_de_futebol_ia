@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute start.bat uma vez para preparar o programa.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m tools.setup_brain
if errorlevel 1 echo Falha na instalacao. Confira sua conexao e a mensagem acima.
pause
