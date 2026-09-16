// One output for native voices and local neural speech. Cancellation also invalidates pending HTTP audio.
class NarrationUtterance {constructor(text){this.text=text;}}
class SpeechOutput {
 constructor({native=window.speechSynthesis,fetcher=window.fetch.bind(window)}={}){
  this.native=native;this.fetcher=fetcher;this.localVoices=[];this.token=0;this.current=null;
 }
 async load(){
  try{
   const response=await this.fetcher('/api/voice/status');
   if(!response.ok)throw new Error();
   const status=await response.json();
   this.localVoices=(status.voices||(status.available?[status]:[])).map(voice=>({...voice,localService:true}));
   this.message=status.message||'Vozes locais disponíveis.';
   if(!status.apiVersion||status.apiVersion<2)this.message+=' Reinicie o programa pelo start.bat para carregar as novas vozes Alex, Santa e Dora.';
  }catch{this.message='Reinicie o programa pelo start.bat para verificar a voz de IA local.';}
 }
 getVoices(){return [...this.localVoices,...(this.native?.getVoices()||[])];}
 isLocalAI(voice){return ['piper','kokoro'].includes(voice?.engine);}
 async unlock(voice){
  if(!this.isLocalAI(voice))return;
  if(!this.context)this.context=new AudioContext();
  if(this.context.state==='suspended')await this.context.resume();
 }
 cancel(){
  this.token++;
  this.controller?.abort();this.controller=null;
  if(this.source){this.source.onended=null;this.source.stop();this.source.disconnect();this.source.buffer=null;this.source=null;}
  this.gain?.disconnect();this.gain=null;
  if(this.nativeActive)this.native?.cancel();
  this.nativeActive=false;this.current=null;
 }
 speak(utterance){
  if(this.canSpeak&&!this.canSpeak()){utterance.onerror?.({message:'Outra saída está responsável pelo áudio.'});return;}
  this.cancel();this.current=utterance;
  const token=this.token;
  if(this.isLocalAI(utterance.voice)){this.speakLocal(utterance,token);return;}
  const native=new SpeechSynthesisUtterance(utterance.text);
  for(const key of ['voice','lang','rate','volume','pitch'])native[key]=utterance[key];
  native.onend=()=>{if(token===this.token){this.nativeActive=false;this.current=null;utterance.onend?.();}};
  native.onerror=e=>{if(token===this.token){this.nativeActive=false;this.current=null;utterance.onerror?.(e);}};
  this.nativeActive=true;this.native.speak(native);
 }
 async speakLocal(utterance,token){
  const controller=new AbortController();this.controller=controller;
  const deadline=setTimeout(()=>controller.abort(),45000);
  try{
   if(!this.context||this.context.state!=='running')throw Object.assign(new Error(),{speechCode:'not-allowed'});
   let response;
   const payload={text:utterance.text,rate:utterance.rate};
   if(utterance.voice.apiVersion>=2)Object.assign(payload,{voice:utterance.voice.voiceURI,delivery:utterance.delivery||'natural',kind:utterance.kind||'event'});
   utterance.onwaiting?.('Gerando a voz…');
   // New servers wait for the previous inference. Back off for older servers or an overloaded queue.
   for(let attempt=0;attempt<6;attempt++){
    if(token!==this.token)return;
    if(controller.signal.aborted)throw new DOMException('Voice timeout','AbortError');
    response=await this.fetcher('/api/voice/synthesize',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify(payload)});
    if(token!==this.token)return;
    if(![409,429].includes(response.status)||attempt===5)break;
    utterance.onwaiting?.('Aguardando a geração anterior terminar…');
    const retryAfter=Number(response.headers?.get('Retry-After'));
    const delay=Number.isFinite(retryAfter)&&retryAfter>0?Math.min(3000,retryAfter*1000):Math.min(2000,750*2**attempt);
    await new Promise(resolve=>{
     const done=()=>{clearTimeout(timer);controller.signal.removeEventListener('abort',done);resolve();};
     const timer=setTimeout(done,delay);controller.signal.addEventListener('abort',done,{once:true});
     if(controller.signal.aborted)done();
    });
   }
   if(token!==this.token)return;
   if(!response.ok){
    const body=await response.json().catch(()=>({}));
    throw new Error(typeof body.detail==='string'?body.detail:'Não foi possível gerar a voz de IA. Teste novamente.');
   }
   const buffer=await this.context.decodeAudioData(await response.arrayBuffer());
   if(token!==this.token)return;
   if(this.canSpeak&&!this.canSpeak())throw new Error('A conexão da saída de áudio foi interrompida.');
   const source=this.context.createBufferSource(),gain=this.context.createGain();
   source.buffer=buffer;gain.gain.value=utterance.volume;
   source.connect(gain);gain.connect(this.context.destination);
   source.onended=()=>{
    source.disconnect();gain.disconnect();source.buffer=null;
    if(token!==this.token)return;
    this.source=null;this.gain=null;this.current=null;utterance.onend?.();
   };
   this.source=source;this.gain=gain;source.start();utterance.onstart?.();
  }catch(error){
   if(token===this.token){this.current=null;utterance.onerror?.({error:error.speechCode||'synthesis-failed',message:error.name==='AbortError'?'A geração da voz demorou demais. Teste novamente.':error.message});}
  }finally{
   clearTimeout(deadline);if(this.controller===controller)this.controller=null;
  }
 }
}
