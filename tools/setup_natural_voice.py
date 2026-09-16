"""Install the fixed Kokoro model and Brazilian voices for offline narration."""
import hashlib
from pathlib import Path
import ssl
import urllib.request

BASE = Path(__file__).resolve().parents[1] / 'models' / 'kokoro'
ROOT = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1'
FILES = {
    'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}


def install():
    BASE.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        target = BASE / name
        if target.exists():
            with target.open('rb') as current:
                if hashlib.file_digest(current, 'sha256').hexdigest() == expected:
                    print(name + ' ja instalado e verificado.', flush=True)
                    continue
        print('Baixando ' + name + '...', flush=True)
        partial = target.with_name(name + '.part')
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(ROOT + '/' + name, context=ssl.create_default_context(), timeout=60) as response, partial.open('wb') as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise RuntimeError('Falha na verificacao SHA-256: ' + name)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    print('Vozes Kokoro instaladas: Alex, Santa e Dora. Reinicie o programa.', flush=True)


if __name__ == '__main__':
    install()
