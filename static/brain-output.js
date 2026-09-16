// Optional local planning. A canceled or slow plan cannot hold up the match narration.
class BrainOutput {
 constructor(){this.enabled=true;this.status=null;this.message='Verificando a IA local…';}
 async load(){
  try{
   const response=await fetch('/api/brain/status');
   if(!response.ok)throw new Error();
   this.status=await response.json();this.message=this.status.message;
  }catch{this.status=null;this.message='Reinicie o programa pelo start.bat para carregar o cérebro local.';}
 }
 async prepare(){
  const response=await fetch('/api/brain/start',{method:'POST'});
  const body=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(body.detail||'Não foi possível preparar a IA. Reinicie o programa pelo start.bat.');
  this.status=body;this.message=body.message;
 }
 async compose(item,state,signal){
  if(!this.enabled||!this.status?.ready||item.kind!=='analysis')return item.text;
  const controller=new AbortController(),cancel=()=>controller.abort();
  signal.addEventListener('abort',cancel,{once:true});
  if(signal.aborted)controller.abort();
  const timeout=setTimeout(cancel,13000);
  const payload={text:item.text,kind:item.kind};
  if(item.panorama&&item.kind==='analysis'&&state?.phase!=='pre'){
   const radio=new RadioCommentary();
   payload.choices=radio.candidates(state).slice(0,8).map(fact=>fact.text);
   const moment=state.phase==='post'?'Partida encerrada.':state.status==='INTERVALO'?'Intervalo.':state.source==='manual'?'Dados do controle manual.':radio.clock(state)?`Na última atualização, ${radio.clock(state)}.`:'Na última informação recebida.';
   payload.anchor=moment+' '+radio.score(state);
  }
  try{
   const response=await fetch('/api/brain/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
   if(!response.ok)return item.text;
   const result=await response.json();
   return typeof result.text==='string'?result.text:item.text;
  }catch{return item.text;}
  finally{clearTimeout(timeout);signal.removeEventListener('abort',cancel);}
 }
}
