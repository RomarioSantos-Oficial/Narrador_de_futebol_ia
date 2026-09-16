# Narração GE e áudio no OBS

Implementação de 16/09/2026. Os controles são compartilhados entre painel e OBS pelo servidor, sem depender do armazenamento local de cada navegador.

## Funcionamento

- A agenda pública do GE é consultada ao selecionar uma partida e reutilizada por até cinco minutos. Mandante, visitante e horário precisam corresponder sem ambiguidade; aliases conhecidos como Sport Recife/Sport são normalizados.
- O link informado manualmente também é validado contra a partida antes de publicar seus lances. Um link de outro jogo não altera placar, estatísticas nem narração.
- A página pública é lida pelo Edge em segundo plano, com JavaScript desativado, a cada 30 segundos. O canal de eventos do portal devolveu HTTP 403 no teste e não é consultado pela integração final. Nenhum parâmetro do widget TheSports é reutilizado.
- O HTML inicial serve de referência e não é narrado. Novos IDs e alterações de texto alimentam a fila; repetições são ignoradas. Itens retirados ou corrigidos deixam de permanecer na fila. Uma reconexão não despeja o histórico antigo na voz.
- Resumos automáticos, vídeos e publicações de redes sociais incorporadas são excluídos da leitura de lances. O texto editorial elegível permanece em português, com sua fonte indicada; não passa por reescrita do modelo local.
- Os lances não aguardam o intervalo de comentários. Se outra fala estiver em andamento, ficam na fila; gols interrompem análises e falas de menor prioridade. Acúmulos antigos são descartados para evitar uma narração muito atrasada.
- GE fornece o texto complementar. Placar e relógio continuam controlados pela fonte principal, evitando misturar contagens de fontes em momentos diferentes. Um gol do GE não faz o programa anunciar um placar antigo como se já estivesse atualizado.

## Configurar o áudio

1. No painel, selecione a partida e as vozes locais. Para OBS, use Kokoro Alex/Santa/Dora ou Piper Faber.
2. Escolha **Saída do áudio → Diretamente no OBS** e **Iniciar narração**.
3. Adicione uma fonte **Navegador** no OBS com `http://127.0.0.1:8787/audio`.
4. Marque **Controlar áudio via OBS**. Ajuste o volume da fonte no mixer.
5. O painel pode ser fechado. O servidor iniciado por `start.bat` precisa continuar aberto.

O endereço `/audio` é transparente. Para ver controles e mensagens, use `/audio?monitor=1`; o botão **Ativar áudio no OBS** também permite iniciar sem o painel de controle, com as preferências já salvas. Em um navegador comum, o áudio automático pode depender de um clique. No OBS, a opção **Interagir** permite acessar os controles dessa página de diagnóstico.

Adicione a mesma fonte existente às demais cenas. A permissão de áudio é exclusiva e renovada periodicamente; uma segunda página aguarda a primeira. Se a conexão cair, a voz é cancelada antes de outra página assumir. A retomada ignora os lances recebidos enquanto a saída estava sem conexão.

## Preferências

- **Sem comentários por intervalo:** os lances continuam ativos; comentários estatísticos periódicos ficam desligados. **Panorama agora** continua disponível.
- **Ler automaticamente os titulares:** opcional e inicialmente desligado. **Ler escalações agora** solicita a leitura mesmo com essa opção desmarcada e mesmo em partidas encerradas. A saída de narração precisa estar ativada e sem pausa. **Pular escalações** cancela o bloco atual e o restante da escalação.
- **Pedir like e inscrição:** ativável, com intervalo mínimo de 5, 10 ou 15 minutos. Só entra quando a fila está livre e não houve lance nos últimos 15 segundos. Eventos do jogo interrompem o lembrete.
- **Vou comentar no microfone:** pausa a voz automática. Não controla seu microfone do OBS.

## Limitações verificadas

A atualização GE nesta versão é por consulta da página, não por push em tempo real. O intervalo de 30 segundos se soma ao atraso editorial, carregamento e cache. A estrutura do site pode mudar; sem cobertura ou com bloqueio, o painel informa e mantém a fonte principal. O campo animado TheSports não está incluído.

O teste real confirmou a associação CRB x Sport e a leitura de 100 registros elegíveis na amostra mais recente, sem falar o histórico inicial. Testes locais com respostas controladas verificam novos lances, alterações, ausência de duplicações, duas páginas concorrentes, reprodução Web Audio e continuidade após fechar o painel. A configuração do mixer precisa ser feita no próprio OBS.

Texto editorial acessível publicamente não implica licença de retransmissão. Consulte as condições do GE para o uso pretendido, especialmente em transmissões monetizadas.

Referências: [partida testada](https://ge.globo.com/al/futebol/brasileirao-serie-b/jogo/15-09-2026/crb-sport.ghtml), [agenda GE](https://ge.globo.com/agenda/), [fonte de navegador no OBS](https://obsproject.com/kb/browser-source).
