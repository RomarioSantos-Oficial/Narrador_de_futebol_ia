function resize(){const scale=Math.min(innerWidth/1920,innerHeight/1080);$('stage').style.transform=`scale(${scale})`;$('stage').style.left=(innerWidth-1920*scale)/2+'px';$('stage').style.top=(innerHeight-1080*scale)/2+'px'}
addEventListener('resize',resize);resize();
function logo(side,url,name){const img=$(side+'Logo'),fallback=$(side+'Fallback');fallback.textContent=name;img.alt='Escudo '+name;if(img.dataset.url===url)return;img.dataset.url=url||'';img.hidden=true;fallback.hidden=false;if(url){img.onload=()=>{img.hidden=false;fallback.hidden=true};img.onerror=()=>{img.hidden=true;fallback.hidden=false};img.src=url}else img.removeAttribute('src')}
function appearance(a={}){
 const root=document.documentElement;root.style.setProperty('--accent',a.accent||'#38e8a0');root.style.setProperty('--away',a.away_accent||'#72aaff');root.style.setProperty('--panel',`rgba(12,20,30,${a.panel_opacity??.94})`);
 $('channelName').textContent=a.channel_name||'';$('stage').classList.toggle('compact',a.layout==='compact');$('stage').classList.toggle('no-logos',a.show_logos===false);
 $('statsPanel').hidden=a.show_stats===false;$('eventsPanel').hidden=a.show_events===false;$('matchLineups').hidden=a.show_lineups===false;$('pitchPanel').hidden=!a.show_pitch;$('contextBand').hidden=a.show_context===false||a.scene!=='match';$('stage').classList.toggle('with-pitch',!!a.show_pitch);
 $('matchPanels').hidden=['lineups','bench','table'].includes(a.scene);$('lineupsPanel').hidden=!['lineups','bench'].includes(a.scene);$('lineupGroup').textContent=a.scene==='bench'?'Reservas':'Titulares';$('tablePanel').hidden=a.scene!=='table';
 const bg=$('backdrop');bg.style.backgroundImage='none';bg.style.backgroundColor='transparent';$('shade').style.background='transparent';
 if(a.background==='solid')bg.style.backgroundColor=a.background_color;
 if(a.background==='gradient'){bg.style.backgroundColor=a.background_color;bg.style.backgroundImage=`radial-gradient(ellipse at 20% 20%, ${a.accent}25, transparent 55%),radial-gradient(ellipse at 90% 80%, ${a.away_accent}20, transparent 60%),linear-gradient(135deg,transparent,#0006)`}
 if(a.background==='image'&&a.background_image){bg.style.backgroundColor=a.background_color;bg.style.backgroundImage=`url("${a.background_image}")`;$('shade').style.background=`rgba(0,0,0,${a.image_dim??.35})`}
}
let leagueState=null,leaguePages=[],leaguePage=0,leagueKey='',leagueScene='';
function drawLeagueTable(){
 const s=leagueState;if(!s)return;
 $('overlayTableTitle').textContent=s.league_table?.name||s.competition||'Tabela completa';
 $('tablePageIndicator').textContent=leaguePages.length>1?`${leaguePage+1} / ${leaguePages.length} · troca a cada 12 s`:'';
 $('overlayTableColumns').innerHTML=leaguePages.length?leaguePages[leaguePage].map(column=>`<div class="standings-column">${s.league_table.groups.length>1?`<h3>${esc(column.name)}</h3>`:''}${leagueRowsHTML(column.entries)}</div>`).join(''):'<p class="table-empty">A fonte não forneceu a tabela deste campeonato.<br><small>Competições de mata-mata podem não ter classificação por pontos.</small></p>';
 $('tableSourceNote').textContent=leaguePages.length?`Fonte: ${s.league_table.source||s.source}. Pode não incluir a partida em andamento. Times desta partida destacados.`:'';
}
function updateLeagueTable(s){
 const key=JSON.stringify([s.league_table?.league,s.competition,s.home.name,s.away.name,s.kickoff]);
 if(key!==leagueKey||(s.appearance?.scene==='table'&&leagueScene!=='table'))leaguePage=0;
 leagueKey=key;leagueScene=s.appearance?.scene;leagueState=s;
 const columns=[];for(const group of s.league_table?.groups||[])for(let i=0;i<group.entries.length;i+=10)columns.push({name:group.name,entries:group.entries.slice(i,i+10)});
 leaguePages=[];for(let i=0;i<columns.length;i+=2)leaguePages.push(columns.slice(i,i+2));
 if(leaguePage>=leaguePages.length)leaguePage=0;
 drawLeagueTable();
}
setInterval(()=>{if(leagueScene==='table'&&leaguePages.length>1){leaguePage=(leaguePage+1)%leaguePages.length;drawLeagueTable()}},12000);
function render(s){
 updateLeagueTable(s);
 const a=s.appearance||{};appearance(a);
 $('competition').textContent=s.competition;$('homeName').textContent=s.home.name;$('awayName').textContent=s.away.name;$('homeScore').textContent=s.home.score;$('awayScore').textContent=s.away.score;
 $('clock').textContent=s.clock_display??`${s.minute}′`;$('matchStatus').textContent=s.status;$('venue').textContent=s.venue||'';
 $('matchBadge').textContent=s.phase==='in'?'AO VIVO':s.phase==='post'?'ENCERRADO':s.phase==='manual'?'MANUAL':'PRÉ-JOGO';$('matchBadge').classList.toggle('live',s.phase==='in');
 for(const side of ['home','away']){logo(side,a[side+'_logo']||s[side].logo||'',s[side].abbreviation||s[side].name.slice(0,3).toUpperCase());$('stats'+(side==='home'?'Home':'Away')).textContent=s[side].abbreviation||s[side].name}
 const action=s.field_action,manual=s.source==='manual';$('ball').hidden=!action&&!manual;$('ball').style.left=(action?.x??s.ball.x)+'%';$('ball').style.top=(action?.y??s.ball.y)+'%';$('pitchEyebrow').textContent=manual?'CONTROLE MANUAL':'ÚLTIMA POSIÇÃO INFORMADA';$('zone').textContent=action?`${action.team} · ${action.minute} · Posição de lance registrado; não é a bola ao vivo.`:manual?s.ball.label:'A fonte não informa quem ataca ou a posição da bola ao vivo.';
 $('stats').innerHTML=Object.entries(statNames).map(([k,n])=>{const v=s.stats[k]||[null,null],x=Number(v[0]||0),y=Number(v[1]||0),sum=Math.max(1,x+y);const show=n=>n==null?'—':Number(n).toLocaleString('pt-BR')+(['possession','pass_accuracy'].includes(k)?'%':'');return `<div class="stat"><span class="stat-value">${show(v[0])}</span><div><div class="stat-name">${n}</div><div class="bar"><i style="width:${x/sum*100}%"></i><i style="width:${y/sum*100}%"></i></div></div><span class="stat-value">${show(v[1])}</span></div>`}).join('');
 const events=s.ge?.ready?s.ge.events||[]:s.events||[];
 $('events').innerHTML=events.length?events.slice(0,a.show_pitch?2:5).map(e=>`<div class="event"><span class="event-minute">${esc(e.minute)}${e.minute==='—'?'':'′'}</span><div><div class="event-text">${esc(e.icon)} ${esc(e.text)}</div>${e.editorial?'<small>Fonte: ge · tempo real</small>':''}${e.text_en?`<div class="event-english" lang="en">${esc(e.text_en)}</div>`:''}</div></div>`).join(''):'<p class="empty">Aguardando eventos da partida.</p>';
 $('overlayLineups').innerHTML=lineupHTML(s,a.scene==='bench'?'bench':'starters');
 $('matchLineupRows').innerHTML=lineupHTML(s,'starters');
 $('contextBand').innerHTML=['home','away'].map(side=>{const t=s.standings?.[side],history=s.recent_form?.[side]||[];return `<div class="context-team"><strong>${esc(s[side].name)}</strong><span class="context-rank">${t?.rank?esc(t.rank)+'º · '+esc(t.points??'—')+' pts':'Classificação indisponível'}</span><span class="form-label">ÚLTIMOS 5</span><div class="form-badges">${history.length?formBadges(history):'<small>Não informados</small>'}</div></div>`}).join('')+'<div class="context-caption">V vitória · E empate · D derrota · mais recente primeiro · últimos jogos em todas as competições · classificação informada pela fonte</div>';
 $('bookings').innerHTML=(s.cards||[]).length?'<span class="eyebrow">CARTÕES NA PARTIDA</span><div class="booking-list">'+s.cards.slice(-4).reverse().map(c=>`<div><span class="card-icon ${c.color==='red'?'red':''}"></span> ${esc(c.player)} <small>${esc(c.minute)}′ · ${esc(c.team)}</small></div>`).join('')+'</div>':'';
}
fetch('/api/state').then(r=>r.json()).then(render).catch(()=>{});
function connect(){const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`);ws.onmessage=e=>render(JSON.parse(e.data));ws.onclose=()=>setTimeout(connect,3000)}connect();
