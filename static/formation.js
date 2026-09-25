function profileKey(s,p){return [s.source,p.id,p.name].map(v=>v??'').join('|')}
function formationPhoto(url){try{const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password?u.href:''}catch{return ''}}
function formationSlots(lineup){
 const starters=lineup.starters||[],all=[...starters,...(lineup.bench||[])],active=currentPlayers(lineup),placed=new Set();
 const parts=String(lineup.formation||'').split('-').map(Number);
 if(!parts.length||parts.some(n=>!Number.isInteger(n)||n<1||n>5)||parts.reduce((a,b)=>a+b,0)!==10||starters.length!==11)return {slots:[],unplaced:active};
 const rows=[1,...parts],rank=p=>{const pos=String(p.position||'').toUpperCase();return /^(G|GK)$/.test(pos)?0:/^(D|CD|LB|RB|CB|LWB|RWB)/.test(pos)?1:/DM/.test(pos)?2:/^(M|CM|LM|RM)/.test(pos)?3:/AM/.test(pos)?4:5};
 const ordered=[...starters].sort((a,b)=>rank(a)-rank(b)||Number(a.formation_place||99)-Number(b.formation_place||99));
 let index=0;const slots=[];
 rows.forEach((count,row)=>{for(let col=0;col<count;col++){
   let p=ordered[index++];const visited=new Set();
   while(p?.subbed_out&&p.replacement_id&&!visited.has(p.id)){visited.add(p.id);p=all.find(q=>String(q.id)===String(p.replacement_id))}
   if(!p||p.subbed_out||p.red||!active.includes(p)||placed.has(p))continue;
   placed.add(p);slots.push({player:p,x:100*(col+1)/(count+1),y:10+row*78/(rows.length-1)});
 }});
 return {slots,unplaced:active.filter(p=>!placed.has(p))};
}
function formationPlayer(s,p,side){
 const bio=s.player_profiles?.[profileKey(s,p)]||{},photo=formationPhoto(p.photo)||formationPhoto(bio.photo);
 const flags=`${p.subbed_in?'<span title="Entrou em campo">↗</span>':''}${p.yellow?'<span class="formation-yellow" title="Cartão amarelo"></span>':''}`;
 return `<button type="button" class="formation-player" data-player-id="${esc(p.id)}" data-player-side="${side}" title="${esc(p.name)} · ${esc(p.position||'Posição não informada')}"><span class="formation-avatar"><span aria-hidden="true">●</span>${photo?`<img src="${esc(photo)}" alt="" loading="lazy" onerror="this.hidden=true">`:''}<span class="formation-flags">${flags}</span></span><span class="formation-name">${esc(p.number||'—')} ${esc(p.name)}</span></button>`;
}
function formationHTML(s){
 const layouts=['home','away'].map(side=>formationSlots(s.lineups?.[side]||{}));
 const header=side=>`<div class="formation-team"><strong>${formationPhoto(s[side]?.logo)?`<img src="${esc(formationPhoto(s[side].logo))}" alt="" onerror="this.hidden=true">`:''}${esc(s[side]?.name||'Time')}</strong><span>${esc(s.lineups?.[side]?.formation||'Formação não informada')}</span></div>`;
 const half=(side,i)=>`<div class="formation-half ${side}"><div class="formation-box"></div>${layouts[i].slots.map(slot=>`<div class="formation-slot" style="left:${slot.x}%;top:${side==='home'?slot.y:100-slot.y}%">${formationPlayer(s,slot.player,side)}</div>`).join('')}${!layouts[i].slots.length?'<p class="formation-missing">Posicionamento não disponível</p>':''}</div>`;
 const missing=['home','away'].map((side,i)=>layouts[i].unplaced.length?`<div class="formation-unplaced"><strong>${esc(s[side]?.name)} · sem posição confirmada</strong><div>${layouts[i].unplaced.map(p=>formationPlayer(s,p,side)).join('')}</div></div>`:'').join('');
 return `<div class="formation-board">${header('home')}<div class="formation-grass"><div class="formation-circle"></div>${half('home',0)}${half('away',1)}</div>${header('away')}</div>${missing}<p class="formation-caption">Disposição tática aproximada a partir da formação inicial. Substitutos ocupam a vaga informada pela fonte. Não representa movimento ao vivo.<br>Dados: ${esc(s.source||'—')} · Fotos complementares: TheSportsDB, quando disponíveis.</p>`;
}
function formationDetails(s,side,id){
 const l=s.lineups?.[side]||{},p=[...(l.starters||[]),...(l.bench||[])].find(p=>String(p.id)===id);if(!p)return '';
 const bio=s.player_profiles?.[profileKey(s,p)]||{};
 const labels={totalGoals:'Gols',goalAssists:'Assistências',totalShots:'Finalizações',saves:'Defesas',foulsCommitted:'Faltas cometidas'};
 return `<h3>${esc(p.name)}</h3><p>Camisa ${esc(p.number||'—')} · Posição: ${esc(p.position||'—')}</p><dl>${Object.entries({Nacionalidade:bio.nationality,Nascimento:bio.birth_date,Altura:bio.height,Peso:bio.weight,Clube:bio.club}).filter(([,v])=>v).map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}${Object.entries(p.match_stats||{}).filter(([k])=>labels[k]).map(([k,v])=>`<div><dt>${labels[k]} nesta partida</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><p class="formation-caption">Estatísticas: ${esc(s.source)}.${bio.source?' Perfil: '+esc(bio.source)+'.':' Perfil complementar ainda não disponível.'}</p>`;
}
function benchPlayers(lineup){return (lineup.bench||[]).filter(p=>!p.subbed_in&&!p.subbed_out&&!p.red)}
function formationBenchHTML(s){
 return ['home','away'].map(side=>{
  const lineup=s.lineups?.[side],players=benchPlayers(lineup||{});
  return `<section class="formation-bench-team"><header><span class="eyebrow">NO BANCO</span><h3>${esc(s[side]?.name||'Time')}</h3></header><div class="formation-bench-grid">${players.length?players.map(p=>formationPlayer(s,p,side)).join(''):`<p class="formation-bench-empty">${lineup?.bench?.length?'Nenhum reserva disponível informado.':'Banco não informado pela fonte.'}</p>`}</div></section>`;
 }).join('');
}
let formationSelected=null;
function renderFormation(s){
 const target=document.getElementById('formationPreview');if(target){target.innerHTML=formationHTML(s);document.getElementById('profileStatus').textContent=s.profile_status||'Busque fotos e informações complementares dos jogadores.';
 if(formationSelected)document.getElementById('formationDetails').innerHTML=formationDetails(s,...formationSelected);}
 const overlay=document.getElementById('formationPanel');if(overlay)overlay.innerHTML=formationHTML(s);
 for(const id of ['formationBenchPanel','formationBenchPreview']){const bank=document.getElementById(id);if(bank)bank.innerHTML=formationBenchHTML(s)}
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-player-id]');if(b&&typeof S!=='undefined'&&S){formationSelected=[b.dataset.playerSide,b.dataset.playerId];document.getElementById('formationDetails').innerHTML=formationDetails(S,...formationSelected)}});
