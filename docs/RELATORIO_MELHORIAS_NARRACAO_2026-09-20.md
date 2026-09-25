# Relatório de avaliação e melhorias do Futebol Live Overlay

Data: 20/09/2026. Avaliação da cópia local do programa, incluindo as correções de leitura de lances feitas nesta conversa.

**A prioridade é tornar a narração correta, rastreável e bem organizada. Depois disso, ajustar textos, ritmo e timbres.** O programa já tem uma estrutura aproveitável: dados automáticos, duas funções de voz, saída independente para o OBS, comentários, escalações e personalização visual. Os maiores problemas encontrados estão na escolha do que falar, na identificação dos eventos, nos textos de jogadores e na clareza dos controles.

Este documento apresenta diagnóstico e propostas. Nesta etapa não foram alteradas configurações de transmissão nem implementadas as melhorias descritas. Os exemplos de falas são sugestões editoriais, não relatos de uma partida real.

## 1. O que foi avaliado e o que os resultados significam

Foram examinados servidor e inicialização, integrações de dados, captura GE, contexto de clubes e jogadores, classificação dos eventos, fila de narração, IA de texto, síntese de voz, sessão de áudio, controles, overlay, documentação e testes.

A avaliação combinou leitura do código, consulta somente de leitura ao servidor local, testes automatizados e simulações isoladas no Edge com voz falsa. As simulações não reproduziram narração audível. Não houve avaliação auditiva comparativa dos timbres; por isso, não seria correto declarar que uma voz é a melhor para você ou prometer qualidade emocional sem ouvi-la.

**Resultado da suíte completa:** 104 testes executados; 95 passaram; 8 falharam e 1 apresentou erro; nenhum foi ignorado. Execução em aproximadamente 22,5 segundos. As nove ocorrências também estavam presentes antes das correções da etapa anterior. Isso não equivale a nove defeitos independentes: parte das expectativas precisa ser confrontada com o comportamento desejado, especialmente limites de fila e roteiros.

A consulta local mostrou Kokoro Alex, Santa, Dora e Piper Faber disponíveis. A configuração salva usava Dora na narração, Alex nos comentários, velocidade 1,0, modo dinâmico, comentários a cada 30 segundos, curiosidades e escalações ativadas, chamadas do canal a cada 5 minutos e saída OBS. O Qwen estava instalado, mas não estava pronto naquele instante. A partida já aparecia encerrada; esse retrato não permite concluir que o áudio ou a IA tenham falhado durante o jogo.

## 2. Como o programa funciona hoje

| Parte | Função atual | Avaliação |
|---|---|---|
| Servidor Python/FastAPI | Guarda o estado e distribui atualizações por WebSocket | Base adequada para o uso local |
| ESPN e fontes opcionais | Placar, situação, estatísticas, escalações e eventos conforme cobertura | Precisam preservar melhor identidade e histórico dos eventos |
| Captura GE | Consulta a página pública e extrai textos editoriais | Acrescenta lances, mas tem atraso e disponibilidade próprios |
| Narrador JavaScript | Decide o que entra na fila e o que interrompe outras falas | Principal área a estabilizar |
| Comentários e contexto | Montam panoramas estatísticos, perfis e curiosidades | Há bons recursos e também textos sem sustentação factual |
| Qwen local | Seleciona abertura e informações fornecidas para comentários | Não é um narrador que observa o jogo |
| Kokoro/Piper | Transformam o texto em áudio local | A qualidade depende também do texto e do tempo de geração |
| Página `/audio` | Reproduz áudio no OBS com controle de exclusividade | Boa separação em relação ao painel |
| Painel `/control` | Configura a transmissão | Esconde alguns recursos internos e precisa explicar o estado da leitura |
| Página `/overlay` | Exibe placar, lances e demais gráficos | Precisa de melhor legibilidade e hierarquia |

O caminho básico é: **fonte de dados → interpretação do lance → seleção e fila → texto falado → geração de voz → reprodução no OBS**. Um texto pode aparecer no overlay sem ter passado por todas as etapas de áudio.

