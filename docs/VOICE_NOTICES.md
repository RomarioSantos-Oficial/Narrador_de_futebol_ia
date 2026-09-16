# Componentes da voz local

## Planejamento local dos comentários

**Qwen3-4B-GGUF**, quantização Q4_K_M, é distribuído pelo projeto Qwen sob Apache-2.0. A execução usa **llama.cpp**, licença MIT, build `b10410` com Vulkan. O modelo seleciona uma abertura e índices de informações fornecidas; o programa valida esses índices e monta o texto com os fatos originais. Não há serviço externo de geração de texto, nem cobrança por comentário.

- Modelo: https://huggingface.co/Qwen/Qwen3-4B-GGUF
- Revisão fixada: `bc640142c66e1fdd12af0bd68f40445458f3869b`.
- SHA-256 do GGUF: `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
- Runtime: https://github.com/ggml-org/llama.cpp/releases/tag/b10410
- SHA-256 do pacote Windows Vulkan: `943f047c39843a8051a750424957852079f740bfeb6a9fa4b155d720b52d576e`.
- As fontes de informações cadastrais e históricas são identificadas separadamente no painel; a licença do modelo não substitui as condições dessas fontes.

## Kokoro

As vozes **Alex** (`pm_alex`), **Santa** (`pm_santa`) e **Dora** (`pf_dora`) usam o modelo **Kokoro-82M v1.0**, em português brasileiro, a 24.000 Hz. O projeto informa licença Apache-2.0 para o modelo; o adaptador `kokoro-onnx` 0.6.1 usa MIT. O adaptador também utiliza `phonemizer` e eSpeak NG, com suas próprias licenças GPL. As vozes são fornecidas pelo modelo; o programa não faz clonagem de vozes.

- Modelo e atribuições dos dados: https://huggingface.co/hexgrad/Kokoro-82M
- Catálogo das vozes: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
- Código e licença do adaptador: https://github.com/thewh1teagle/kokoro-onnx
- Distribuição: https://pypi.org/project/kokoro-onnx/0.6.1/
- Exportação ONNX usada: https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1
- SHA-256 do modelo: `beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a`.
- SHA-256 do conjunto de vozes: `bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d`.
- eSpeak NG: https://github.com/espeak-ng/espeak-ng
- Phonemizer: https://github.com/bootphon/phonemizer

## Piper

O modo de IA usa **Piper TTS 1.8.0**, da Open Home Foundation, instalado separadamente por `requirements-voice.txt`.

- Código e licença GPL-3.0-or-later: https://github.com/OHF-Voice/piper1-gpl/tree/v1.8.0
- Licença do motor: https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/COPYING
- Distribuição: https://pypi.org/project/piper-tts/1.8.0/
- Voz: `pt_BR-faber-medium`, português brasileiro, 22.050 Hz, um falante.
- Origem fixada: https://huggingface.co/rhasspy/piper-voices/tree/1162a9173d0ce503555aed757976b7a9912eae4c/pt/pt_BR/faber/medium
- O cartão dessa voz declara CC0 para o conjunto de treinamento. O repositório de vozes informa MIT em seus metadados. As declarações originais ficam em `models/piper/MODEL_CARD` e `models/piper/REPOSITORY_README.md` após instalar.
- SHA-256 do modelo ONNX: `858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7`.

A geração de voz acontece localmente. Textos de narração seguem do navegador para o servidor local do programa; não são enviados a uma API externa de voz. A primeira instalação baixa o motor, suas dependências e o modelo. As consultas de dados do futebol continuam usando a internet.

O Qwen3 local pode selecionar e ordenar informações dos comentários. A saída é um plano restrito aos fatos fornecidos; o texto factual permanece inalterado. A síntese da voz é feita por Kokoro ou Piper. As licenças desses componentes não concedem direitos sobre transmissões, dados esportivos ou escudos de terceiros. Ao redistribuir o software, mantenha e observe as licenças dos componentes incluídos.
