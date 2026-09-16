"""Install a pinned, verified local Qwen model and llama.cpp Vulkan runtime."""
import hashlib
import os
from pathlib import Path
import ssl
import urllib.request
import zipfile

BASE = Path(__file__).resolve().parents[1] / 'models' / 'brain'
MODEL_NAME = 'Qwen3-4B-Q4_K_M.gguf'
MODEL_URL = 'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/' + MODEL_NAME
MODEL_SHA = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
RUNTIME_NAME = 'llama-b10410-bin-win-vulkan-x64.zip'
RUNTIME_URL = 'https://github.com/ggml-org/llama.cpp/releases/download/b10410/' + RUNTIME_NAME
RUNTIME_SHA = '943f047c39843a8051a750424957852079f740bfeb6a9fa4b155d720b52d576e'


def download(name, url, expected):
    target = BASE / name
    if target.is_file():
        with target.open('rb') as current:
            if hashlib.file_digest(current, 'sha256').hexdigest() == expected:
                print(name + ' verificado.', flush=True)
                return target
    partial = target.with_suffix(target.suffix + f'.{os.getpid()}.part')
    print('Baixando ' + name + '...', flush=True)
    try:
        digest = hashlib.sha256()
        received, last_report = 0, 0
        with urllib.request.urlopen(url, context=ssl.create_default_context(), timeout=60) as response, partial.open('wb') as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
                received += len(block)
                if received - last_report >= 128 * 1024 * 1024:
                    print(f'{received // (1024 * 1024)} MB recebidos...', flush=True)
                    last_report = received
        if digest.hexdigest() != expected:
            raise RuntimeError('Verificacao SHA-256 falhou: ' + name)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def install():
    BASE.mkdir(parents=True, exist_ok=True)
    archive = download(RUNTIME_NAME, RUNTIME_URL, RUNTIME_SHA)
    runtime = (BASE / 'runtime').resolve()
    runtime.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if not (runtime / member.filename).resolve().is_relative_to(runtime):
                raise RuntimeError('Caminho invalido no pacote do runtime.')
        zipped.extractall(runtime)
    download(MODEL_NAME, MODEL_URL, MODEL_SHA)
    print('Qwen3 instalado. Abra start.bat e use Preparar IA no painel.', flush=True)


def install_once():
    # Windows releases this lock even if a download is interrupted or its console closes.
    import msvcrt
    BASE.mkdir(parents=True, exist_ok=True)
    with (BASE / 'install.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('A instalacao da IA ja esta em andamento em outra janela. Aguarde terminar.', flush=True)
            return
        try:
            install()
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    install_once()