O programa trabalha com os dados recebidos. Não existe, no fluxo analisado, interpretação de vídeo capaz de acompanhar cada passe ou drible.

## 3. Problemas que devem ser tratados primeiro

### 3.1. Perfis de jogadores afirmam qualidades que a fonte não forneceu

Em `backend/club_context.py:48`, a função que escreve perfis acrescenta frases como “controla o ritmo”, “tem visão de jogo” e “traz segurança” com base na posição do jogador. Essas avaliações não vêm de análise da partida ou de um perfil técnico comprovado. A seleção varia pelo nome do atleta, não pelo seu desempenho.

O mesmo trecho usa “Olho no lance com…” para uma curiosidade cadastral, embora nenhum lance do jogador tenha sido informado. Também junta nascimento e nacionalidade como “Nascido em [data], na Brasil”. Nacionalidade não comprova o local de nascimento. Há ainda a expressão inadequada “presença decorativa no setor”.

**Melhoria:** retirar elogios automáticos, separar nascimento de nacionalidade e usar apresentação neutra. Exemplo: “Uma informação sobre [jogador]: nasceu em [data] e atua como [posição].” Cada campo deve aparecer somente se estiver disponível. Uma frase sobre participação no lance exige um evento correspondente.

### 3.2. O mesmo gol pode ser narrado novamente quando o identificador muda

O módulo usado pelas páginas reais, `static/match-events.js:3`, forma a chave pelo identificador e revisão/texto. Se uma fonte troca o identificador numérico de um lance igual, ele pode parecer novo. A simulação com os módulos reais confirmou duas leituras do mesmo gol quando o identificador passou de 101 para 102.

Há uma interpretação alternativa dentro de `static/narration.js:2`, usada pelos testes que não carregam `match-events.js`. Ela se comporta de outra maneira. Assim, um teste pode passar sem representar o programa real.

**Melhoria:** manter uma única implementação e carregar nos testes os mesmos módulos das páginas. Usar identificação por fonte, partida, período e evento, com uma estratégia complementar para identificadores instáveis. Essa estratégia não pode juntar dois lances diferentes só porque ocorreram no mesmo minuto.

### 3.3. Gol anulado perde a classificação que deveria cancelar o anúncio anterior

Em `static/match-events.js:6`, “gol anulado” e `kind: cancelled` retornam a categoria genérica `event`. Já `static/narration.js:490` espera `cancelled`, `correction` ou `review` para limpar anúncios de gol pendentes.

A simulação confirmou que, antes da correção do placar, o gol antigo pode continuar na fila junto do aviso de anulação.

**Melhoria:** preservar a categoria “gol anulado”, vincular a correção ao lance original, cancelar o áudio pendente correspondente e anunciar a correção. Não celebrar novamente um lance em revisão.

### 3.4. Pausa, reconexão e mudança de fonte ainda podem reler o histórico

Os testes mostram reapresentação de eventos nessas transições. Há um problema concreto em `static/narration.js:441`: o estado atual é substituído antes da leitura de `previousSource`, prejudicando a detecção da troca de fonte. A reconstrução do conjunto de eventos vistos em `baseline()` também precisa distinguir início, retomada e reconexão.

**Melhoria:** definir regras próprias para cada operação. Ao retomar depois do microfone, seguir a preferência explícita do usuário sobre recuperar ou ignorar os lances da pausa. Reconectar não deve anunciar automaticamente tudo o que já foi narrado.

### 3.5. Valores zero aparecem errados nos controles

`static/channel-controls.js:13` preenche campos com `settings[key] || ''`. Isso transforma zero em vazio. A simulação no Edge confirmou que intervalo zero deixa o seletor sem opção e volume zero aparece como 0,5 no controle deslizante. Uma gravação posterior das preferências pode enviar esse valor incorreto.

**Melhoria:** preservar zero com uma verificação de ausência, como `??`, e testar o ciclo carregar → mostrar → salvar. Trata-se de correção funcional, não apenas visual.

