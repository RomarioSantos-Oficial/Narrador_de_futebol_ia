let photoChoices=new Map(),photoChoiceSignature='';
function updatePlayerPhotoPreview(){
 const selected=photoChoices.get($('playerPhotoSelect').value),image=$('playerPhotoPreview');
 $('playerPhotoUpload').disabled=!selected;
 $('resetPlayerPhoto').disabled=!selected;
 if(!selected){image.hidden=true;$('playerPhotoStatus').textContent='Carregue uma partida e selecione um jogador.';return}
 const {player}=selected,url=playerPortrait(S,player),custom=S.player_photo_overrides?.[profileKey(S,player)];
 image.hidden=!url;image.onerror=()=>{image.hidden=true};image.alt='Foto de '+player.name;
 if(url&&image.getAttribute('src')!==url)image.src=url;
 $('playerPhotoStatus').textContent=custom?'Foto enviada por você.':url?'Foto automática disponível.':'Sem foto disponível. Você pode enviar uma imagem.';
 $('resetPlayerPhoto').disabled=!custom;
}
function renderPlayerPhotoControls(s){
 if(!$('playerPhotoSelect'))return;
 const rows=[];photoChoices=new Map();
 for(const side of ['home','away']){const l=s.lineups?.[side]||{};
  for(const player of [...(l.starters||[]),...(l.bench||[])]){
   const key=profileKey(s,player);if(photoChoices.has(key))continue;
   photoChoices.set(key,{player,side});rows.push([key,`${s[side].name} · ${player.number||'—'} ${player.name}${playerPortrait(s,player)?'':' · sem foto'}`]);
  }
 }
 const signature=JSON.stringify(rows),select=$('playerPhotoSelect');
 if(signature!==photoChoiceSignature){const previous=select.value;select.innerHTML=rows.length?rows.map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join(''):'<option value="">Carregue uma partida com escalações</option>';if(photoChoices.has(previous))select.value=previous;photoChoiceSignature=signature}
 $('rosterProfileStatus').textContent=s.profile_status||'';
 // Rendering receives the newest state before the control's shared S is assigned.
 const choice=photoChoices.get(select.value);if(choice){
  const image=$('playerPhotoPreview'),url=playerPortrait(s,choice.player),custom=s.player_photo_overrides?.[select.value];
  image.hidden=!url;image.onerror=()=>image.hidden=true;image.alt='Foto de '+choice.player.name;if(url&&image.getAttribute('src')!==url)image.src=url;
  $('playerPhotoStatus').textContent=custom?'Foto enviada por você.':url?'Foto automática disponível.':'Sem foto disponível. Você pode enviar uma imagem.';
  $('playerPhotoUpload').disabled=false;$('resetPlayerPhoto').disabled=!custom;
 }else{$('playerPhotoPreview').hidden=true;$('playerPhotoUpload').disabled=true;$('resetPlayerPhoto').disabled=true;$('playerPhotoStatus').textContent='Carregue uma partida com escalações.'}
}
document.getElementById('playerPhotoSelect').onchange=()=>updatePlayerPhotoPreview();
document.getElementById('playerPhotoUpload').onchange=async e=>{
 const file=e.target.files[0],key=$('playerPhotoSelect').value;if(!file||!key)return;
 e.target.disabled=true;
 try{
  if(file.size>5*1024*1024)throw new Error('A foto deve ter no máximo 5 MB.');
  if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Escolha PNG, JPG ou WebP.');
  const bitmap=await createImageBitmap(file).catch(()=>{throw new Error('Não foi possível abrir essa imagem.')});bitmap.close();
  const uploaded=await api('/api/appearance/upload',{method:'POST',headers:{'Content-Type':file.type},body:file});
  await post('/api/players/photo',{key,url:uploaded.url});await load();notice('Foto do jogador salva e aplicada à transmissão.');
 }catch(error){notice(error.message,true)}finally{e.target.value='';e.target.disabled=!photoChoices.size}
};
document.getElementById('resetPlayerPhoto').onclick=async()=>{try{const key=$('playerPhotoSelect').value;if(!key)return;await post('/api/players/photo',{key,url:''});await load();notice('Foto automática restaurada.')}catch(error){notice(error.message,true)}};
document.getElementById('searchRosterProfiles').onclick=async()=>{try{const r=await post('/api/players/profiles',{});notice(r.status)}catch(error){notice(error.message,true)}};
