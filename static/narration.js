// Narrates changes in the supplied match data. Never infers passes or attacks.
class MatchNarrator {
 constructor({synth=window.speechSynthesis,Utterance=window.SpeechSynthesisUtterance,onChange=()=>{},compose=null}={}) {
  Object.assign(this,{synth,Utterance,onChange,enabled:false,previewing:false,paused:false,queue:[],utterance:null,seen:new Set(),scoreTimer:null,status:'Narração desligada.',lastText:'',voice:null,rate:1,volume:1,style:'events',commentaryInterval:90,lastCommentAt:0});
  this.radio=new RadioCommentary();
  this.compose=compose;this.composing=null;this.finishAfterDrain=false;
  this.lineupQueue=[];this.lineupsSeen=new Set();
 }
 configure({voice,commentaryVoice=null,rate=1,volume=1,style='events',commentaryInterval=90,delivery='natural',curiosities=false,announceLineups=false,engagement=false,engagementInterval=600}) {
  this.voice=voice;
  this.commentaryVoice=commentaryVoice||voice;this.curiosities=curiosities;
  if(this.announceLineups&&!announceLineups)this.lineupQueue=this.lineupQueue.filter(item=>item.manualLineup);
  this.announceLineups=announceLineups;
  this.rate=Math.min(1.4,Math.max(.7,Number(rate)||1));
  this.volume=Number.isFinite(Number(volume))?Math.min(1,Math.max(0,Number(volume))):1;
  const previousStyle=this.style;this.style=style==='radio'?'radio':'events';
  this.delivery=delivery==='dynamic'?'dynamic':'natural';
  this.commentaryInterval=[0,30,60,90,120].includes(Number(commentaryInterval))?Number(commentaryInterval):90;
  this.engagement=engagement;this.engagementInterval=[300,600,900].includes(Number(engagementInterval))?Number(engagementInterval):600;
  if(previousStyle==='radio'&&this.style!=='radio')this.interruptAnalysis({preserveLineups:true});
 }
 notify(status=this.status) {
  this.status=status;
  this.onChange({enabled:this.enabled,active:this.enabled||this.previewing,paused:this.paused,status,lastText:this.lastText,lastSource:this.lastSource});
 }
 clearPlayback() {
  clearTimeout(this.scoreTimer);this.scoreTimer=null;this.queue=[];
  this.lineupQueue=[];
  this.cancelComposition();this.finishAfterDrain=false;
  const speaking=this.utterance;this.utterance=null;
  if(speaking)this.synth.cancel();
 }
 cancelComposition(){const pending=this.composing;this.composing=null;pending?.controller.abort();}
 stop(status='Narração desligada.') {
  this.enabled=false;this.previewing=false;this.paused=false;this.clearPlayback();this.notify(status);
 }
 toggleHost(s){
  if(!this.enabled)return;
  this.clearPlayback();this.paused=!this.paused;
  if(this.paused)this.notify('Voz pausada. Você pode comentar pelo microfone no OBS.');
  else{this.baseline(s);this.notify('Narração retomada. Aguardando novos lances.');}
 }
 panorama(s){
  if(!this.enabled||this.paused)throw new Error('Inicie a narração e deixe a voz ativa para ouvir o panorama.');
  if(!s)throw new Error('Aguarde os dados da partida.');
  if(this.utterance||this.composing||this.queue.length)throw new Error('Aguarde a fala atual terminar para ouvir o panorama.');
  this.currentState=s;this.lastCommentAt=Date.now();this.enqueue(this.radio.snapshot(s),'analysis',{panorama:true});
 }
 interruptAnalysis({preserveLineups=false}={}){
  this.queue=this.queue.filter(item=>item.kind!=='analysis'||(preserveLineups&&item.lineup));
  if(this.composing?.item.kind==='analysis')this.cancelComposition();
  if(this.utterance&&this.utteranceKind==='analysis'&&!(preserveLineups&&this.currentItem?.lineup)){
   if(this.currentItem?.lineup&&(this.currentItem.manualLineup||this.announceLineups))this.lineupQueue.unshift({...this.currentItem,created:Date.now()});
   this.utterance=null;this.synth.cancel();
  }
 }
 disconnect() {
  if(!this.enabled)return;
  this.clearPlayback();this.resync=true;this.notify('Sem conexão com o servidor. Aguardando reconexão.');
 }
 requireVoice() {
  if(!this.synth||!this.Utterance)throw new Error('Este navegador não oferece leitura por voz. Abra o painel no Microsoft Edge.');
  if(!this.voice?.localService||!/^pt(?:-|_)/i.test(this.voice.lang))throw new Error('Selecione uma voz local em português.');
 }
 identity(s) {return JSON.stringify([s.competition,s.home?.name,s.away?.name,s.kickoff||'',s.source||'']);}
 eventKey(e) {return e.id!=null?String(e.id)+(e.revision?':'+e.revision:''):JSON.stringify([e.minute,e.icon,e.text]);}
 events(s){return s.ge?.ready?s.ge.events||[]:s.events||[];}
 feedKey(s){return s.ge?.ready?'ge:'+s.ge.session:'primary';}
 score(s) {return JSON.stringify([s.home?.score,s.away?.score]);}
 scoreboard(s) {return `${s.home.name}, ${s.home.score}. ${s.away.name}, ${s.away.score}.`;}
 baseline(s) {
  this.currentState=s;
  if(this.matchKey!==this.identity(s)){this.contextFacts=[];this.contextSeen=new Map();this.lineupsSeen=new Set();}
  this.matchKey=this.identity(s);this.lastScore=this.score(s);this.lastPhase=s.phase;this.lastStatus=s.status;
  this.seen=new Set(this.events(s).map(e=>this.eventKey(e)));this.lastFeed=this.feedKey(s);
  this.lastEngagementAt=Date.now();
  this.radio.reset(s);this.lastCommentAt=Date.now();
  this.goalCount=0;
 }
 start(s) {
  this.requireVoice();
  if(!s)throw new Error('Aguarde o painel carregar a partida.');
  this.stop();this.lineupsSeen=new Set();this.baseline(s);this.resync=false;this.enabled=true;
  this.enqueue(this.style==='radio'?this.radio.snapshot(s):'Narração ativada. Aguardando novos lances.',this.style==='radio'?'analysis':'event',{panorama:true});
  this.scheduleLineups(s);
 }
 preview({commentary=false}={}) {
  this.requireVoice();this.stop();this.previewing=true;
  this.previewRole=commentary?'commentary':'narrator';
  if(commentary){this.enqueue('Este é um teste da voz de comentários. Vou trazer os números da partida e informações dos clubes.','analysis');return;}
  if(this.delivery==='dynamic'){
   this.enqueue('Este é um teste da voz, no ritmo dos comentários da partida.','analysis');
   this.enqueue('Agora, um exemplo de gol: é gol! Bola na rede!','goal');
  }else this.enqueue('Esta é a voz da sua transmissão. Gols, cartões e novos lances serão anunciados em português.');
 }
 enqueue(text,kind='event',meta={}) {
  const parts=[];let rest=String(text);
  while(meta.editorial&&rest.length>900){const split=rest.lastIndexOf(' ',850);const at=split>400?split:850;parts.push(rest.slice(0,at));rest=rest.slice(at).trimStart();}
  parts.push(rest.slice(0,900));
  const items=parts.map(text=>({text,created:Date.now(),kind,...meta}));
  if(kind==='goal'||meta.urgent)this.queue.unshift(...items);else this.queue.push(...items);
  // Discard an old backlog instead of speaking minutes behind the feed.
  while(this.queue.length>8){const drop=this.queue.findIndex(next=>next.kind!=='goal'&&!next.urgent);this.queue.splice(drop<0?this.queue.length-1:drop,1);}this.pump();
 }
 pump() {
  if(this.utterance||this.composing||this.paused||(!this.enabled&&!this.previewing))return;
  this.queue=this.queue.filter(item=>Date.now()-item.created<45000);
  const item=this.queue.shift()||(!this.scoreTimer?this.lineupQueue.shift():null);
  if(!item){if(this.finishAfterDrain){this.stop('Partida encerrada. Fila e áudios liberados.');return;}this.previewing=false;this.notify(this.enabled?'Aguardando novos lances.':'Teste de voz concluído.');return;}
  if(this.compose&&this.enabled&&!this.previewing&&!item.lineup){
   const pending={item,controller:new AbortController()};this.composing=pending;
   this.notify('Preparando comentário…');
   Promise.resolve().then(()=>this.compose(item,this.currentState,pending.controller.signal)).then(text=>{
    if(this.composing!==pending)return;
    this.composing=null;
    if(Date.now()-item.created>=45000){this.pump();return;}
    this.speakItem({...item,text:typeof text==='string'&&text.trim()?text.slice(0,900):item.text});
   }).catch(()=>{if(this.composing!==pending)return;this.composing=null;this.speakItem(item);});
   return;
  }
  this.speakItem(item);
 }
 speakItem(item){
  this.currentItem=item;
  const utterance=new this.Utterance(item.text);
  const voice=item.kind==='analysis'&&(!this.previewing||this.previewRole==='commentary')?this.commentaryVoice||this.voice:this.voice;
  const pace=this.delivery==='dynamic'?({goal:1.08,card:1.02,analysis:.95}[item.kind]||1):1;
  Object.assign(utterance,{voice,lang:voice.lang,rate:Math.min(1.4,Math.max(.7,this.rate*pace)),volume:this.volume,pitch:1,delivery:this.delivery||'natural',kind:item.kind});
  this.lastSource=item.source||null;
  this.utterance=utterance;this.utteranceKind=item.kind;this.lastText=item.text;this.notify(this.previewing?'Testando a voz…':item.kind==='analysis'?'Panorama da partida…':'Narrando…');
  utterance.onwaiting=status=>{if(this.utterance===utterance)this.notify(status);};
  utterance.onstart=()=>{if(this.utterance===utterance)this.notify(this.previewing?'Testando a voz…':item.kind==='analysis'?'Panorama da partida…':'Narrando…');};
  utterance.onend=()=>{if(this.utterance!==utterance)return;this.utterance=null;this.pump();};
  utterance.onerror=event=>{if(this.utterance!==utterance)return;this.stop(event.error==='not-allowed'?'O navegador bloqueou a fala. Clique em Testar voz e tente iniciar novamente.':event.message||'Não foi possível reproduzir a voz. Selecione outra voz e clique em Testar voz.');};
  try{this.synth.speak(utterance);}catch{this.stop('Não foi possível reproduzir a voz. Clique em Testar voz para tentar novamente.');}
 }
 setContext(s,facts){
  if(this.identity(this.currentState||s)!==this.identity(s))return;
  this.contextFacts=facts;this.contextSeen??=new Map();
 }
 contextCandidates(s){
  const priority=fact=>{
   if(!fact.player_id)return 0;
   const lineup=s.lineups?.[fact.side]||{},starters=lineup.starters||[],bench=lineup.bench||[];
   const player=[...starters,...bench].find(p=>String(p.id)===fact.player_id&&p.name===fact.player_name);
   if(!player||player.subbed_out||player.red)return -1;
   const involved=(s.events||[]).some(e=>e.icon==='⚽'&&((e.players||[]).some(p=>String(p.id)===fact.player_id)||e.text?.includes(fact.player_name)));
   return involved?5:player.subbed_in?4:player.captain?3:starters.includes(player)?2:1;
  };
  const result=[...(this.contextFacts||[])].filter(f=>priority(f)>=0).sort((a,b)=>priority(b)-priority(a));
  for(const side of ['home','away']){
   const r=s.standings?.[side],name=s[side]?.name;
   if(r&&[r.rank,r.points,r.wins,r.draws,r.losses].every(v=>v!=null&&Number.isFinite(Number(v)))){
    const text=`Na classificação informada de ${s.competition}, ${name} está na posição ${r.rank}, com ${r.points} pontos. São ${r.wins} vitórias, ${r.draws} empates e ${r.losses} derrotas no campeonato. A tabela pode não incluir o jogo em andamento.`;
    result.push({id:side+':table:'+JSON.stringify(r),text,source:{name:s.league_table?.source||s.source}});
   }
  }
  return result;
 }
 position(value){
  const positions={GK:'goleiro',G:'goleiro',D:'defensor',DF:'defensor',DC:'zagueiro',CB:'zagueiro',CD:'zagueiro',CDL:'zagueiro pela esquerda',CDR:'zagueiro pela direita',LB:'lateral esquerdo',RB:'lateral direito',DL:'lateral esquerdo',DR:'lateral direito',LWB:'ala esquerdo',RWB:'ala direito',M:'meio-campista',MF:'meio-campista',CM:'meio-campista central',MC:'meio-campista central',DMC:'volante',DM:'volante',DMR:'volante pela direita',DML:'volante pela esquerda',AMC:'meia ofensivo',AM:'meia ofensivo',AMR:'meia pela direita',AML:'meia pela esquerda',LM:'meia pela esquerda',RM:'meia pela direita',F:'atacante',FW:'atacante',ST:'atacante',CF:'centroavante',LW:'ponta esquerda',RW:'ponta direita',SUB:'reserva',Goalkeeper:'goleiro',Defender:'defensor',Midfielder:'meio-campista',Attacker:'atacante'};
  return positions[value]||positions[String(value||'').replace(/[-_]/g,'')]||'posição não informada';
 }
 scheduleLineups(s,force=false){
  if(!this.enabled||this.paused||(s.phase==='post'&&!force)||(!this.announceLineups&&!force))return;
  for(const side of ['home','away']){
   const group=s.lineups?.[side],players=group?.starters||[];
   if(!players.length||(!force&&this.lineupsSeen.has(side)))continue;
   // Wait for the complete eleven before automatically announcing the initial lineup.
   if(!force&&players.length!==11)continue;
   this.lineupsSeen.add(side);
   for(let index=0;index<players.length;index+=3){
    const intro=index===0?`Escalação inicial informada do ${s[side].name}. `:`Seguindo a escalação do ${s[side].name}. `;
    const text=intro+players.slice(index,index+3).map(p=>`${p.name}${p.number?`, camisa ${p.number}`:''}, ${this.position(p.position)}${p.captain?', capitão':''}`).join('. ')+'.';
    this.lineupQueue.push({text,kind:'analysis',lineup:true,manualLineup:force,created:Date.now()});
   }
  }
  if(this.lineupQueue.length)this.pump();
 }
 readLineups(s){
  if(this.paused)throw new Error('Retome a voz automática para ler as escalações.');
  if(!this.enabled&&s?.phase!=='post')throw new Error('Inicie a narração para ler as escalações.');
  if(!['home','away'].some(side=>s?.lineups?.[side]?.starters?.length))throw new Error('A fonte ainda não forneceu os titulares.');
  if(!this.enabled){this.requireVoice();this.clearPlayback();this.baseline(s);this.resync=false;this.enabled=true;this.finishAfterDrain=true;}
  this.currentState=s;this.interruptAnalysis();
  this.lineupQueue=[];this.scheduleLineups(s,true);this.pump();
 }
 skipLineups(){
  this.lineupsSeen.add('home');this.lineupsSeen.add('away');
  this.lineupQueue=[];this.queue=this.queue.filter(item=>!item.lineup);
  if(this.currentItem?.lineup&&this.utterance){this.utterance=null;this.synth.cancel();}
  this.notify('Leitura das escalações pulada.');this.pump();
 }
 tick(s=this.currentState){
  if(!s||!this.enabled||this.paused||this.resync||s.phase==='post'||this.utterance||this.composing||this.queue.length||this.scoreTimer)return;
  if(this.lineupQueue.length){this.pump();return;}
  if(this.engagement&&Date.now()-this.lastEngagementAt>=this.engagementInterval*1000&&Date.now()-this.lastCommentAt>=15000){
   this.lastEngagementAt=Date.now();this.lastCommentAt=Date.now();
   const phrases=['Está acompanhando com a gente? Deixe seu like e inscreva-se no canal para acompanhar as próximas transmissões.','Se está gostando da cobertura, fortaleça o canal com seu like e sua inscrição. Obrigado pela companhia!'];
   this.enqueue(phrases[(this.engagementCount||0)%phrases.length],'analysis',{engagement:true});this.engagementCount=(this.engagementCount||0)+1;return;
  }
  if(this.style!=='radio'||this.commentaryInterval===0||Date.now()-this.lastCommentAt<this.commentaryInterval*1000)return;
  const fresh=this.radio.fresh(s);
  let comment=fresh?this.radio.next(s):'',source=null;
  if(!comment&&this.curiosities){
   this.contextSeen??=new Map();
   const fact=this.contextCandidates(s).find(f=>!this.contextSeen.has(f.id)||Date.now()-this.contextSeen.get(f.id)>=600000);
   if(fact){comment=fact.text;source=fact.source;this.contextSeen.set(fact.id,Date.now());}
  }
  if(comment){this.lastCommentAt=Date.now();this.enqueue(comment,'analysis',{source});}
 }
 eventSpeech(event) {
  if(!event.text||event.text==='Lance registrado na partida')return '';
  const minute=String(event.minute??'').replace(/['′\s]/g,'').match(/^(\d+)(?:\+(\d+))?$/);
  const when=minute?`Aos ${minute[1]} minutos${minute[2]?`, mais ${minute[2]} de acréscimo`:''}. `:'';
  let text=event.text.replace(/\s*·\s*/g,'. ');
  if(event.editorial)return (event.corrected?'Atualização do lance. ':'')+when+(event.period?event.period.replace('1T','Primeiro tempo. ').replace('2T','Segundo tempo. '):'')+text;
  if(this.style==='radio'||this.delivery==='dynamic'){
   if(this.eventKind(event)==='goal')text=text.replace(/^Gol(?:\s+contra|\s+de cabeça)?\.?\s*/i,match=>/contra/i.test(match)?'Gol contra! ':/cabeça/i.test(match)?'Gol de cabeça! ':this.delivery==='dynamic'?['É gol! ','Bola na rede! ','Saiu o gol! '][(this.goalCount||0)%3]:'É gol! ');
   else if(/^Cartão (amarelo|vermelho)\./i.test(text))text=text.replace(/^Cartão (amarelo|vermelho)\.\s*/i,'Cartão $1 para ');
  }
  return this.delivery==='dynamic'&&this.eventKind(event)==='goal'?text.replace(/[.!?]\s*$/,'')+'. '+when.trim():when+text;
 }
 eventKind(event){
  if(event.editorial)return ['goal','card','event'].includes(event.kind)?event.kind:'event';
  if(event.icon==='⚽'&&/^Gol\b/i.test(event.text||'')&&!/anulad|cancelad/i.test(event.text))return 'goal';
  return /^Cartão (amarelo|vermelho)/i.test(event.text||'')?'card':'event';
 }
 update(s) {
  this.currentState=s;
  if(!this.enabled)return;
  if(this.paused){this.baseline(s);return;}
  if(this.resync){this.baseline(s);this.resync=false;this.notify('Conexão restabelecida. Aguardando novos lances.');return;}
  if(this.matchKey!==this.identity(s)) {
   this.clearPlayback();this.baseline(s);
   this.enqueue(this.style==='radio'?this.radio.snapshot(s):`Partida selecionada: ${s.home.name} e ${s.away.name}. A narração acompanhará os próximos lances.`,this.style==='radio'?'analysis':'event',{panorama:true});
   this.scheduleLineups(s);
   return;
  }
  const feedChanged=this.lastFeed!==this.feedKey(s);
  if(feedChanged){
   this.lastFeed=this.feedKey(s);this.seen=new Set(this.events(s).map(e=>this.eventKey(e)));
   this.queue=this.queue.filter(item=>!item.eventKey);
   if(this.currentItem?.eventKey&&this.utterance){this.utterance=null;this.synth.cancel();}
  }
  const fresh=[];
  const available=new Set(this.events(s).map(e=>this.eventKey(e)));
  this.queue=this.queue.filter(item=>!item.editorial||available.has(item.eventKey));
  if(this.currentItem?.editorial&&this.utterance&&!available.has(this.currentItem.eventKey)){this.utterance=null;this.synth.cancel();}
  for(const event of this.events(s)) {
   const key=this.eventKey(event);
   if(!this.seen.has(key)){this.seen.add(key);if(event.speak!==false)fresh.push(event);}
  }
  while(this.seen.size>1000)this.seen.delete(this.seen.values().next().value);
  // GE can announce a goal before the primary score provider catches up.
  const goal=fresh.some(e=>e.icon==='⚽'&&!e.editorial),ended=s.phase==='post'&&this.lastPhase!=='post';
  const scoreChanged=this.score(s)!==this.lastScore;
  if(fresh.some(e=>this.eventSpeech(e))||scoreChanged||ended){this.interruptAnalysis();this.lastCommentAt=Date.now();}
  if((fresh.some(e=>this.eventKind(e)==='goal')||scoreChanged)&&this.utterance&&this.utteranceKind!=='goal'){this.utterance=null;this.synth.cancel();}
  for(const event of fresh.reverse().sort((a,b)=>Number(this.eventKind(b)==='goal')-Number(this.eventKind(a)==='goal'))) {
   if(ended&&/^Fim do (?:tempo|segundo)/i.test(event.text||''))continue;
   const text=this.eventSpeech(event);
   if(text){const kind=this.eventKind(event);this.enqueue(text,kind,{eventKey:this.eventKey(event),editorial:!!event.editorial,source:event.source});if(kind==='goal')this.goalCount++;}
  }
  if(scoreChanged||goal||ended) {
   clearTimeout(this.scoreTimer);this.scoreTimer=null;
   const validScore=[s.home?.score,s.away?.score].every(n=>n!=null&&Number.isFinite(Number(n)));
   if(ended){this.lineupQueue=[];this.finishAfterDrain=true;this.enqueue('Partida encerrada.'+(validScore?' Placar final. '+this.scoreboard(s):''));}
   else if(validScore&&(scoreChanged||goal)) {
    // Manual goals can arrive in two consecutive WebSocket messages: score, then event.
    this.scoreTimer=setTimeout(()=>{this.scoreTimer=null;if(this.enabled)this.enqueue('Placar atualizado. '+this.scoreboard(s));},1000);
   }
  }
  if(s.status==='INTERVALO'&&this.lastStatus!=='INTERVALO'&&!fresh.some(e=>/intervalo/i.test(e.text||'')))this.enqueue('Intervalo da partida. '+this.scoreboard(s));
  this.scheduleLineups(s);this.tick(s);
  this.lastScore=this.score(s);this.lastPhase=s.phase;this.lastStatus=s.status;
 }
}
