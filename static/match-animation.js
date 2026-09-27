// Temporary graphics for newly received events. Opening/reconnecting never replays history.
class MatchAnimation {
 constructor(){this.key='';this.seen=new Set();this.queue=[];this.active=null;this.timer=null;this.state=null;this.baseline=true;this.score=0}
 reset(){clearTimeout(this.timer);this.timer=null;this.queue=[];this.active=null;document.getElementById('matchAnimation')?.remove()}
 roster(s){return ['home','away'].flatMap(side=>[...(s.lineups?.[side]?.starters||[]),...(s.lineups?.[side]?.bench||[])].map(p=>({...p,side})))}
 eventKey(e){return String(e.id||JSON.stringify([e.minute,e.kind,e.text]))}
 update(s){
  const source=s.source?.startsWith('ESPN')?'primary':s.ge?.ready?'ge':'primary';
  const key=JSON.stringify([s.source,s.kickoff,s.home?.name,s.away?.name,source,s.rehearsal?.session]);
  const events=source==='ge'?s.ge.events||[]:s.events||[];
  const total=Number(s.home?.score||0)+Number(s.away?.score||0);
  if(this.baseline||key!==this.key){this.reset();this.key=key;this.seen=new Set(events.map(e=>this.eventKey(e)));this.baseline=false;this.score=total;this.state=s;return}
  this.state=s;
  const visible=(s.appearance?.scene||'match')==='match'&&s.appearance?.show_lineups!==false;
  if(!visible||total<this.score)this.reset();
  this.score=total;
  for(const e of [...events].reverse()){
   const id=this.eventKey(e),kind=MatchEvents.kind(e);
   if(this.active?.id===id&&!['goal','substitution'].includes(kind))this.reset();
   if(this.seen.has(id))continue;
   this.seen.add(id);
   if(!visible||s.phase!=='in'||!['goal','substitution'].includes(kind))continue;
   const nums=String(e.minute||'').match(/\d+/g),minute=nums?nums.map(Number).reduce((a,b)=>a+b,0):null;
   if(minute!==null&&Number(s.minute)-minute>3)continue;
   this.queue.push({id,kind,event:e});
  }
  this.queue=this.queue.slice(-4);
  if(this.seen.size>1000)this.seen=new Set([...this.seen].slice(-500));
  if(!this.active)this.next();
 }
 portrait(player,label,css=''){
  const p=player||{},photo=player?playerPortrait(this.state,p):'';
  return `<div class="moment-person ${css}"><span class="moment-role">${esc(label)}</span><div class="moment-photo"><span aria-hidden="true">&#9679;</span>${photo?`<img src="${esc(photo)}" alt="" onerror="this.hidden=true">`:''}</div><strong>${esc(p.name||'Jogador não informado')}</strong>${p.number?`<small>CAMISA ${esc(p.number)}</small>`:''}</div>`;
 }
 next(){
  const item=this.queue.shift();if(!item)return;
  this.active=item;
  const s=this.state,e=item.event,roster=this.roster(s),norm=x=>String(x||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
  const side=MatchEvents.team(e,s);
  const find=ref=>{if(!ref)return null;const matches=roster.filter(p=>(!side||p.side===side)&&((ref.id&&String(p.id)===String(ref.id))||(ref.name&&norm(p.name)===norm(ref.name))));return matches.length===1?matches[0]:null};
  const refs=e.players||[];
  const scorer=find({name:e.player})||find(refs[0]);
  const people=refs.map(find).filter(Boolean);
  const outs=people.filter(p=>p.subbed_out),ins=people.filter(p=>p.subbed_in&&!p.subbed_out);
  const out=find(e.player_out)||(outs.length===1?outs[0]:null),incoming=find(e.player_in)||(ins.length===1?ins[0]:null);
  const geDescription=item.kind==='goal'&&scorer&&s.ge?.ready?(s.ge.events||[]).find(g=>g.kind==='goal'&&norm(g.player)===norm(scorer.name)&&String(g.minute)===String(e.minute)):null;
  const description=geDescription?.text||e.text||'';
  const el=document.createElement('section');el.id='matchAnimation';el.className='match-moment '+item.kind;el.setAttribute('aria-live','polite');
  el.innerHTML=`<div class="moment-shine"></div><div class="moment-content"><div class="moment-top">${esc(side?s[side].name:s.competition)} · ${esc(e.minute||'—')}′</div><h2>${item.kind==='goal'?'GOOOL!':'SUBSTITUIÇÃO'}</h2><div class="moment-people">${item.kind==='goal'?this.portrait(scorer||(e.player?{name:e.player}:null),'AUTOR DO GOL'):this.portrait(out,'SAI','out')+'<span class="moment-swap">⇄</span>'+this.portrait(incoming,'ENTRA','in')}</div><p class="moment-description">${esc(description)}</p><small class="moment-source">${geDescription?'GE · tempo real':esc(e.source?.name||s.source||'')}</small></div><div class="moment-progress" style="--duration:${item.kind==='goal'?9:7}s"></div>`;
  document.getElementById('matchLineups')?.appendChild(el);
  this.timer=setTimeout(()=>{el.remove();this.active=null;this.next()},item.kind==='goal'?9000:7000);
 }
}
const matchAnimation=new MatchAnimation();
