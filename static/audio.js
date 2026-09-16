const monitorMode=new URLSearchParams(location.search).has('monitor');
const audioSession=new NarrationSession({output:'obs',onChange:status=>{
 document.getElementById('status').textContent=status.status;
 document.getElementById('transcript').textContent=status.lastText||'';
 document.body.classList.toggle('monitor',monitorMode);
}});
document.body.classList.toggle('monitor',monitorMode);
document.getElementById('activate').onclick=async()=>{
 try{
  const voice=audioSession.voices().find(v=>v.voiceURI===audioSession.settings?.voice)||audioSession.voices().find(v=>audioSession.speech.isLocalAI(v));
  await audioSession.unlock(voice);
  await audioSession.save({output:'obs',enabled:true,paused:false});
 }catch(e){document.getElementById('status').textContent=e.message;}
};
document.getElementById('pause').onclick=()=>audioSession.save({paused:!audioSession.settings?.paused});
async function connect(){
 const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);
 ws.onmessage=event=>audioSession.update(JSON.parse(event.data));
 ws.onclose=()=>{audioSession.disconnect();setTimeout(connect,3000);};
}
audioSession.load().then(connect).catch(e=>{document.getElementById('status').textContent=e.message;setTimeout(()=>location.reload(),5000);});