### 3.6. Dados antigos podem receber aparência de informação recente

`backend/ge_feed.py:145` atualiza o horário geral do estado ao publicar situação do GE, inclusive mensagens de erro. `static/radio-commentary.js:83` usa esse horário geral para avaliar se estatísticas são recentes. Uma atualização do GE não atualiza necessariamente as estatísticas da fonte principal.

**Melhoria:** guardar horários separados para placar, estatísticas, escalações e GE. Cada comentário deve consultar a idade do dado que realmente utiliza. Este achado foi confirmado pela leitura dos caminhos do código; não foi medido em uma transmissão prolongada.

## 4. Leitura de lances: o que já melhorou e o que falta

Na etapa anterior foram corrigidos filtros que desativavam a elegibilidade de um lance na consulta seguinte, descartavam certas novidades recebidas com atraso e eliminavam lances após 45 segundos de espera. Também foi tratado o início do jogo informado pelo GE enquanto a fonte principal ainda indicava pré-jogo.

Essas correções reduzem perdas. Porém, **conservar todos os lances indefinidamente não resolve a gestão do atraso**. Uma simulação confirmou que 100 eventos podem permanecer na fila. O áudio pode continuar falando de jogadas antigas enquanto o jogo avança.

É necessário registrar o estado de cada evento: recebido, selecionado, aguardando voz, gerando áudio, reproduzindo, concluído, interrompido ou descartado com motivo. Hoje, a marcação de visto ocorre ao colocar o lance na fila; isso não comprova que ele foi ouvido até o fim.

Proposta de política:

| Conteúdo | Tratamento proposto |
|---|---|
| Gol, gol anulado, correção de placar | Prioridade máxima; preservar e relacionar anúncio e correção |
| Cartão vermelho, pênalti e revisão | Prioridade alta e linguagem correspondente ao estado informado |
| Substituição e chance relevante | Leitura curta; agrupar quando fizer sentido e houver dados suficientes |
| Lance comum | Resumir ou dispensar se a fila estiver atrasada, registrando o motivo |
| Estatística e curiosidade | Entrar apenas em uma pausa real |
| Like e patrocínio | Ceder lugar ao jogo e respeitar um intervalo mínimo |

Os limites devem considerar **segundos estimados de áudio**, além da quantidade de itens. Um limite inicial de 15–20 segundos por comentário é uma proposta para testar; não é desempenho medido nem obrigação do motor de voz. Se um lote contiver dez frases de quinze segundos, são aproximadamente dois minutos e meio de áudio, antes de novas chegadas.

Também é preciso preservar eventos além da janela visual: o caminho ESPN e parte das fontes opcionais restringem a lista a seis eventos. Uma rajada maior entre consultas pode ocultar acontecimentos antes da leitura.

## 5. Como melhorar as locuções e os textos falados

### Separar texto recebido, texto exibido e texto falado

Guardar o texto original da fonte, uma versão curta para o gráfico e uma versão preparada para voz. A adaptação deve preservar nomes, ações, números, negações e situação de revisão. Não transformar uma nota de pré-jogo em lance ao vivo.

O texto falado deve usar frases curtas, uma ideia por frase e sujeito claro. Evitar repetir minuto, período, placar e nome completo de ambos os clubes em toda entrada. As informações completas continuam acessíveis no painel.

Revisar singular e plural: a montagem atual pode dizer “Aos 1 minutos”. Usar “Um minuto de jogo” ou “No primeiro minuto”, conforme o contexto. No segundo tempo, conservar a convenção de relógio da fonte e explicar os acréscimos sem transformá-los em um minuto diferente.

