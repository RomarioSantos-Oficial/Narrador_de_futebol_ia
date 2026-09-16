let narrationVoices=[];
const narrationSession=new NarrationSession({output:'control',onChange:renderNarrationStatus,onSettings:fillNarrationSettings});
const matchNarrator=narrationSession.narrator,speechOutput=narrationSession.speech,brainOutput=narrationSession.brain;
let settingsReady=false,saveTimer,saveChain=Promise.resolve();
const narrationInputs={narrationVoice:'voice',commentaryVoice:'commentaryVoice',narrationRate:'rate',narrationVolume:'volume',
 narrationStyle:'style',narrationInterval:'commentaryInterval',narrationDelivery:'delivery',narrationOutput:'output',
 narrationBrain:'brain',narrationCuriosities:'curiosities',announceLineups:'announceLineups',
 narrationEngagement:'engagement',engagementInterval:'engagementInterval'};

function fillNarrationSettings(settings){
 for(const [id,key] of Object.entries(narrationInputs)){
  const el=$(id);if(document.activeElement===el)continue;
  if(el.type==='checkbox')el.checked=settings[key];else el.value=settings[key];
 }
 settingsReady=true;updateNarrationLabels();renderNarrationStatus();
}
function renderNarrationStatus(local=narrationSession?.status||{}){
 const settings=narrationSession?.settings||{},remote=narrationSession?.state?.narration_playback||{};
 const obs=settings.output==='obs',active=!!settings.enabled||!!local.active;
 $('narrationStatus').textContent=obs?(remote.output==='obs'&&remote.connected?remote.status||'Canal OBS conectado.':settings.enabled?'Aguardando a fonte de navegador /audio no OBS.':'Áudio direcionado ao OBS. Clique em Iniciar narração.'):local.status||'Narração desligada.';
 $('narrationLastText').textContent=(obs?remote.text:local.lastText)||'';
 const source=$('narrationTextSource');source.replaceChildren();
 if(!obs&&local.lastSource){
  source.append('Fonte: ');let valid=false;try{const url=new URL(local.lastSource.url);valid=url.protocol==='https:'&&['ge.globo.com','www.thesportsdb.com','www.liverpoolfc.com','www.fulhamfc.com'].includes(url.hostname);}catch{}
  if(valid){const link=document.createElement('a');link.href=local.lastSource.url;link.textContent=local.lastSource.name;link.target='_blank';link.rel='noopener';source.append(link);}else source.append(local.lastSource.name||'Dados da partida');
 }else if(obs&&narrationSession?.state?.ge?.ready)source.textContent='Lances: ge · tempo real';
 $('startNarration').disabled=!settingsReady||active||!narrationVoices.length;
 $('stopNarration').disabled=!active;
 for(const id of ['testNarration','testCommentaryVoice'])$(id).disabled=active||obs||!narrationVoices.length;
 for(const id of ['hostCommentary','narrationPanorama','readLineups','skipLineups'])$(id).disabled=!settings.enabled;
 $('hostCommentary').textContent=settings.paused?'Retomar voz automática':'Vou comentar no microfone';
 $('narrationBadge').textContent=settings.paused?'PAUSADA':settings.enabled?(obs?'OBS':'ATIVADA'):local.active?'TESTE':'DESLIGADA';
 $('narrationBadge').classList.toggle('active',active);
 $('useDynamicVoice').disabled=!narrationVoices.some(v=>v.voiceURI==='kokoro:pm_alex');
}
function loadNarrationVoices(){
 narrationVoices=narrationSession.voices();
 narrationVoices.sort((a,b)=>Number(speechOutput.isLocalAI(b))-Number(speechOutput.isLocalAI(a))||a.name.localeCompare(b.name));
 for(const id of ['narrationVoice','commentaryVoice']){
  const el=$(id);el.replaceChildren();narrationVoices.forEach(v=>el.add(new Option(v.name,v.voiceURI)));
  if(!narrationVoices.length)el.add(new Option('Nenhuma voz local disponível',''));
 }
 $('narrationVoiceHelp').textContent=(speechOutput.message||'Verificando vozes…')+' Para áudio no OBS, use Alex, Dora, Santa ou Faber.';
 if(narrationSession.settings)fillNarrationSettings(narrationSession.settings);
}
function updateNarrationLabels(){
 $('narrationRateValue').textContent=Number($('narrationRate').value).toLocaleString('pt-BR')+'×';
 $('narrationVolumeValue').textContent=Math.round(Number($('narrationVolume').value)*100)+'%';
}
function saveNarrationPreferences(){
 if(!settingsReady)return;
 updateNarrationLabels();clearTimeout(saveTimer);
 const patch={};
 for(const [id,key] of Object.entries(narrationInputs)){
  const el=$(id);patch[key]=el.type==='checkbox'?el.checked:['rate','volume','commentaryInterval','engagementInterval'].includes(key)?Number(el.value):el.value;
 }
 saveTimer=setTimeout(()=>{saveChain=saveChain.then(()=>narrationSession.save(patch)).catch(e=>notice(e.message,true));},150);
}
const narrationAction=fn=>async()=>{try{await fn();}catch(e){notice(e.message,true);}};
for(const id of Object.keys(narrationInputs))$(id).oninput=saveNarrationPreferences;
$('testNarration').onclick=narrationAction(()=>narrationSession.preview());
$('testCommentaryVoice').onclick=narrationAction(()=>narrationSession.preview(true));
$('startNarration').onclick=narrationAction(async()=>{if(narrationSession.settings.output==='control')await narrationSession.unlock(matchNarrator.voice);await narrationSession.save({enabled:true,paused:false});});
$('stopNarration').onclick=narrationAction(async()=>{matchNarrator.stop();await narrationSession.save({enabled:false,paused:false});});
$('hostCommentary').onclick=narrationAction(()=>narrationSession.save({paused:!narrationSession.settings.paused}));
$('narrationPanorama').onclick=narrationAction(()=>narrationSession.commandAction('panorama'));
$('readLineups').onclick=narrationAction(()=>narrationSession.commandAction('lineups'));
$('skipLineups').onclick=narrationAction(()=>narrationSession.commandAction('skip_lineups'));
$('useDynamicVoice').onclick=narrationAction(()=>narrationSession.save({voice:'kokoro:pm_alex',commentaryVoice:'kokoro:pf_dora',delivery:'dynamic',rate:1}));
$('prepareBrain').onclick=narrationAction(async()=>{await brainOutput.prepare();showBrainStatus();});
function showBrainStatus(){$('brainStatus').textContent=brainOutput.message;$('prepareBrain').disabled=!brainOutput.status?.installed||brainOutput.status?.ready;}
$('refreshNarrationVoices').onclick=narrationAction(async()=>{await Promise.all([speechOutput.load(),brainOutput.load()]);loadNarrationVoices();showBrainStatus();});
window.speechSynthesis?.addEventListener('voiceschanged',loadNarrationVoices);
$('obsAudioUrl').textContent=location.origin+'/audio';
$('copyAudioUrl').onclick=narrationAction(async()=>{await navigator.clipboard.writeText(location.origin+'/audio');notice('Endereço de áudio copiado.');});
$('geEnabled').onchange=narrationAction(()=>narrationSession.request('/api/ge/options',{enabled:$('geEnabled').checked,url:''}));
$('geLink').onclick=narrationAction(()=>narrationSession.request('/api/ge/options',{enabled:true,url:$('geUrl').value.trim()}));
$('geAuto').onclick=narrationAction(async()=>{$('geUrl').value='';await narrationSession.request('/api/ge/options',{enabled:true,url:''});});
function updateNarrationState(state){
 narrationSession.update(state);renderNarrationStatus();
 const ge=state.ge||{};$('geStatus').textContent=ge.status||'A cobertura GE será buscada ao selecionar uma partida.';
 $('geEnabled').checked=ge.enabled!==false;
 $('geSource').replaceChildren();
 if(ge.url){const link=document.createElement('a');link.textContent='Abrir cobertura no GE';link.href=ge.url;link.target='_blank';link.rel='noopener';$('geSource').append(link);}
}
function refreshClubContext(){narrationSession.refreshContext();}
narrationSession.load().then(()=>{loadNarrationVoices();showBrainStatus();}).catch(e=>notice(e.message,true));
