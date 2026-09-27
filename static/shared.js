const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statNames={possession:'Posse de bola',shots:'Finalizações',shots_on:'No gol',passes:'Passes',pass_accuracy:'Precisão de passe',fouls:'Faltas',corners:'Escanteios',offsides:'Impedimentos',saves:'Defesas',yellow:'Cartões amarelos',red:'Cartões vermelhos'};
function formBadges(history){return history.map(g=>`<span class="form-result ${g.result==='V'?'win':g.result==='D'?'loss':'draw'}" title="${({V:'Vitória',D:'Derrota',E:'Empate'})[g.result]||'Resultado não informado'} · ${esc(g.date)} · ${esc(g.opponent)} · ${esc(g.score)} · ${esc(g.competition)}">${esc(g.result)}</span>`).join('')}
function playerRows(players){return players.map(p=>`<div class="player"><span class="shirt-number">${esc(p.number)||'—'}</span><span class="player-name">${esc(p.name)}</span><span class="player-position">${esc(p.position)}</span><span class="player-flags">${p.subbed_in?'<span title="Entrou em campo">↗</span>':''}${p.subbed_out?'<span title="Substituído">↙</span>':''}${p.yellow?`<span title="${p.yellow} cartão(ões) amarelo(s)" class="card-icon"></span>${p.yellow>1?p.yellow:''}`:''}${p.red?'<span title="Cartão vermelho" class="card-icon red"></span>':''}</span></div>`).join('')}
function pregameState(s){
 renderSupportCredit(s);
 if(s.phase!=='pre')return s;
 const lineups={...s.lineups};
 for(const side of ['home','away']){
  const announced=s.ge?.ready?s.ge.lineups?.[side]:null;
  if(announced?.starters?.length===11)lineups[side]=announced;
  if(lineups[side])lineups[side]={...lineups[side],...Object.fromEntries(['starters','bench'].map(group=>[group,(lineups[side][group]||[]).map(p=>({...p,subbed_in:false,subbed_out:false,replacement_id:''}))]))};
 }
 return {...s,lineups};
}
function renderSupportCredit(s){
 let credit=document.getElementById('supportCredit');
 if(!credit){credit=document.createElement('a');credit.id='supportCredit';credit.href='https://sportscore.com/';credit.target='_blank';credit.rel='noopener';credit.textContent='Powered by SportScore';credit.style.cssText='position:absolute;bottom:8px;right:14px;font:12px sans-serif;color:#fff;background:#101820;padding:5px 8px;border-radius:4px;z-index:20';(document.getElementById('stage')||document.body).appendChild(credit)}
 credit.hidden=!(s.support_sources||[]).includes('SportScore');
}
function currentPlayers(lineup){return [...(lineup.starters||[]),...(lineup.bench||[]).filter(p=>p.subbed_in)].filter(p=>!p.subbed_out&&!p.red)}
function lineupHTML(s,group){return ['home','away'].map(side=>{const l=s.lineups?.[side]||{},players=group==='field'?currentPlayers(l):l[group]||[];return `<div class="lineup-team ${group==='bench'?'reserves':''}"><h3>${esc(s[side].name)} <small>${esc(group==='field'?'':l.formation||'')}</small></h3>${players.length?(typeof rosterPlayerHTML==='function'?players.map(p=>rosterPlayerHTML(s,p,side)).join(''):playerRows(players)):'<p class="empty">'+(group==='bench'?'Reservas não informados pela fonte.':'Escalação ainda não disponível.')+'</p>'}</div>`}).join('')}
function leagueRowsHTML(entries){return `<table class="league-table"><thead><tr><th>Pos.</th><th>Clube</th><th title="Pontos">PTS</th><th title="Jogos no campeonato">J</th><th title="Vitórias no campeonato">V</th><th title="Empates no campeonato">E</th><th title="Derrotas no campeonato">D</th><th title="Saldo de gols">SG</th></tr></thead><tbody>${entries.map(r=>`<tr class="${r.side==='home'?'selected-home':r.side==='away'?'selected-away':''}"><td>${esc(r.rank??'—')}</td><td><div class="league-club">${r.logo?`<img src="${esc(r.logo)}" alt="" loading="lazy" onerror="this.hidden=true">`:''}<span>${esc(r.team)}</span>${r.side?'<i class="playing-dot" title="Time desta partida"></i>':''}</div></td>${['points','played','wins','draws','losses','goal_difference'].map(k=>`<td>${esc(r[k]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
