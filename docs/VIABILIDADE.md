# Viabilidade da proposta em txt.txt

Avaliação em 15/09/2026. O roteiro com várias fontes, duas vozes alternadas e prioridade para o jogo é viável neste programa. Narração editorial completa de portais exige outra integração e verificação das condições de acesso e reutilização.

| Proposta | Situação |
| --- | --- |
| IA instalada no computador | Qwen3-4B com llama.cpp; seleciona informações e organiza comentários sem alterar os fatos. |
| Narrador e comentarista | Seletores separados; uma única fila de reprodução. |
| Prioridade para gols, cartões e mudanças no placar | Lances interrompem análises. Gols não aguardam o planejador de texto. |
| Titulares e posições | Leitura por equipe ao chegar a escalação completa; botão para solicitar novamente. |
| Jogadores e reservas | Perfis consultados no TheSportsDB e relacionados à escalação por identificação ou nome inequívoco. Prioridade para autores de gols, recém-entrados, capitães e titulares quando identificados. O catálogo gratuito pode omitir atletas. |
| Técnicos e estádios | Informações cadastrais identificadas como tal; não substituem a informação oficial específica da partida. |
| História e torcida | Informações estruturadas e algumas notas históricas verificadas em sites dos clubes. A cobertura inicial dessas notas é limitada a Liverpool e Fulham. |
| Comentários regulares | Intervalo mínimo de 30, 60, 90 ou 120 segundos. Curiosidades podem voltar depois de 10 minutos. Ausência de dados não vira história inventada. |
| GE | Integrado aos textos do overlay e à fila de voz, conforme disponibilidade e correspondência da partida. Consulta da página pública a cada 30 segundos; o canal direto retornou 403 e não é utilizado. Diagnóstico em `tools/inspect_ge.py`. Ver [GE e OBS](GE_OBS.md). |
| Lance! / Vai Score | Não integrados. Ainda faltam URLs concretas de partidas, documentação e condições de acesso para validar esses conectores. |
| Sportmonks | Integração tecnicamente possível, mas ainda não implementada. Seu plano gratuito permanente cobre a Superliga dinamarquesa e a Premiership escocesa; não resolve Premier League grátis. |

## Correções importantes no texto

- Afirmar que nenhuma API oficial existe exigiria confirmação dos portais. Não foi validada uma API pública documentada de GE, Lance! ou Vai Score que corresponda ao serviço descrito.
- CORS é uma regra de acesso aplicada pelo navegador. Uma consulta Python no servidor pode não depender dela, mas continua sujeita a autenticação, limites, termos e bloqueios do provedor. Alterar CORS não transforma um endpoint interno em serviço autorizado ou estável.
- Scraping e endpoints internos podem funcionar tecnicamente, mas dependem do site e podem mudar. Um teste precisa de uma página concreta, identificação segura da partida, tratamento de correções, limites de consulta e análise das condições de reutilização.
- Texto editorial de um portal não equivale a um dado factual como placar ou minuto. Reproduzir automaticamente a narração inteira é diferente de criar comentários próprios com fatos da partida.
- Um provedor pago não garante sozinho autorização para qualquer uso. É necessário conferir cobertura e licença; fontes gratuitas também podem permitir usos específicos conforme seus termos.
- O plano gratuito da API-Football oferece 100 consultas por dia, com restrições de temporadas. Isso não equivale a acesso ilimitado à temporada atual.
- Uma IA local não sabe o que acontece no jogo sem receber dados. Sua memória interna não deve ser usada como fonte atual de elenco, técnico, lesões ou estatísticas.

## Como acrescentar novas fontes

Manter uma fonte principal para placar e relógio, validar identidade e horário antes de complementar informações, preservar fonte/data de cada fato e reutilizar consultas em cache. Um conector editorial experimental deve ser independente dos dados principais: se cair, a narração factual continua. Não habilitar coleta em loop de segundos sem conhecer limites e permissões da fonte.

## Fontes consultadas

- [Sportmonks — plano gratuito e campeonatos](https://www.sportmonks.com/football-api/free-plan/)
- [Sportmonks — funcionamento dos dados de placar ao vivo](https://www.sportmonks.com/football-api/solutions/live-score-api/)
- [API-Football — guia e limites de acesso](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide)
- [API-Football — termos e limites](https://www.api-football.com/terms)
- [TheSportsDB — API gratuita](https://www.thesportsdb.com/api.php)
- [Qwen3 — modelo local](https://huggingface.co/Qwen/Qwen3-4B-GGUF)
- [Liverpool FC — história da Kop](https://www.liverpoolfc.com/news/125-years-story-spion-kop)
- [Fulham FC — história do clube](https://www.fulhamfc.com/club/history/history-of-fulham-football-club)
