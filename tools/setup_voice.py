"""Download the fixed Brazilian Portuguese voice; no account or external TTS service."""
import hashlib
from pathlib import Path
import ssl
import urllib.request

BASE = Path(__file__).resolve().parents[1] / 'models' / 'piper'
REVISION = '1162a9173d0ce503555aed757976b7a9912eae4c'
ROOT = f'https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}'
VOICE = 'pt_BR-faber-medium'
MODEL_HASH = '858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7'


def install():
    BASE.mkdir(parents=True, exist_ok=True)
    files = {VOICE + '.onnx': f'pt/pt_BR/faber/medium/{VOICE}.onnx',
             VOICE + '.onnx.json': f'pt/pt_BR/faber/medium/{VOICE}.onnx.json',
             'MODEL_CARD': 'pt/pt_BR/faber/medium/MODEL_CARD',
             'REPOSITORY_README.md': 'README.md'}
    for filename, remote in files.items():
        target = BASE / filename
        if filename.endswith('.onnx') and target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == MODEL_HASH:
            print('Modelo ja instalado e verificado.')
            continue
        print('Baixando ' + filename + '...')
        partial = target.with_name(target.name + '.part')
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(ROOT + '/' + remote, context=ssl.create_default_context(), timeout=60) as response, partial.open('wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
                    digest.update(block)
            if filename.endswith('.onnx') and digest.hexdigest() != MODEL_HASH:
                raise RuntimeError('O modelo baixado nao passou na verificacao SHA-256.')
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    print('Voz Piper Faber instalada. Reinicie o programa e escolha a voz no painel.')


if __name__ == '__main__':
    install()
