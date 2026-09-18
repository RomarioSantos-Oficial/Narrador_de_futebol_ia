// Narrates changes in the supplied match data. Never infers passes or attacks.
const MatchEventsCompat = typeof MatchEvents !== 'undefined' ? MatchEvents : {
  key(e){
   const minute=String(e.minute ?? '').replace(/['′\s]/g,'');
   const text=String(e.text || '').replace(/\s+/g,' ').trim().toLowerCase();
   const players=Array.isArray(e.players)?e.players.map(p=>`${p.id||''}:${p.name||''}:${p.position||''}`).join('|'):'';
   const kind=e.kind || this.kind?.(e) || '';
   const stableId=e.id!=null&&!/^\d+$/.test(String(e.id))?String(e.id):null;
   return JSON.stringify([stableId ? `id:${stableId}` : null, minute, e.icon || '', kind, text, players, e.corrected ? 'corrected' : '']);
  },
  kind(e){
   const text=String(e.text||'');
   if(/gol.{0,35}(?:anulad|cancelad)|(?:anulad|cancelad).{0,25}gol/i.test(text)||e.kind==='cancelled')return 'event';
   if(e.corrected||e.kind==='correction')return 'correction';
   if(e.kind==='review'||/(?:VAR|vídeo).{0,50}(?:analisa|revis|verifica)|(?:revisão|checagem|análise).{0,40}(?:VAR|gol)|gol.{0,25}em análise/i.test(text))return 'review';
   if(e.kind==='goal'||(e.icon==='⚽'&&/^Gol\b/i.test(text)&&!/anulad|cancelad/i.test(text)))return 'goal';
   if(e.kind==='card'||['🟨','🟥'].includes(e.icon)||/^Cartão (amarelo|vermelho)/i.test(text))return 'card';
   if(e.kind==='substitution'||/substitui|^Sai\b.*\bentra\b/i.test(text))return 'substitution';
   return 'event';
  }
};

class MatchNarrator {
 constructor({synth=window.speechSynthesis,Utterance=window.SpeechSynthesisUtterance,onChange=()=>{},compose=null}={}) {
  Object.assign(this,{synth,Utterance,onChange,enabled:false,previewing:false,paused:false,queue:[],utterance:null,seen:new Set(),scoreTimer:null,status:'Narração desligada.',lastText:'',voice:null,rate:1,volume:1,style:'events',commentaryInterval:90,lastCommentAt:0,customComments:[],sponsorReads:[],playerFocus:'',customIndex:0,sponsorIndex:0});
  this.radio=new RadioCommentary();
  this.compose=compose;this.composing=null;this.finishAfterDrain=false;
  this.lineupQueue=[];this.lineupsSeen=new Set();
  this.analysisCycle=0;
 }
 configure({voice,commentaryVoice=null,rate=1,volume=1,commentaryRate=null,commentaryVolume=null,pronunciations={},stageScripts=true,style='events',commentaryInterval=90,delivery='natural',curiosities=false,announceLineups=false,engagement=false,engagementInterval=600,customComments=[],sponsorReads=[],commentLibrary=[],playerFocus=''}) {
  this.voice=voice;
  this.commentaryVoice=commentaryVoice||voice;this.curiosities=curiosities;
  this.customComments=Array.isArray(customComments)?customComments.filter(Boolean).slice(0,12):[];
  this.sponsorReads=Array.isArray(sponsorReads)?sponsorReads.filter(Boolean).slice(0,8):[];
  this.commentLibrary=Array.isArray(commentLibrary)?commentLibrary.filter(item=>item&&typeof item.text==='string'&&item.text.trim()).slice(0,50):[];
  this.playerFocus=String(playerFocus||'');
  if(this.announceLineups&&!announceLineups)this.lineupQueue=this.lineupQueue.filter(item=>item.manualLineup);
  this.announceLineups=announceLineups;
  this.rate=Math.min(1.4,Math.max(.7,Number(rate)||1));
  this.volume=Number.isFinite(Number(volume))?Math.min(1,Math.max(0,Number(volume))):1;
  this.commentaryRate=commentaryRate??this.rate;this.commentaryVolume=commentaryVolume??this.volume;
  this.pronunciations=pronunciations;this.stageScripts=stageScripts;
  const previousStyle=this.style;this.style=style==='radio'?'radio':'events';
  this.delivery=delivery==='dynamic'?'dynamic':'natural';
  this.commentaryInterval=[0,30,60,90,120].includes(Number(commentaryInterval))?Number(commentaryInterval):90;
  this.engagement=engagement;this.engagementInterval=[300,600,900].includes(Number(engagementInterval))?Number(engagementInterval):600;
  if(previousStyle==='radio'&&this.style!=='radio')this.interruptAnalysis({preserveLineups:true});
 }
 notify(status=this.status) {
  this.status=status;
  const describe=item=>item?{text:item.text.slice(0,900),kind:item.kind,role:item.kind==='analysis'?'Comentarista':'Narrador',label:item.lineup?'Escalação':item.script?'Roteiro':item.engagement?'Like e inscrição':item.replay?'Repetição':''}:null;
  this.onChange({enabled:this.enabled,active:this.enabled||this.previewing,paused:this.paused,status,lastText:this.lastText,lastSource:this.lastSource,
   current:describe(this.utterance?this.currentItem:this.composing?.item),queue:[...this.queue,...this.lineupQueue].slice(0,40).map(describe),can_repeat:!!this.lastEvent});
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
 skip(){
  if(this.paused)throw new Error('Retome a voz para pular a fala atual.');
  this.cancelComposition();
  if(this.utterance){this.utterance=null;this.synth.cancel();}
  this.currentItem=null;this.notify('Fala pulada.');this.pump();
 }
 repeat(s=this.currentState){
  if(!this.lastEvent)throw new Error('Nenhum lance disponível para repetir.');
  if(this.paused)throw new Error('Retome a voz para repetir o lance.');
  if(this.lastEvent.eventKey&&!this.events(s).some(e=>this.eventKey(e)===this.lastEvent.eventKey))throw new Error('Esse lance foi corrigido ou já saiu da lista da fonte.');
  if(!this.enabled&&s.phase==='post'){this.requireVoice();this.enabled=true;this.finishAfterDrain=true;}
  if(!this.enabled)throw new Error('Inicie a narração para repetir o lance.');
  this.interruptAnalysis();
  this.enqueue('Repetindo o último lance. '+this.lastEvent.text,'event',{...this.lastEvent,replay:true,text:'Repetindo o último lance. '+this.lastEvent.text,created:Date.now(),kind:'event'});
 }
 readStage(s=this.currentState){
  if(this.paused)throw new Error('Retome a voz para ler o roteiro.');
  if(!this.enabled&&s?.phase==='post'){this.requireVoice();this.enabled=true;this.finishAfterDrain=true;}
  if(!this.enabled)throw new Error('Inicie a narração para ler o roteiro.');
  if(this.queue.some(i=>i.script)||this.currentItem?.script&&this.utterance)throw new Error('O roteiro já está na fila.');
  this.currentState=s;
  for(const text of this.radio.stage(s))this.enqueue(text,'analysis',{script:true});
 }
 pronounce(text){
  const entries=Object.entries(this.pronunciations||{}).sort((a,b)=>b[0].length-a[0].length);
  if(!entries.length)return text;
  const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const lookup=new Map(entries.map(([key,value])=>[key.toLocaleLowerCase('pt-BR'),value]));
  const pattern=new RegExp('(?<![\\p{L}\\p{N}])(?:'+entries.map(([key])=>escape(key)).join('|')+')(?![\\p{L}\\p{N}])','giu');
  return text.replace(pattern,match=>lookup.get(match.toLocaleLowerCase('pt-BR'))||match);
 }
 interruptAnalysis({preserveLineups=false}={}){
  this.queue=this.queue.filter(item=>item.kind!=='analysis'||(preserveLineups&&item.lineup));
  if(this.composing?.item.kind==='analysis')this.cancelComposition();
  if(this.utterance&&this.utteranceKind==='analysis'&&!(preserveLineups&&this.currentItem?.lineup)){
   if(this.currentItem?.lineup&&(this.currentItem.manualLineup||this.announceLineups))this.lineupQueue.unshift({...this.currentItem,created:Date.now()});
   this.utterance=null;this.synth.cancel();
  }
 }
 allowGEJump() {
  if(!this.currentItem||this.currentItem.kind!=='analysis')return;
  const nextEvent=this.queue.findIndex(item=>item.editorial||item.source?.name?.includes('ge')||item.eventKey||['goal','card','substitution','review','cancelled','correction'].includes(item.kind));
  if(nextEvent<0)return;
  this.sortQueue();
  const item=this.queue.splice(nextEvent,1)[0];
  if(item)this.queue.unshift(item);
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
 eventKey(e) {return MatchEventsCompat.key(e);}
 eventMinuteValue(value){
  if(value==null||value===''||value==='—')return null;
  const text=String(value).replace(/['′\s]/g,'');
  const match=text.match(/^(\d+)(?:\+(\d+))?$/);
  if(!match)return null;
  return Number(match[1])+Number(match[2]||0);
 }
 recentInPlayEvent(event,s,minutes=8){
  if(s.phase!=='in'||!event||event.speak===false)return false;
  const eventMinute=this.eventMinuteValue(event.minute);
  const nowMinute=this.eventMinuteValue(s.minute ?? s.clock_display ?? s.updated_at ?? '');
  if(eventMinute==null)return false;
  if(nowMinute==null)return true;
  return eventMinute >= Math.max(0, nowMinute - minutes);
 }
 events(s){
  const ge=(s.ge?.events||[]).filter(Boolean);
  const primary=(s.events||[]).filter(Boolean);
  const preferred = s.ge?.ready && ge.length ? ge : [...primary,...ge];
  const byKey=new Map();
  for(const event of preferred){
   const key=this.eventKey(event);
   if(!byKey.has(key))byKey.set(key,event);
   else if(ge.some(item=>this.eventKey(item)===key)&&!primary.some(item=>this.eventKey(item)===key))byKey.set(key,event);
  }
  return [...byKey.values()].filter(Boolean);
 }
 feedKey(s){return s.ge?.ready?'ge:'+s.ge.session:'primary';}
 score(s) {return JSON.stringify([s.home?.score,s.away?.score]);}
 scoreboard(s) {return `${s.home.name}, ${s.home.score}. ${s.away.name}, ${s.away.score}.`;}
 baseline(s) {
  this.currentState=s;
  if(this.matchKey!==this.identity(s)){this.contextFacts=[];this.contextSeen=new Map();this.lineupsSeen=new Set();this.lastEvent=null;}
  this.matchKey=this.identity(s);this.lastScore=this.score(s);this.lastPhase=s.phase;this.lastStatus=s.status;
  const liveHistory=this.events(s).filter(e=>!this.recentInPlayEvent(e,s,8));
  this.seen=new Set(liveHistory.map(e=>this.eventKey(e)));this.lastFeed=this.feedKey(s);
  this.lastEngagementAt=Date.now();
  this.radio.reset(s);this.lastCommentAt=Date.now();
  this.goalCount=0;
 }
 start(s) {
  this.requireVoice();
  if(!s)throw new Error('Aguarde o painel carregar a partida.');
  this.stop();this.lineupsSeen=new Set();this.baseline(s);this.resync=false;this.enabled=true;
  if(this.stageScripts&&s.phase==='pre')this.readStage(s);
  else this.enqueue(this.style==='radio'?this.radio.snapshot(s):'Narração ativada. Aguardando novos lances.',this.style==='radio'?'analysis':'event',{panorama:true});
  this.update(s);
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
 queuePriority(item){
  if(item.urgent||item.scoreAnnouncement)return 200;
  if(item.editorial&&(item.eventKey||item.source?.name?.includes('ge')||item.source?.url?.includes('ge.globo.com')))return 180;
  if(['goal','card','substitution','review','cancelled','correction'].includes(item.kind))return 150;
  if(item.eventKey)return 100;
  if(item.kind==='event')return 90;
  if(item.lineup||item.script||item.panorama||item.engagement||item.kind==='analysis')return 10;
  return 50;
 }
 sortQueue(){
  this.queue.sort((a,b)=>{
   const aRealtime=Boolean(a.eventKey||a.editorial||['goal','card','substitution','review','cancelled','correction'].includes(a.kind));
   const bRealtime=Boolean(b.eventKey||b.editorial||['goal','card','substitution','review','cancelled','correction'].includes(b.kind));
   if(aRealtime!==bRealtime)return Number(bRealtime)-Number(aRealtime);
   return this.queuePriority(b)-this.queuePriority(a)||a.created-b.created;
  });
 }
 enqueue(text,kind='event',meta={}) {
  const parts=[];let rest=String(text);
  while(meta.editorial&&rest.length>900){const split=rest.lastIndexOf(' ',850);const at=split>400?split:850;parts.push(rest.slice(0,at));rest=rest.slice(at).trimStart();}
  parts.push(rest.slice(0,900));
  const eventKey=meta.eventKey?String(meta.eventKey):null;
  if(eventKey){this.queue=this.queue.filter(item=>!item.eventKey||item.eventKey!==eventKey||item.text===text);} 
  const items=parts.map(text=>({text,created:Date.now(),kind,...meta}));
  const front = kind==='goal' || meta.urgent || Boolean(meta.editorial) || ['cancelled','correction','review'].includes(kind);
  if(front)this.queue.unshift(...items);else this.queue.push(...items);
  this.sortQueue();
  // Discard an old backlog instead of speaking minutes behind the feed.
  while(this.queue.length>8){const drop=this.queue.findIndex(next=>this.queuePriority(next)<100);this.queue.splice(drop<0?this.queue.length-1:drop,1);}this.pump();this.notify();
 }
 pump() {
  if(this.utterance||this.composing||this.paused||(!this.enabled&&!this.previewing))return;
  this.queue=this.queue.filter(item=>Date.now()-item.created<45000);
  this.sortQueue();
  const item=this.queue.shift()||(!this.scoreTimer?this.lineupQueue.shift():null);
  if(!item){if(this.finishAfterDrain){this.stop('Partida encerrada. Fila e áudios liberados.');return;}this.previewing=false;this.notify(this.enabled?'Aguardando novos lances.':'Teste de voz concluído.');return;}
  if(this.compose&&this.enabled&&!this.previewing&&!item.lineup&&!item.script){
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
  const utterance=new this.Utterance(this.pronounce(item.text));
  const commentary=item.kind==='analysis'&&(!this.previewing||this.previewRole==='commentary');
  const voice=commentary?this.commentaryVoice||this.voice:this.voice;
  const pace=this.delivery==='dynamic'?({goal:1.08,card:1.02,analysis:.95}[item.kind]||1):1;
  Object.assign(utterance,{voice,lang:voice.lang,rate:Math.min(1.4,Math.max(.7,(commentary?this.commentaryRate:this.rate)*pace)),volume:commentary?this.commentaryVolume:this.volume,pitch:1,delivery:this.delivery||'natural',kind:item.kind});
  this.lastSource=item.source||null;
  this.utterance=utterance;this.utteranceKind=item.kind;this.lastText=item.text;this.notify(this.previewing?'Testando a voz…':item.kind==='analysis'?'Panorama da partida…':'Narrando…');
  utterance.onwaiting=status=>{if(this.utterance===utterance)this.notify(status);};
  utterance.onstart=()=>{if(this.utterance===utterance){if(item.eventKey&&!item.replay)this.lastEvent={...item};this.notify(this.previewing?'Testando a voz…':item.kind==='analysis'?'Panorama da partida…':'Narrando…');}};
  utterance.onend=()=>{if(this.utterance!==utterance)return;this.utterance=null;this.allowGEJump();this.pump();};
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
 featuredPlayer(s){
  const raw=this.playerFocus||'';
  if(!raw||!s?.lineups)return null;
  const [side, ...rest]=String(raw).split(':');
  const requested=rest.join(':').trim();
  const pool=[...(s.lineups?.[side]?.starters||[]),...(s.lineups?.[side]?.bench||[])];
  if(!pool.length)return null;
  if(requested){return pool.find(p=>p.name===requested)||pool.find(p=>p.name?.toLowerCase()===requested.toLowerCase())||null;}
  return pool[0]||null;
 }
 customComment(s){
  const library=this.commentLibrary||[];
  const focused=this.featuredPlayer(s);
  const picks=library.filter(entry=>{
   const team=String(entry.team||'').trim();
   const player=String(entry.player||'').trim();
   if(!team&&!player)return true;
   if(focused){
    const samePlayer=player && focused.name && focused.name.toLowerCase()===player.toLowerCase();
    const sameTeam=team && [s.home?.name,s.away?.name].some(name=>name && name.toLowerCase()===team.toLowerCase());
    if(samePlayer||sameTeam)return true;
   }
   return !player && !!team && [s.home?.name,s.away?.name].some(name=>name && name.toLowerCase()===team.toLowerCase());
  });
  if(picks.length){
   const pick=picks[Math.floor(Math.random()*picks.length)];
   if(pick && pick.text){return pick.text;}
  }
  if(!this.customComments.length)return '';
  const player=focused;
  const base=this.customComments[this.customIndex % this.customComments.length];
  this.customIndex=(this.customIndex+1)%Math.max(this.customComments.length,1);
  if(!player)return base;
  const role=this.position(player.position)||'no time';
  const number=player.number?` camisa ${player.number}`:'';
  return `Atenção para ${player.name}${number}, ${role}. ${base}`;
 }
 sponsorRead(s){
  if(!this.sponsorReads.length)return '';
  const message=this.sponsorReads[this.sponsorIndex % this.sponsorReads.length];
  this.sponsorIndex=(this.sponsorIndex+1)%Math.max(this.sponsorReads.length,1);
  return message;
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
  if(!s||!this.enabled||this.paused||this.resync||s.rehearsal?.disconnected||s.phase==='post'||this.utterance||this.composing||this.queue.length||this.scoreTimer)return;
  if(this.lineupQueue.length){this.pump();return;}
  if(this.engagement&&Date.now()-this.lastEngagementAt>=this.engagementInterval*1000&&Date.now()-this.lastCommentAt>=15000){
   this.lastEngagementAt=Date.now();this.lastCommentAt=Date.now();
   const phrases=['Está acompanhando com a gente? Deixe seu like e inscreva-se no canal para acompanhar as próximas transmissões.','Se está gostando da cobertura, fortaleça o canal com seu like e sua inscrição. Obrigado pela companhia!'];
   this.enqueue(phrases[(this.engagementCount||0)%phrases.length],'analysis',{engagement:true});this.engagementCount=(this.engagementCount||0)+1;return;
  }
  if(this.style!=='radio'||this.commentaryInterval===0||Date.now()-this.lastCommentAt<this.commentaryInterval*1000)return;
  const fresh=this.radio.fresh(s);
  const geAhead=this.queue.some(item=>item.editorial||item.source?.name?.includes('ge')||item.eventKey);
  if(geAhead) return;
  let comment='',source=null;
  const cycle = this.analysisCycle % 10;
  this.analysisCycle += 1;
  if((this.commentLibrary.length || this.customComments.length) && (cycle===0 || cycle===4)){
   comment=this.customComment(s);source={name:'comentário do usuário'};
  }
  if(!comment && this.sponsorReads.length && cycle===5){
   comment=this.sponsorRead(s);source={name:'patrocinador'};
  }
  if(this.curiosities && !comment){
   this.contextSeen??=new Map();
   const facts=this.contextCandidates(s).filter(f=>!this.contextSeen.has(f.id)||Date.now()-this.contextSeen.get(f.id)>=600000);
   if(facts.length){
    const playerFacts=facts.filter(f=>!!f.player_id);
    const clubFacts=facts.filter(f=>!f.player_id);
    const curiosityTurn=cycle % 5 === 0;
    const fact = curiosityTurn ? (playerFacts[0] || clubFacts[0]) : (fresh ? this.radio.next(s) : null);
    if(fact && typeof fact === 'object'){comment=fact.text;source=fact.source;this.contextSeen.set(fact.id,Date.now());}
   }
  }
  if(!comment&&fresh){comment=this.radio.next(s);}
  if(!comment&&this.style==='radio'&&(!s.stats||Object.keys(s.stats||{}).length===0)&&(cycle===0||cycle===5)){
   comment=this.radio.snapshot(s);source={name:'panorama'};
  }
  if(comment){this.lastCommentAt=Date.now();this.enqueue(comment,'analysis',{source,panorama:!!source&&source.name==='panorama'});}
 }
 eventOrder(event){
  const minute=String(event.minute ?? '').replace(/['′\s]/g,'');
  const match=minute.match(/^(\d+)(?:\+(\d+))?$/);
  const score=match ? Number(match[1]) + Number(match[2] || 0) : 0;
  return score * 1000 + (Number(event.revision||event.updated_at||0) || 0);
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
  return MatchEventsCompat.kind(event);
 }
 update(s) {
  this.currentState=s;
  if(!this.enabled)return;
  const previousSource=this.currentState?.source;
  if(this.paused){
   this.currentState=s;
   this.seen=new Set([...this.events(s).map(e=>this.eventKey(e)), ...this.seen]);
   this.queue=[];
   this.baseline(s);
   return;
  }
  if(this.resync){this.baseline(s);this.resync=false;this.notify('Conexão restabelecida. Aguardando novos lances.');return;}
  if(previousSource&&s.source&&previousSource!==s.source){
   this.queue=[];this.lastEvent=null;this.seen=new Set(this.events(s).map(e=>this.eventKey(e)));this.lastCommentAt=Date.now();
  }
  if(this.matchKey!==this.identity(s)) {
   this.clearPlayback();this.baseline(s);
   this.enqueue(this.style==='radio'?this.radio.snapshot(s):`Partida selecionada: ${s.home.name} e ${s.away.name}. A narração acompanhará os próximos lances.`,this.style==='radio'?'analysis':'event',{panorama:true});
   this.scheduleLineups(s);
   return;
  }
  const feedChanged=this.lastFeed!==this.feedKey(s);
  if(feedChanged){
   this.lastFeed=this.feedKey(s);const liveHistory=this.events(s).filter(e=>!this.recentInPlayEvent(e,s,8));
   this.seen=new Set(liveHistory.map(e=>this.eventKey(e)));
   this.queue=this.queue.filter(item=>!item.eventKey||Date.now()-item.created<45000);
   if(this.currentItem?.eventKey&&this.utterance){this.utterance=null;this.synth.cancel();}
  }
  const fresh=[];
  const available=new Set(this.events(s).map(e=>this.eventKey(e)));
  this.queue=this.queue.filter(item=>!item.editorial||available.has(item.eventKey));
  if(this.currentItem?.editorial&&this.utterance&&!available.has(this.currentItem.eventKey)){this.utterance=null;this.synth.cancel();}
  if(this.composing?.item.editorial&&!available.has(this.composing.item.eventKey))this.cancelComposition();
  if(this.lastEvent?.editorial&&!available.has(this.lastEvent.eventKey))this.lastEvent=null;
  const ordered=[...this.events(s)].sort((a,b)=>this.eventOrder(a)-this.eventOrder(b));
  for(const event of ordered) {
   if(event.speak===false)continue;
   const key=this.eventKey(event);
   if(this.seen.has(key))continue;
   if(this.lastEvent?.eventKey===key)continue;
   if(this.currentItem?.eventKey===key)continue;
   if(this.queue.some(item=>item.eventKey===key))continue;
   fresh.push(event);
  }
  // Respeitar a fala em andamento: se já existe um comentário ou lance sendo lido,
  // o próximo lance deve aguardar a conclusão da fala atual e entrar depois.
  while(this.seen.size>1000)this.seen.delete(this.seen.values().next().value);
  // GE can announce a goal before the primary score provider catches up.
  const goal=fresh.some(e=>e.icon==='⚽'&&!e.editorial),ended=s.phase==='post'&&this.lastPhase!=='post';
  const scoreChanged=this.score(s)!==this.lastScore;
  const previousScore=JSON.parse(this.lastScore||'[]');
  const scoreReduced=[s.home?.score,s.away?.score].some((value,i)=>value!=null&&previousScore[i]!=null&&Number(value)<Number(previousScore[i]));
  const correction=scoreReduced||fresh.some(e=>['cancelled','correction','review'].includes(this.eventKind(e)));
  if(correction){
   this.queue=this.queue.filter(item=>item.kind!=='goal'&&!item.scoreAnnouncement);
   if(this.composing&&(this.composing.item.kind==='goal'||this.composing.item.scoreAnnouncement))this.cancelComposition();
   this.lastEvent=null;clearTimeout(this.scoreTimer);this.scoreTimer=null;
  }
  if(fresh.some(e=>this.eventSpeech(e))||scoreChanged||ended){this.interruptAnalysis();this.lastCommentAt=Date.now();}
  for(const event of fresh) {
   if(ended&&/^Fim do (?:tempo|segundo)/i.test(event.text||''))continue;
   const key=this.eventKey(event);
   const sameQueued=this.queue.some(item=>item.eventKey===key);
   const sameCurrent=this.currentItem?.eventKey===key;
   const sameLast=this.lastEvent && this.eventKey(this.lastEvent)===key;
   if(sameQueued||sameCurrent||sameLast)continue;
   const text=this.eventSpeech(event);
   if(text){
    const kind=this.eventKind(event);
    this.seen.add(key);
    this.enqueue(text,kind,{eventKey:key,editorial:!!event.editorial,source:event.source,urgent:['cancelled','correction','review'].includes(kind)});
    if(kind==='goal')this.goalCount++;
   }
  }
  if(scoreChanged||goal||ended) {
   clearTimeout(this.scoreTimer);this.scoreTimer=null;
   const validScore=[s.home?.score,s.away?.score].every(n=>n!=null&&Number.isFinite(Number(n)));
   if(ended){this.lineupQueue=[];this.finishAfterDrain=true;if(this.stageScripts)this.readStage(s);else this.enqueue('Partida encerrada.'+(validScore?' Placar final. '+this.scoreboard(s):''));}
   else if(validScore&&(scoreChanged||goal)) {
    // Manual goals can arrive in two consecutive WebSocket messages: score, then event.
    this.scoreTimer=setTimeout(()=>{this.scoreTimer=null;if(this.enabled)this.enqueue((scoreReduced?'Correção do placar informada pela fonte. ':'Placar atualizado. ')+this.scoreboard(s),'event',{scoreAnnouncement:true,urgent:scoreReduced});},1000);
   }
  }
  if(s.status==='INTERVALO'&&this.lastStatus!=='INTERVALO'){if(this.stageScripts)this.readStage(s);else if(!fresh.some(e=>/intervalo/i.test(e.text||'')))this.enqueue('Intervalo da partida. '+this.scoreboard(s));}
  if(this.lastStatus==='INTERVALO'&&s.status!=='INTERVALO'&&s.phase==='in'&&!fresh.some(e=>/segundo tempo|começou o segundo|retornou/i.test(e.text||''))){
   this.enqueue('Segundo tempo em andamento. '+this.scoreboard(s),'event',{scoreAnnouncement:true,urgent:false});
  }
  this.scheduleLineups(s);this.tick(s);
  this.lastScore=this.score(s);this.lastPhase=s.phase;this.lastStatus=s.status;
 }
}