| Situação | Forma atual ou problema observado | Exemplo de proposta |
|---|---|---|
| Início do jogo | “Aos 0 minutos. Primeiro tempo. Bola rolando. Começa o jogo!” | “Bola rolando! Começa a partida.” |
| Pré-jogo | Acréscimo de títulos e marcadores na leitura | “Os jogadores se cumprimentam após o hino. A partida começa em instantes.” |
| Estatística | “Nas finalizações, Casa tem 6 e Fora, 2” | “[Mandante] finalizou seis vezes; [visitante], duas.” |
| Chutes no alvo | “No gol, são 1 a 0”, que pode soar como placar | “Nas finalizações no alvo, uma a zero.” |
| Perfil | “Olho no lance… na Brasil… tem visão de jogo…” | “Uma informação sobre [jogador]: atua como [posição] e veste a camisa [número].” |
| VAR | Celebração enquanto existe revisão | “O lance está em revisão. Aguardamos a confirmação.” |
| Anulação confirmada | Gol anterior permanece na fila | “Gol anulado, segundo a atualização da fonte.” |
| Substituição | Lista pouco fluida ou evento omitido | “Mudança no [time]: sai [jogador], entra [jogador].” |
| Correção | Repetição do anúncio antigo | “Correção da informação anterior: [informação confirmada].” |

Os exemplos dependem dos campos realmente disponíveis. Não mencionar pênalti, defesa, chute ou jogador ausente da informação recebida.

### Dar funções diferentes às duas vozes

O narrador anuncia a ação e mantém o ritmo. O comentarista acrescenta uma informação útil, preferencialmente diferente do que acabou de ser dito. Evitar que o comentarista apenas repita o lance com outras palavras.

Exemplo baseado em dados hipotéticos: narrador — “Escanteio para o [time].” Comentarista — “É o quarto escanteio da equipe.” A segunda fala depende de estatística atualizada que confirme o número; não pode ser deduzida da simples presença do lance.

### Corrigir a seleção de comentários

Em `static/narration.js:409`, `radio.next()` retorna um texto, mas um caminho de seleção trata a resposta como objeto. Na simulação, uma estatística foi marcada como usada sem ser narrada. O programa então parece ficar em silêncio apesar de ter informação nova.

A biblioteca também pode escolher uma nota de outro jogador quando o clube coincide com o filtro (`static/narration.js:313`), e um caminho periódico ignora o próximo horário permitido (`static/narration.js:390`).

**Melhoria:** selecionar, validar e confirmar a leitura em etapas separadas. Exigir correspondência de jogador quando esse filtro foi preenchido. Aplicar a mesma regra de intervalo a todos os caminhos da biblioteca.

### Criar uma biblioteca editorial revisada

Organizar textos por abertura, pré-jogo, lance, intervalo, retomada, encerramento e mensagem do canal. Cada item deve ter assunto, time/jogador quando aplicável, fonte, data de revisão, condição de uso e intervalo de repetição. Variar a construção das frases sem mudar os fatos.

Priorizar textos que acrescentem informação. Repetir adjetivos como “qualidade”, “inteligência” e “presença” para todos os atletas produz aparência artificial e não melhora o conteúdo.

## 6. Vozes, pronúncia, ritmo e áudio

