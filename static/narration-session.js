// One session per page; the server grants audio to only one page at a time.
class NarrationSession {
 constructor({output,onChange=()=>{},onSettings=()=>{}}){
  this.output=output;this.onChange=onChange;this.onSettings=onSettings;
  this.client=crypto.randomUUID();this.deadline=0;this.started=false;this.ready=false;
  this.speech=new SpeechOutput();this.brain=new BrainOutput();
  this.speech.canSpeak=()=>this.ownsAudio();
  this.narrator=new MatchNarrator({synth:this.speech,Utterance:NarrationUtterance,
   compose:(item,state,signal)=>this.brain.compose(item,state,signal),
   onChange:status=>{const changed=JSON.stringify(this.status)!==JSON.stringify(status);this.status=status;onChange(status);
    if(changed&&this.ownsAudio()&&!this.statusTimer)this.statusTimer=setTimeout(()=>{this.statusTimer=null;this.renew();},150);}});
  this.timer=setInterval(async()=>{await this.renew();this.maintain().catch(e=>this.fail(e.message));this.refreshContext();},2000);
  this.tickTimer=setInterval(()=>this.narrator.tick(),1000);
  addEventListener('pagehide',()=>this.close());
 }
 async request(path,body){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Não foi possível atualizar a narração. Reinicie o programa.');
  if(path==='/api/narration/settings'&&result&&typeof result==='object'){
   this.settings={...(this.settings||{}),...result};
   if(this.state&&this.state.narration&&typeof this.state.narration==='object')this.state.narration={...(this.state.narration||{}),...result};
   this.onSettings?.(this.settings);
  }
  return result;
 }
 async load(){
  await Promise.all([this.speech.load(),this.brain.load()]);
  this.ready=true;
  const response=await fetch('/api/state');
  if(!response.ok)throw new Error('Servidor indisponível.');
  this.update(await response.json());
  return this;
 }
 voices(){return this.speech.getVoices().filter(v=>v.localService&&/^pt(?:-|_)/i.test(v.lang));}
 configure(){
  const c=this.settings,voices=this.voices();
  const voice=voices.find(v=>v.voiceURI===c.voice),commentaryVoice=voices.find(v=>v.voiceURI===c.commentaryVoice)||voice;
  if(this.output==='obs'&&(!this.speech.isLocalAI(voice)||!this.speech.isLocalAI(commentaryVoice)))throw new Error('Para o OBS, selecione Alex, Dora, Santa ou Faber nas duas vozes.');
  this.narrator.configure({...c,voice,commentaryVoice});this.brain.enabled=c.brain;
 }
 ownsAudio(){return performance.now()<this.deadline&&this.settings?.output===this.output;}
 lose(status='Saída de áudio aguardando conexão.'){
  clearTimeout(this.expiryTimer);this.deadline=0;this.started=false;
  this.narrator.stop(status);
 }
 fail(message){this.lose(message||'A conexão do áudio foi interrompida.');}
 disconnect(){this.connected=false;this.lose('Sem conexão com o servidor. Aguardando reconexão.');}
 update(state){
  this.connected=true;
  this.state=state;
  if(!state.narration){this.fail('Reinicie o programa pelo start.bat para carregar o canal de áudio.');return;}
  const before=this.settings;this.settings=state.narration;
  if(JSON.stringify(before)!==JSON.stringify(this.settings))this.onSettings(this.settings);
  if(!this.settings.enabled||this.settings.output!==this.output){
   if(!this.narrator.previewing&&(this.started||this.narrator.enabled))this.narrator.stop();
   this.started=false;
   if(this.settings.output!==this.output&&this.deadline)this.release();
  }
  if(this.ready){try{this.configure();}catch(e){if(this.settings.output===this.output)this.fail(e.message);}}
  if(this.narrator.enabled&&this.settings.paused!==this.narrator.paused)this.narrator.toggleHost(state);
  if(this.lastMatch&&this.lastMatch!==this.narrator.identity(state)&&!this.narrator.enabled)this.started=false;
  this.lastMatch=this.narrator.identity(state);
  if(state.rehearsal?.disconnected){if(!this.feedDisconnected){this.feedDisconnected=true;this.narrator.disconnect();}}
  else{this.feedDisconnected=false;this.narrator.update(state);}
  const command=state.narration_command;
  if(command&&this.command!==undefined&&this.command!==command.id){
   this.pendingCommand={...command,match:this.lastMatch,expires:Date.now()+15000};
  }
  this.command=command?.id||null;
  this.processCommand();
  if(this.ready)this.maintain().catch(e=>this.fail(e.message));
 }
 processCommand(){
  const command=this.pendingCommand;
  if(!command)return;
  if(!this.settings?.enabled||this.settings.output!==this.output||command.match!==this.lastMatch||Date.now()>command.expires){this.pendingCommand=null;return;}
  if(!this.ready||!this.started||!this.ownsAudio())return;
  this.pendingCommand=null;
  try{
   if(this.settings.paused)throw new Error('Retome a voz automática para ler as escalações ou solicitar comentários.');
   if(command.action==='lineups')this.narrator.readLineups(this.state);
   else if(command.action==='skip_lineups')this.narrator.skipLineups();
   else if(command.action==='panorama')this.narrator.panorama(this.state);
   else if(command.action==='skip')this.narrator.skip();
   else if(command.action==='repeat')this.narrator.repeat(this.state);
   else if(command.action==='stage')this.narrator.readStage(this.state);
  }catch(e){this.narrator.notify(e.message);}
 }
 async acquire(){
  const start=performance.now(),controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),2500);
  try{
   const response=await fetch('/api/narration/lease',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
    body:JSON.stringify({client:this.client,output:this.output,status:this.status?.status||'',text:this.status?.lastText||'',
     current:this.status?.current||null,queue:this.status?.queue||[],can_repeat:!!this.status?.can_repeat})});
   if(!response.ok)throw new Error('Não foi possível reservar a saída de áudio.');
   const body=await response.json();
   if(!body.granted){this.lose('Outra página está usando o canal de áudio.');return false;}
   this.deadline=start+body.ttl*1000-750;
   clearTimeout(this.expiryTimer);this.expiryTimer=setTimeout(()=>this.lose('Conexão de áudio perdida. Aguardando reconexão.'),Math.max(0,this.deadline-performance.now()));
   return this.ownsAudio();
  }finally{clearTimeout(timer);}
 }
 async maintain(){
  if(!this.ready||!this.connected||this.maintaining||!this.settings||!this.state)return;
  if(this.settings.output!==this.output||(!this.settings.enabled&&!this.narrator.previewing&&!this.previewRequested)){if(this.deadline)await this.release();return;}
  if(this.ownsAudio()&&this.started){this.processCommand();return;}
  this.maintaining=true;
  try{
   if(!this.ownsAudio()&&!await this.acquire())return;
   if(this.settings.enabled&&!this.started){
    this.configure();
    await this.unlock(this.narrator.voice);
    if(!this.ownsAudio()||!this.settings.enabled)return;
    this.narrator.start(this.state);this.started=true;
    if(this.settings.paused)this.narrator.toggleHost(this.state);
    this.refreshContext();
    if(this.brain.enabled&&this.brain.status?.installed&&!this.brain.status?.ready&&!this.brainPreparing){
     this.brainPreparing=true;this.brain.prepare().catch(()=>{}).finally(()=>{this.brainPreparing=false;});
    }
   }
   this.processCommand();
  }finally{this.maintaining=false;}
 }
 async renew(){
  if(this.renewing||!this.deadline)return;
  this.renewing=true;try{await this.acquire();}catch(e){this.fail('Sem conexão com o servidor de áudio.');}finally{this.renewing=false;}
 }
 async save(patch){return this.request('/api/narration/settings',patch);}
 async unlock(voice){
  let timer;try{await Promise.race([this.speech.unlock(voice),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Ative o áudio pelo botão da página, usando Interagir no OBS se necessário.')),2000);})]);}finally{clearTimeout(timer);}
 }
 async commandAction(action){return this.request('/api/narration/command',{action});}
 async preview(commentary=false){
  if(this.settings.output!==this.output)throw new Error('Escolha a saída Painel para testar as vozes aqui.');
  this.previewRequested=true;
  try{this.configure();if(!await this.acquire())return;
   await this.unlock(commentary?this.narrator.commentaryVoice:this.narrator.voice);
   if(this.ownsAudio())this.narrator.preview({commentary});
  }finally{this.previewRequested=false;}
 }
 async refreshContext(){
  if(!this.settings?.curiosities||!this.state||this.state.rehearsal?.active||!this.narrator.enabled)return;
  const key=this.narrator.identity(this.state)+JSON.stringify(this.state.lineups||{});
  if(key===this.contextKey&&Date.now()<this.contextNext)return;
  this.contextKey=key;this.contextNext=Date.now()+300000;
  const state=this.state;
  try{const r=await fetch('/api/narration/context');if(r.ok){const data=await r.json();if(key===this.contextKey&&JSON.stringify(data.teams)===JSON.stringify([state.home.name,state.away.name]))this.narrator.setContext(state,data.facts||[]);}}catch{}
 }
 async release(){
  this.lose(this.settings?.output==='obs'?'Áudio direcionado ao OBS.':'Narração desligada.');
  try{await this.request('/api/narration/release',{client:this.client,output:this.output});}catch{}
 }
 close(){
  clearInterval(this.timer);clearInterval(this.tickTimer);clearTimeout(this.statusTimer);this.lose();
  navigator.sendBeacon('/api/narration/release',new Blob([JSON.stringify({client:this.client,output:this.output})],{type:'application/json'}));
 }
}
