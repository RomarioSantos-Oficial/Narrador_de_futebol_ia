"""Use the project interpreter and reuse an already running local panel."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

BASE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8787'


def port_in_use():
    try:
        with socket.create_connection(('127.0.0.1', 8787), timeout=1):
            return True
    except OSError:
        return False


def existing_panel():
    try:
        with urllib.request.urlopen(URL + '/openapi.json', timeout=2) as response:
            return json.load(response).get('info', {}).get('title') == 'Futebol Live Overlay'
    except (OSError, ValueError):
        return False


def check_existing(open_browser=True):
    if not port_in_use():
        return False
    if existing_panel():
        print('O Futebol Live Overlay ja esta aberto na porta 8787.', flush=True)
        print('Para carregar atualizacoes e vozes: feche a janela ANTIGA do servidor com Ctrl+C e abra start.bat uma vez.', flush=True)
        if open_browser:
            webbrowser.open(URL + '/control')
    else:
        print('Outro programa esta usando a porta 8787. Nenhum processo foi encerrado.', flush=True)
    return True


def open_when_ready(process):
    for _ in range(60):
        if process.poll() is not None:
            return
        if existing_panel():
            webbrowser.open(URL + '/control')
            return
        time.sleep(.5)


def main():
    if check_existing():
        return 2
    if '--check' in sys.argv:
        return 0
    python = BASE / '.venv' / 'Scripts' / 'python.exe'
    if not python.is_file():
        print('Execute start.bat para preparar o Python do programa.', flush=True)
        return 1
    process = subprocess.Popen([str(python), '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8787'], cwd=BASE)
    threading.Thread(target=open_when_ready, args=(process,), daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        # Ctrl+C also reaches our console child; let uvicorn finish its shutdown.
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            return process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
