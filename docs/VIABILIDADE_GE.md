# Dados do GE e campo animado

**Atualização em 16/09/2026:** os textos foram integrados ao overlay e à narração, com consulta da página pública a cada 30 segundos. O canal direto retornou 403; não é usado. Consulte [o funcionamento atual e a saída OBS](GE_OBS.md). O diagnóstico manual abaixo continua disponível.

Teste da URL enviada de [CRB x Sport, em 15/09/2026](https://ge.globo.com/al/futebol/brasileirao-serie-b/jogo/15-09-2026/crb-sport.ghtml).

## Resultado concreto

A página pública respondeu normalmente, sem login. Seu HTML contém a configuração `window.trv2`. O diagnóstico lê os valores JSON dessa configuração sem executar JavaScript.

Na amostra consultada foram encontrados:

- Identificação da partida, equipes, campeonato, estádio, árbitros e placar.
- 11 titulares e 12 reservas de cada equipe, nomes, números, posições, técnicos e URLs de fotos/escudos.
- 64 registros com identificador, momento, período, título, texto em português e, quando preenchidos, atleta e equipe. Esse total inclui pré-jogo e resumos automáticos, não apenas ações em campo.
- Estatísticas e dados de classificação/histórico presentes na página.

Os dados vieram da página, não de reconhecimento das imagens enviadas. As imagens serviram para identificar os elementos pretendidos.

## Dois componentes diferentes

Os cartões de texto são lances da cobertura do GE. Podem ser analisados tecnicamente por esse diagnóstico; a reutilização editorial e comercial precisa ser verificada antes da retransmissão dos textos.

O campo é um widget externo da **TheSports**, e não do TheSportsDB. A [parceria oficial com a Globo](https://www.thesports.com/news/detail/87) identifica o produto LiveTracker Pro. O [Live Tracker](https://www.thesports.com/solutions/live-tracker) oferece visualização de ações e teste gratuito; isso não confirma uso gratuito permanente nem autorização para reutilizar o acesso do GE.

O diagnóstico registra apenas o domínio do widget. Não exporta seus parâmetros de acesso e não extrai posição da bola, trajetória ou jogador com posse. Percentual de posse e posição de um lance anterior não determinam quem está com a bola agora. Um campo próprio pode representar eventos confirmados, mas não deve apresentar uma animação estimada como rastreamento real.

## Como repetir o teste

Na pasta do programa, executar no PowerShell:

```powershell
.venv/Scripts/python.exe -m tools.inspect_ge --url https://ge.globo.com/al/futebol/brasileirao-serie-b/jogo/15-09-2026/crb-sport.ghtml --output artifacts/ge-crb-sport-fresh.json
```

Isso faz uma consulta e grava um JSON local. Não seleciona a partida, não altera o overlay, não reproduz áudio e não inicia consultas periódicas.

Para analisar o HTML salvo sem internet:

```powershell
.venv/Scripts/python.exe -m tools.inspect_ge --html artifacts/ge-crb-sport-page.html --output artifacts/ge-crb-sport-diagnostic.json
```

Foram verificados o acesso real à página, a leitura do HTML salvo, preservação de escanteios iguais a zero, estatísticas ausentes como `null`, associação do atleta Reverson e rejeição de entradas inválidas. Os textos completos ficam somente no arquivo de diagnóstico local.

## Limites da integração

A extração inicial e a integração por consultas estão validadas. O HTML pode conter uma fotografia em cache. `currentTime` também é um campo bruto; o relógio exibido pelo navegador pode ser calculado a partir de outros campos. Por isso, o programa usa GE para os textos e mantém placar/relógio da fonte principal.

A integração confere a identidade da partida, acompanha IDs e versões do texto, exclui resumos automáticos, ignora o histórico inicial e prioriza gols na fila de voz. Relatos que contêm indicação de gol anulado não recebem a prioridade de gol confirmado. Textos retirados ou alterados são removidos da fila; correções publicadas podem ser anunciadas como atualização do lance.

A estrutura inspecionada é interna ao site, não uma API pública documentada com estabilidade ou limites garantidos. Uma falha nessa fonte deve preservar as demais fontes já configuradas. Fotos, escudos, textos e widget têm condições de uso distintas; conseguir consultá-los não confirma autorização para uso na transmissão monetizada.
