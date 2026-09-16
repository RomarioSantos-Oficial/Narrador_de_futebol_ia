# Futebol Live Overlay

Programa local para OBS/YouTube com placar, estatísticas, lances e narração por voz. Gráficos em `/overlay` e áudio independente em `/audio`.

## GE e áudio direto no OBS

1. Selecione uma partida em **Carregar e acompanhar**. A busca GE confere os dois times e o horário na agenda pública. Se não localizar, informe o link da mesma partida em **Informar cobertura do GE manualmente**.
2. O programa consulta a página pública a cada **30 segundos**, mostra os lances em **Últimos lances** e narra os novos textos recebidos. O canal direto retornou HTTP 403 no teste; esta versão não o utiliza. O atraso da publicação e do cache do GE também conta.
3. **Intervalo entre comentários → Sem comentários por intervalo** desliga os panoramas periódicos. Os lances continuam sendo lidos ao chegar à fila, uma voz por vez, com prioridade para gols.
4. Em **Saída do áudio**, selecione **Diretamente no OBS** e clique em **Iniciar narração**. No OBS, adicione uma **Fonte de navegador** com `http://127.0.0.1:8787/audio` e marque **Controlar áudio via OBS**. Essa fonte é transparente e tem seu próprio canal no mixer.
5. O painel pode ser fechado; mantenha o programa e a fonte de áudio funcionando. Use a mesma fonte existente nas outras cenas. Para continuidade ao trocar de cena, deixe desmarcadas as opções de desligar a fonte quando invisível e recarregar ao ativar. Veja o [guia oficial de fontes de navegador](https://obsproject.com/kb/browser-source).

A página `/audio?monitor=1` mostra o estado do áudio e um botão para ativá-lo, útil para diagnóstico ou pela opção **Interagir** do OBS. Use vozes **Alex, Santa, Dora ou Faber** nas duas funções para a saída OBS. Vozes nativas do Windows continuam disponíveis na saída do painel. Apenas uma página por vez recebe permissão para reproduzir a narração.

As escalações são opcionais: **Ler automaticamente os titulares**, **Ler escalações agora** e **Pular escalações**. Os pedidos de like e inscrição podem ser ativados/desativados e espaçados em 5, 10 ou 15 minutos; entram nas pausas e cedem lugar aos lances.

A leitura GE exige o Microsoft Edge instalado. O programa abre uma instância invisível, sem JavaScript, para ler somente as páginas públicas. Se houver recusa de acesso, a cobertura para e os eventos da fonte principal continuam. Fotos, textos e serviços externos têm condições de reutilização próprias. Detalhes em [GE e OBS](docs/GE_OBS.md).

## Organização dos arquivos

| Pasta / arquivo | Conteúdo |
| --- | --- |
| `start.bat` | Iniciar o programa. |
| `install_voice.bat`, `install_brain.bat` | Instalar ou restaurar as IAs. |
| `main.py`, `launcher.py` | Entrada do servidor e inicialização. |
| `backend/` | Fontes de dados, narração, vozes, aparência e contexto. |
| `static/` | Painel, overlay e página de áudio. |
| `tools/` | Instaladores Python e diagnóstico manual do GE. |
| `tests/` | Testes automatizados. |
| `docs/` | Guias, estudos, licenças e roteiro original. |
| `models/` | Modelos de voz e linguagem instalados. |
| `artifacts/` | Capturas e resultados de diagnóstico. |

Configurações locais: `.env` (chaves), `appearance.json` (visual) e `narration.json` (vozes, saída, opções e ativação). Para executar os testes, use `.venv/Scripts/python.exe -m unittest discover -s tests -q` na pasta principal.

## Iniciar no Windows

1. Extraia a pasta.
2. Dê duplo clique em `start.bat`.
3. O painel abre em `http://127.0.0.1:8787/control`.
4. No OBS, adicione **Fonte > Navegador**.
5. URL: `http://127.0.0.1:8787/overlay`
6. Tamanho recomendado: 1920 x 1080.
7. Marque a opção de atualizar a fonte quando ela ficar ativa, se desejar.

## Modo manual
Funciona sem nenhuma API. Você controla:
- times;
- placar;
- minuto;
- posse;
- chutes;
- chutes no gol;
- escanteios;
- cartões;
- eventos;
- posição visual da bola.

## Teste gratuito automático (sem chave)

1. Reinicie o programa pelo `start.bat` e abra `/control`.
2. Na aba **Partida**, escolha **ESPN** como fonte e selecione o campeonato.
3. Clique em **Buscar ao vivo agora**, selecione a partida e clique em **Carregar e acompanhar**. Para consultar a programação, escolha uma data e use **Buscar jogos da data**.
4. O overlay recebe placar, relógio informado pela fonte, estatísticas e eventos disponíveis a cada 30 segundos.
5. Use **Pausar atualização** para pausar. Editar a partida manualmente também pausa as consultas.

A busca ao vivo mostra apenas partidas em andamento. Se não houver jogo ao vivo no campeonato escolhido, o painel avisa; escolha outro campeonato ou aguarde o início da partida. Partidas encerradas são carregadas uma vez, sem consultas contínuas.

A fonte experimental é o endpoint público da ESPN, consultado sem cadastro ou chave. Não há garantia de disponibilidade, cobertura completa ou ausência de atraso. Estatísticas ausentes aparecem como **—**, eventos podem vir em inglês e a posição real da bola não é fornecida. O relógio acompanha a fonte; não é um cronômetro independente. Reiniciar o programa exige selecionar novamente a partida.

## Gráficos da transmissão e personalização

- O `/overlay` recebe cada atualização por WebSocket, sem recarregar a fonte do OBS. Em caso de queda, tenta reconectar automaticamente.
- O placar inclui escudos automáticos, nomes, relógio, situação e estádio quando disponíveis.
- Estatísticas: posse, finalizações, chutes no gol, passes, precisão de passe, faltas, escanteios, impedimentos, defesas e cartões. A precisão é calculada com passes certos / passes totais. Dados ausentes aparecem como **—**.
- A aba **Jogadores** mostra a escalação inicial, os reservas, substituições e cartões por jogador, conforme a cobertura da ESPN. Antes de a escalação ser divulgada, o painel informa que ela está indisponível.
- Use **Partida**, **Titulares**, **Reservas** e **Tabela** abaixo da prévia para trocar o gráfico exibido no OBS. O modo Partida pode mostrar estatísticas, titulares e últimos lances juntos.
- Na aba **Visual**, escolha fundo transparente, cor sólida, degradê ou uma imagem PNG/JPG/WebP de até 5 MB. Também pode ajustar cores, opacidade, posição do placar, nome do canal e enviar escudos próprios.
- Clique em **Aplicar visual à transmissão**. As preferências ficam em `appearance.json`, e imagens enviadas ficam em `static/uploads`. Essas mudanças não pausam o acompanhamento automático.
- Após atualizar arquivos do programa, feche o servidor antigo, abra `start.bat` e atualize as páginas do painel e do overlay uma vez. Depois disso, os dados da partida continuam chegando automaticamente.

## Narração gratuita em português

Na aba **Partida**, use o cartão **Narração automática**. Escolha uma voz local, clique em **Testar voz** e depois em **Iniciar narração**. Ajuste volume e velocidade como preferir. As opções gratuitas incluem **Kokoro Alex**, **Kokoro Santa** (masculinas), **Kokoro Dora** (feminina), **Piper Faber** e as vozes do Windows. Os modelos de IA sintetizam no servidor local; as vozes do Windows são reproduzidas pelo navegador. Nenhuma delas precisa de chave de API de voz ou cobrança por fala.

Para instalar ou restaurar a IA, execute **install_voice.bat** na pasta do programa, depois reinicie **start.bat** e atualize o painel com **Ctrl+F5**. A instalação baixa o Piper (modelo de aproximadamente 63 MB) e o Kokoro (modelo e vozes de aproximadamente 354 MB), além das dependências. Depois de instaladas, as vozes funcionam sem internet; os dados dos jogos ainda dependem das APIs. A primeira fala carrega o modelo e pode demorar mais. Consulte [as fontes e licenças da voz](docs/VOICE_NOTICES.md). Para as vozes do Windows, use o Edge; se necessário, instale uma voz de Português nas configurações de Fala do Windows.

Clique em **Alex narra + Dora comenta** para selecionar duas vozes no estilo Rádio. Os seletores **Voz do narrador** e **Voz do comentarista** permitem escolher timbres separados para lances e análises; os botões de teste reproduzem cada papel individualmente. Em **Interpretação**, escolha **Dinâmica** para acelerar discretamente os gols, alternar suas chamadas e dar mais pausa aos comentários estatísticos. **Regular** mantém o ritmo selecionado. O Kokoro também ajusta as pausas entre frases; a entonação final depende do modelo. **Testar voz**, no modo dinâmico, reproduz um comentário de teste e um exemplo de gol, identificados como demonstração. Compare Alex, Santa e Dora e escolha o timbre de sua preferência. O modo não simula emoção humana nem transforma estatísticas em jogadas não informadas.

O Qwen3 local seleciona informações recebidas e organiza comentários curtos. O resultado é validado contra as informações fornecidas: nomes, números e texto factual são preservados. Kokoro e Piper geram o áudio. Os lances seguem diretamente para a voz para não esperar o planejador. Sem IA disponível ou com resposta inválida, o texto factual original continua funcionando.

A narração anuncia novos lances e mudanças de placar recebidos após a ativação, sem reler os lances antigos a cada consulta. Ao trocar a partida, descarta a fila anterior. O botão **Parar** interrompe a voz. As configurações ficam salvas no servidor em `narration.json`. Na saída **Neste painel**, fechar a página interrompe o áudio; na saída **Diretamente no OBS**, o áudio continua na fonte `/audio`.

Para acompanhar a **Premier League**, selecione esse campeonato na aba Partida, carregue um jogo e escolha **Rádio · lances e estatísticas** na narração. O modo abre com o panorama dos dados carregados, anuncia lances e alterna comentários curtos sobre finalizações, posse, escanteios e outros números fornecidos. O intervalo mínimo é configurável: 30, 60, 90 ou 120 segundos, ou desligado em **Sem comentários por intervalo**. Os comentários estatísticos usam dados recentes e mudanças nos números. Com curiosidades ativadas, informações cadastrais e históricas também podem preencher as pausas; cada curiosidade só se repete após 10 minutos. A narração encerra após anunciar o resultado final. Lances novos interrompem panoramas estatísticos. O botão **Panorama agora** lê os dados carregados quando você solicitar.

Use **Vou comentar no microfone** para silenciar a voz automática enquanto você participa pelo microfone do OBS. Clique em **Retomar voz automática** para continuar a partir dos dados atuais, sem reler os lances do período da pausa. Esse botão controla apenas a voz do programa; configure o microfone no OBS. A narração continua baseada em dados e não descreve passes, dribles ou ataques que a fonte não tenha informado. Esse modo não altera a frequência nem a licença da fonte, e não garante aprovação para monetização.

Na saída **Neste painel**, mantenha o painel aberto e capture o dispositivo de saída do navegador no OBS. Na saída **Diretamente no OBS**, use a fonte `/audio` e seu canal no mixer; a prévia e o `/overlay` continuam sem reproduzir voz. Não capture novamente o mesmo áudio pelo dispositivo do computador se estiver usando monitoração, para evitar eco.

A fala depende dos eventos fornecidos e acompanha o atraso das consultas. Não é uma narração contínua de cada passe ou ataque. Não descreve ações que a fonte não informou. A implementação usa a [síntese de voz do navegador](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/speak) e seleciona apenas [vozes locais](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService).

## API-Football
Copie `.env.example` para `.env` e preencha:
- `API_FOOTBALL_KEY`
- `FIXTURE_ID`

O programa consulta a partida configurada e sincroniza placar, minuto e estatísticas disponíveis.

## Cérebro local, duas vozes e informações dos clubes

Execute `install_brain.bat` para instalar **Qwen3-4B Q4_K_M** (aproximadamente 2,5 GB) e llama.cpp para Windows. O instalador verifica os arquivos por SHA-256 e evita instalações simultâneas. Depois de instalado, o processamento de texto funciona sem internet; os dados esportivos continuam dependendo das fontes. O modelo usa um processo local, carregado ao clicar em **Preparar IA** ou ao iniciar a narração com essa opção habilitada, e é encerrado junto do servidor.

Na cabine, clique em **Alex narra + Dora comenta** para configurar as vozes. É possível trocar cada uma nos seletores e usar **Testar narrador** / **Testar comentarista**. Uma única fila alterna as falas; gols e eventos novos interrompem análises. A reserva de áudio permite apenas uma página narrando por vez. A síntese usa memória: o programa não grava os áudios em arquivos; os buffers são liberados ao terminar/cancelar cada fala, e a fila é limpa depois do anúncio final.

Com **Ler os titulares com posição** ativado, a chegada dos 11 iniciais dispara a leitura por equipe em blocos curtos, com camisa e posição. Um gol pode interromper essa leitura; os blocos restantes continuam depois dos lances prioritários. **Ler escalações agora** solicita outra leitura dos dados disponíveis. A posição é a fornecida pela API, não uma análise tática criada pela IA.

**Intercalar curiosidades e informações dos clubes** consulta o TheSportsDB para fundação, estádio, localização, apelido, técnico cadastrado e perfis de jogadores identificados na escalação ou no banco. Usa identificação de atleta do provedor quando disponível e nomes inequívocos como alternativa; dados ausentes ou ambíguos são omitidos. Não confunde atletas de outros clubes. O catálogo gratuito pode entregar apenas parte do elenco. A prioridade dos perfis considera autores de gols informados, recém-entrados, capitães e titulares; não é um ranking subjetivo dos melhores jogadores.

A fonte fica abaixo do último comentário. Consultas cadastrais são reutilizadas por até 24 horas; falhas são tentadas novamente mais tarde. A leitura também aproveita a classificação do campeonato. História de estádio usa o ano informado pelo cadastro. Notas de história e torcida verificadas em sites oficiais dos clubes têm cobertura inicial limitada a **Liverpool e Fulham**. O sistema não faz pesquisa irrestrita na web nem inventa histórias para preencher silêncio.

Se aparecer só Faber, clique em **Verificar vozes instaladas** e atualize a página com **Ctrl+F5**. Se as vozes estiverem instaladas mas o servidor estiver usando outro Python, feche a janela antiga com **Ctrl+C** e abra **start.bat** uma vez. O iniciador usa explicitamente o Python da pasta `.venv` e reconhece um painel já aberto na porta 8787, evitando a segunda inicialização normal que causa o erro 10048.

Ao interromper uma fala, a geração que já começou pode levar alguns segundos para terminar no computador. O próximo pedido aguarda no servidor, com prioridade para gols e limite de espera, em vez de repetir solicitações a cada 250 ms. Pedidos cancelados durante essa espera são descartados. O painel distingue **Gerando a voz** de **Narrando**; em caso de sobrecarga, informa a espera e limita as novas tentativas.

O estudo das alternativas de APIs, GE/Lance e scraping está em [estudo de viabilidade](docs/VIABILIDADE.md).

## Outras fontes e comparação

Selecione a fonte na aba **Partida**:

- **ESPN:** teste sem chave, atualiza a cada 30 segundos.
- **API-Football:** cole a chave no painel. Uma consulta por atualização a cada 120 segundos, usando o endpoint que reúne dados da partida. O plano gratuito tem 100 consultas diárias e restrições de temporadas.
- **Football-Data.org:** cole a chave no painel. Consulta a cada 60 segundos; o plano gratuito fornece placares com atraso e pode omitir escalações, minuto e estatísticas.
- **TheSportsDB:** chave pública de teste, usada para consultar agenda, resultados e escudos. Este acesso gratuito não acompanha jogos ao vivo.

As chaves ficam no `.env` local e não são enviadas ao overlay nem devolvidas pelo painel.

O catálogo inclui **64 competições pela ESPN**: séries A/B/C, quatro estaduais, Copa do Brasil, Copa do Nordeste, Copinha, torneios sul-americanos, principais ligas e copas europeias, MLS, Liga MX, ligas asiáticas e australiana, seleções e futebol feminino. Use **Encontrar campeonato** para filtrar por nome ou país, com ou sem acentos. O contador mostra quantas opções existem na fonte selecionada. A presença no catálogo não garante partidas hoje nem todos os detalhes dos lances.

No **Football-Data.org**, há **12 competições do catálogo gratuito**: Brasileirão Série A, Premier League, Championship, La Liga, Bundesliga, Serie A italiana, Ligue 1, Primeira Liga portuguesa, Eredivisie, Champions League, Eurocopa e Copa do Mundo. A seleção utiliza o código próprio de cada campeonato em `/v4/matches`; a chave é enviada pelo cabeçalho `X-Auth-Token`. A disponibilidade por temporada acompanha a [cobertura do provedor](https://www.football-data.org/coverage). O programa remove espaços e quebras de linha colados junto da chave.

O TheSportsDB oferece nove competições mapeadas nesta integração; API-Football mantém sete. Ao trocar a fonte, a lista é ajustada aos campeonatos mapeados nela. Não é necessário contratar um plano para adicionar os campeonatos gratuitos já incluídos.

**Comparar dados da partida** consulta as fontes configuradas e identifica a partida pelos times, mandante/visitante e horário. Se não houver uma correspondência inequívoca, não compara esses dados. O quadro mostra divergências e o minuto informado por cada fonte. Resultados são reutilizados por até cinco minutos para reduzir consultas.

O painel também indica a **fonte recomendada para narrar**: considera lances reconhecidos, estatísticas completas, titulares, presença de relógio e intervalo de consulta configurado. A pontuação mede cobertura observada, não comprova a exatidão dos dados nem a latência real do provedor. Fontes sem chave, com erro ou sem acompanhamento ao vivo não são recomendadas. Uma alternativa com placar ou fase divergente, relógio ausente/mais de três minutos atrás, ou consulta mais de dois minutos anterior à principal também fica fora da recomendação ao vivo. Se outra fonte estiver indicada, **Usar [fonte] para narrar** carrega a mesma partida por ela. O programa descarta os lances anteriores dessa nova fonte para evitar repetição na voz.

Ative **Completar campos ausentes com outras fontes** para preencher estatísticas não informadas, escudos, escalações, histórico, classificação e estádio nas próximas atualizações. Valores existentes, inclusive zero, são preservados. Durante o jogo, estatísticas só são complementadas se fase e placar concordarem, os relógios diferirem no máximo três minutos e as consultas estiverem a no máximo dois minutos de distância. Complementos antigos são retirados até uma nova consulta; escudos e outros dados de contexto continuam disponíveis. O placar e o relógio permanecem sob controle da fonte principal. A origem dos complementos aparece no painel. Essa opção vale durante a sessão e utiliza a cota de cada fonte consultada.

## Histórico, tabela e relatos dos lances

A ESPN fornece, conforme a cobertura, os cinco últimos resultados em todas as competições e a classificação no campeonato da partida. O mais recente aparece primeiro: **V** vitória, **E** empate, **D** derrota. A classificação acompanha a tabela do provedor e pode não incluir a partida ainda em andamento.

A aba **Jogadores** também mostra a tabela completa do campeonato selecionado, com destaque para os dois times da partida. As colunas **PTS, J, V, E, D e SG** são pontos, jogos, vitórias, empates, derrotas e saldo de gols **acumulados no campeonato**, separados do histórico dos últimos cinco jogos. Clique em **Exibir tabela na transmissão** ou **Tabela** abaixo da prévia para exibi-la no OBS. Até 20 clubes aparecem em duas colunas; tabelas maiores e grupos adicionais alternam páginas a cada 12 segundos. Os dados são atualizados junto da partida, sem recarregar o overlay. Sem classificação fornecida pela fonte, o programa informa a indisponibilidade.

Os eventos reconhecidos recebem um resumo em português, com o relato original em inglês abaixo quando disponível. Para eventos desconhecidos, é mostrado um título genérico em português junto ao texto original; não há serviço de tradução automática externa.

Ative **Campo · posição do último lance** na aba Visual. Quando a ESPN fornece coordenadas de um evento, o campo indica essa posição com time e minuto. Isso não representa quem ataca neste instante nem rastreamento contínuo da bola. Sem coordenadas, aparece uma mensagem de indisponibilidade; o modo manual permite mover a marcação.

> A posição da bola mostrada no campo NÃO é tracking físico real. No modo manual você controla a zona visual.
> Para coordenadas reais X/Y da bola seria necessário um provedor de tracking/eventos que forneça esses dados.

## YouTube
O programa não retransmite imagens oficiais do jogo. Ele foi pensado como overlay/gráfico para sua narração, análise,
watch-along ou conteúdo próprio. Para transmitir imagens/áudio oficiais da partida, você precisa dos direitos correspondentes.