As quatro vozes locais estão disponíveis nesta instalação. O catálogo oficial do Kokoro lista Dora, Alex e Santa para português brasileiro. A escolha de timbre deve ser feita por comparação com os mesmos textos, não por presumir superioridade de uma delas. [Catálogo oficial do Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

O modo dinâmico atual altera principalmente velocidade e pausas. No código, gols recebem um multiplicador de ritmo e comentários ficam um pouco mais lentos. Isso não equivale a direção emocional completa ou a uma voz de narrador esportivo treinada para cada situação.

Recomendações:

1. Comparar as vozes com nomes de atletas, placar, gol, substituição, estatística e encerramento.
2. Começar com velocidade 1,0; experimentar ajustes pequenos, avaliando clareza e tempo da fila.
3. Expor os controles já existentes de velocidade e volume separados para o comentarista.
4. Criar uma tela de pronúncias com nome escrito, forma de leitura e botão de teste. O servidor já aceita um dicionário para isso.
5. Normalizar abreviações, números e pontuação antes da síntese, mantendo o nome oficial no gráfico.
6. Dividir textos longos em fronteiras de frases. Evitar tanto blocos enormes como chamadas isoladas de uma palavra sem teste auditivo.
7. Preparar o motor antes do jogo e medir o tempo da primeira fala e das seguintes.

O próprio projeto Kokoro descreve limitações com textos muito curtos ou muito longos. Isso reforça a necessidade de testar blocos de fala no motor instalado, em vez de adotar um único tamanho ideal para todos os conteúdos. [Orientações oficiais sobre as vozes](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

Uma melhoria posterior é antecipar a geração da próxima fala curta, com cancelamento quando chegar uma correção. Isso exige controle de prioridade para não ocupar o motor com curiosidades enquanto um gol aguarda. Cache de áudios estáticos pode ajudar aberturas e mensagens do canal; deve considerar texto, voz, velocidade e pronúncia.

No caminho de voz nativa, `static/speech-output.js:55` não encaminha o evento de início de fala utilizado para registrar o último lance. Corrigir isso antes de apresentar o recurso “repetir” como equivalente em todos os motores.

No OBS, testar níveis entre as duas vozes e o microfone. Compressor e limitador são recursos disponíveis; ajustar a partir de gravação real, evitando configurações arbitrárias que deformem a fala. [Guia oficial de filtros do OBS](https://obsproject.com/kb/filters-guide).

## 7. O papel correto da IA de texto

O Qwen atual seleciona informações fornecidas e aberturas permitidas. `static/brain-output.js:19` deixa lances fora desse planejamento, e `backend/local_brain.py` valida o resultado. Isso ajuda a manter os fatos originais, mas não torna a IA responsável por corrigir todo texto ruim que chega à voz.

Trocar por um modelo maior não resolve identificadores duplicados, gol anulado mal classificado, estatística antiga ou elogios fixos escritos no programa.

Evolução recomendada: fatos estruturados → modelo de frase revisado → adaptação opcional por IA → conferência de nomes, números e negações → voz. Se houver divergência ou demora, usar a versão determinística já pronta.

Para justificar uma mudança de modelo, medir tempo de resposta no computador, memória, qualidade textual e taxa de alterações indevidas. Esta avaliação não mediu consumo sustentado de CPU/GPU/RAM; portanto, não há fundamento para indicar compra de hardware.

## 8. Organização e clareza do painel

A área principal deve responder rapidamente: **o que chegou, o que está falando e o que acontecerá depois?**

Proposta de disposição:

| Região | Conteúdo |
|---|---|
| Faixa superior fixa | Partida, placar, fase, última atualização de cada fonte e estado do áudio |
| Coluna de operação | Iniciar/parar, pausar para microfone, retomar, pular fala, repetir último lance |
| Área central | Texto atual, papel da voz, tempo de espera e próximos itens |
| Histórico | Lances recebidos, narrados, corrigidos e ignorados, com motivo |
| Configurações secundárias | Vozes, pronúncias, biblioteca, fontes e aparência |
| Prévia | Imagem do overlay e indicação clara de que a prévia não reproduz a voz |

A fila, fala atual e disponibilidade de repetição já são expostas internamente por `static/narration.js:52` e enviadas na sessão de áudio. As ações de pular, repetir e ler roteiro também existem no servidor. Parte da melhoria consiste em trazer esses recursos para a interface, sem reconstruir o sistema.

Textos recomendados para o painel:

| Texto ou situação | Proposta |
|---|---|
| “Aguardando novos lances” | Acrescentar última consulta e motivo quando existir bloqueio |
| “Narrando” antes do áudio começar | Distinguir “Gerando voz” de “Reproduzindo” |
| Lance no gráfico sem áudio | Exibir no painel “Recebido”, “Na fila”, “Narrado” ou motivo do descarte |
| Promessa de comentário em 1–10 minutos | Explicar que depende do modo Rádio, comentários habilitados e fila disponível |
| “IA ativada” | Diferenciar opção habilitada, modelo carregando e modelo pronto |
| Erro de fonte | Manter o dado anterior identificado como desatualizado e informar nova tentativa |

Os controles devem preservar o texto que o usuário está editando durante as atualizações automáticas. Acrescentar confirmação clara de salvamento, navegação por teclado, foco visível e mensagens que não dependam apenas de cor.

Também é necessário transportar a fonte efetiva de cada fala até o painel OBS. Hoje, a indicação genérica de GE pode aparecer quando o conteúdo atual é uma estatística ou uma nota. Um comentário próprio deve ser identificado como comentário do operador; um patrocinador não deve receber atribuição de fonte esportiva.

## 9. Melhorias visuais do overlay e localização dos elementos

A cor de destaque salva, `#1e4334`, é muito escura sobre o fundo também escuro. Ela aparece nos minutos e nos pequenos títulos. Isso ajuda a explicar o verde pouco legível da imagem enviada. A combinação direta das cores tem contraste aproximado de 1,68:1; transparência e imagem de fundo podem alterar o resultado final.

**Melhoria imediata de apresentação:** separar a cor decorativa do clube da cor usada para texto. Minutos, fase e títulos precisam continuar legíveis mesmo com uma identidade visual escura.

O overlay limita o texto de lances a duas linhas (`static/overlay.css:11`) e apresenta até cinco registros, ou dois quando o campo está ativo (`static/overlay.js:42`). Isso é aceitável como resumo, mas o operador precisa conseguir ler o conteúdo completo no painel.

Propostas de visual:

- Placar como informação dominante; minuto e fase logo abaixo ou ao lado.
- Último lance em destaque, com minuto, categoria e texto curto.
- Fonte apresentada de forma discreta e legível, sem disputar atenção em todas as linhas.
- Layout de “placar e lance” para transmissões simples e layout ampliado para estatísticas.
- Posicionamento por zonas e margens de segurança, com prévia do resultado.
- Ajustes de tamanho de fonte e espaçamento, especialmente para leitura em celular.
- Animações curtas apenas para mudanças relevantes, sem reiniciar a cada atualização.

Recomenda-se validar a imagem em 1920×1080, em uma redução para 1280×720 e em uma tela pequena. Os indicadores técnicos de fila e falhas pertencem ao painel de operação; a audiência recebe informações úteis sobre o jogo.

## 10. Fontes de dados, atraso e qualidade dos acontecimentos

No código atual, ESPN e página GE usam intervalos de 30 segundos, Football-Data de 60 segundos e API-Football de 120 segundos. Esses valores não são o atraso total: somam-se publicação, cache, duração da requisição, fila, geração de voz e reprodução. Alguns ciclos aguardam o intervalo depois da consulta terminar.

Prioridades para melhorar os dados:

- Preservar identificadores, período, equipe, jogador e revisão em todos os provedores.
- Manter histórico interno maior do que a quantidade exibida no gráfico.
- Distinguir falta de cobertura de erro temporário e de ausência real de lances.
- Não reduzir agressivamente intervalos antes de medir onde está o atraso.
- Conciliar GE e placar sem afirmar confirmação que outra fonte ainda não forneceu.
- Registrar horário de publicação, recebimento, entrada na fila e início da reprodução.

Dois defeitos adicionais foram reproduzidos: uma retomada identificada como `kickoff` no segundo tempo pode virar “Início da partida” em `backend/match_context.py:72`; substituições `subst` da API-Football podem ser omitidas pelo filtro em `backend/providers.py:157`. Corrigir esses casos antes de ampliar estilos de narração.

## 11. Operação no OBS e diagnóstico

A saída independente `/audio` e a reserva que evita duas páginas narrando ao mesmo tempo devem ser preservadas. A rotina de teste deve cobrir fechar o painel, trocar de cena, perder conexão e reabrir a fonte.

As opções do OBS de desligar a fonte quando invisível e atualizar quando a cena fica ativa descarregam ou recarregam a página. Para continuidade do áudio entre cenas, essas opções precisam ser compatíveis com a forma como a fonte é compartilhada. [Documentação oficial da fonte de navegador](https://obsproject.com/kb/browser-source).

Melhorias recomendadas: diagnóstico visível do dono atual da saída de áudio; botão para abrir o monitor; aviso de versão antiga da página; indicação do último áudio concluído; e resumo exportável dos eventos e erros. Depois de uma atualização, o operador deve saber se servidor, painel e fonte do OBS estão usando a mesma versão.

Um erro de síntese atualmente pode parar o narrador e limpar a fila, enquanto a preferência global continua ligada. Criar um estado explícito de falha e recuperação, com tentativa limitada e indicação do item afetado. A remoção de um lance da janela mais recente do GE também não deve ser confundida automaticamente com exclusão ou correção desse lance.

Na manutenção, separar instalação de dependências da abertura comum: `start.bat` executa instalação de requisitos ao iniciar. Exibir a versão carregada evita confundir arquivos atualizados com um processo antigo reaproveitado pelo launcher. A recuperação da partida após reinício é uma melhoria possível; hoje a seleção não é persistida. Se implementada, deve usar regras claras para não narrar todo o histórico como novidade.

Atualizar também `docs/GE_OBS.md`: há instruções antigas sobre nunca narrar o conteúdo inicial e sobre descartar acúmulos, que não descrevem completamente as regras atuais. Documentação, testes e comportamento precisam evoluir juntos.

## 12. O que você pode ajustar agora

Estas são sugestões de configuração, não alterações aplicadas:

1. **Desativar temporariamente as curiosidades automáticas** até corrigir os perfis que inventam qualidades e usam frases inadequadas.
2. **Experimentar 60 ou 90 segundos entre comentários**, em vez de 30. Isso dá mais espaço aos lances. Se quiser desligar os comentários periódicos, confirmar o resultado devido ao defeito atual de exibição do valor zero.
3. **Manter duas vozes distintas**, inicialmente em velocidade 1,0, e escolher a dupla por uma gravação comparativa com os mesmos textos.
4. **Espaçar pedidos de like para 10 ou 15 minutos**, se estiverem repetitivos.
5. **Ler escalações antes do início**, usando os botões existentes, e evitar blocos longos durante a bola rolando.
6. **Clarear o destaque visual** para tornar minutos e títulos legíveis.
7. **Usar comentários próprios curtos e revisados**, evitando promessas de atuação e dados sem confirmação.
8. **Gravar um ensaio curto** com um gol, uma anulação, uma substituição, um comentário e uma pausa para microfone; ouvir depois o resultado.

Esses ajustes reduzem excesso de fala e melhoram a clareza, mas não substituem as correções de lógica descritas neste relatório.

## 13. Plano de implementação por prioridade

| Etapa | Trabalho | Critério de conclusão |
|---|---|---|
| P0 — Correção factual | Retirar avaliações inventadas; revisar nascimento/nacionalidade; tratar gol anulado | Nenhuma afirmação acrescentada sem dado correspondente nos cenários de teste |
| P0 — Consistência | Unificar identidade de eventos e módulos usados pelos testes; corrigir pausa/troca de fonte | Mesmo lance não é narrado novamente em atualizações ou retomadas previstas |
| P0 — Controles | Preservar valores zero; corrigir seleção de estatísticas e notas de jogadores | Carregar e salvar mantém valores; comentário selecionado é o que entra na fila |
| P1 — Fila e diagnóstico | Estados por evento, confirmação de reprodução, limite por duração e histórico | Toda perda, interrupção ou dispensa tem motivo verificável |
| P1 — Qualidade dos dados | Horários por fonte, período correto, substituições e histórico maior | Atualização do GE não torna estatística antiga artificialmente recente |
| P1 — Locução | Frases por situação, texto próprio para voz, pronúncias e controles separados | Exemplos revisados passam por teste auditivo com dados preservados |
| P2 — Interface e visual | Monitor de fila, pular/repetir, contraste, tipografia e layouts | Operador identifica o estado do lance sem abrir arquivos ou ferramentas técnicas |
| P2 — Desempenho | Aquecimento, métricas, cache limitado e geração antecipada | Ganho medido sem atrasar eventos prioritários ou tocar áudio cancelado |
| P3 — Expansão | Novas vozes, estilos e fontes, após comparar resultados | Melhoria demonstrada em gravações e testes repetíveis |

Não há estimativa de dias neste relatório: o tempo depende da decisão sobre retomada de lances, da abrangência da interface e do desempenho medido no computador.

## 14. Como validar que a próxima versão ficou melhor

Criar um ensaio reproduzível com pré-jogo; início recebido com atraso; múltiplos lances no mesmo minuto; gol; revisão; anulação; cartão; substituição; intervalo; retomada; fim de jogo; e correção após o encerramento.

Repetir com queda de conexão, pausa para microfone, troca de fonte e troca de cena. Os testes de navegador devem carregar exatamente os scripts de produção. O ensaio atual é uma base útil, mas deve incluir dados brutos e atualizações gravadas para exercitar também os normalizadores.

Registrar:

| Indicador | Como medir | Resultado desejado |
|---|---|---|
| Duplicação | Leituras por identidade e revisão do evento | Zero duplicações indevidas no ensaio |
| Perda | Eventos recebidos versus concluídos ou dispensados com motivo | Nenhum desaparecimento silencioso |
| Correção | Situação do áudio original após revisão/anulação | Anúncio pendente cancelado e correção apresentada |
| Atraso | Publicação → recebimento → voz pronta → reprodução | Identificar separadamente cada parcela |
| Fila | Duração estimada, maior espera e quantidade de itens | Permanecer dentro da política definida para cada tipo |
| Pronúncia | Gravação de nomes e termos selecionados | Leitura compreensível e consistente |
| Naturalidade | Comparação dos mesmos textos e avaliação humana | Menos repetição, pausas adequadas e frases completas |
| Operação | Tarefas do operador sem ferramentas técnicas | Entender rapidamente o que está falando ou bloqueado |

Além dos novos cenários, revisar as nove ocorrências atuais da suíte. Não basta alterar a expectativa de um teste para fazê-lo passar: o comportamento esperado deve estar documentado e cobrir a experiência real no OBS.

## 15. Arquivos de referência para executar o plano

Os números de linha correspondem à cópia analisada e podem mudar após edições.

| Área | Referências principais |
|---|---|
| Servidor e operação | `main.py:75`, `launcher.py:52` |
| Elegibilidade e atualizações GE | `backend/ge_feed.py:145`, `backend/ge_feed.py:205` |
| Perfis e afirmações sobre jogadores | `backend/club_context.py:48`, `backend/club_context.py:109` |
| Período e eventos de provedores | `backend/match_context.py:72`, `backend/free_feed.py:146`, `backend/providers.py:157` |
| Identidade e gol anulado | `static/match-events.js:3`, `static/match-events.js:6` |
| Fila, confirmação e comentários | `static/narration.js:172`, `static/narration.js:228`, `static/narration.js:264`, `static/narration.js:390` |
| Transições e correções | `static/narration.js:441`, `static/narration.js:490` |
| Idade dos dados estatísticos | `static/radio-commentary.js:83` |
| Voz e sessão de áudio | `backend/local_voice.py`, `static/speech-output.js:55`, `static/narration-session.js` |
| IA de seleção de comentários | `backend/local_brain.py:42`, `static/brain-output.js:19` |
| Recursos internos de voz e comandos | `backend/narration_channel.py:20`, `backend/narration_channel.py:111` |
| Valores e mensagens do painel | `static/channel-controls.js:13`, `static/channel-controls.js:179`, `static/control.html` |
| Legibilidade dos lances | `static/overlay.js:41`, `static/overlay.css:11`, `appearance.json:5` |
| Testes da experiência real | `tests/test_narration_browser.py:26`, `tests/test_audio_browser.py`, `backend/rehearsal.py` |

**Primeira entrega recomendada:** corrigir os problemas P0 e apresentar no painel o estado de cada lance. A etapa seguinte deve revisar os textos e expor pronúncias e ajustes separados das vozes. Essa sequência permite melhorar a locução sobre uma base que narra os acontecimentos corretos e explica claramente seu funcionamento.
