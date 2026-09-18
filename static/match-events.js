// Shared event interpretation for speech and graphics. Only use supplied facts.
class MatchEvents {
 static key(e){return e.id!=null?String(e.id)+':'+(e.revision||e.text||''):JSON.stringify([e.minute,e.icon,e.text]);}
 static kind(e){
  const text=String(e.text||'');
  if(/gol.{0,35}(?:anulad|cancelad)|(?:anulad|cancelad).{0,25}gol/i.test(text)||e.kind==='cancelled')return 'cancelled';
  if(e.corrected||e.kind==='correction')return 'correction';
  if(e.kind==='review'||/(?:VAR|vídeo).{0,50}(?:analisa|revis|verifica)|(?:revisão|checagem|análise).{0,40}(?:VAR|gol)|gol.{0,25}em análise/i.test(text))return 'review';
  if(e.kind==='goal'||(e.icon==='⚽'&&/^Gol\b/i.test(text)&&!/anulad|cancelad/i.test(text)))return 'goal';
  if(e.kind==='card'||['🟨','🟥'].includes(e.icon)||/^Cartão (amarelo|vermelho)/i.test(text))return 'card';
  if(e.kind==='substitution'||/(?:substitui|troca|mudança|entrou|saiu|^Sai\b.*\bentra\b)/i.test(text))return 'substitution';
  return 'event';
 }
 static label(e){return {goal:'GOL',card:e.icon==='🟥'||/vermelho/i.test(e.text)?'CARTÃO VERMELHO':'CARTÃO',substitution:'SUBSTITUIÇÃO',review:'VAR · EM ANÁLISE',cancelled:'GOL ANULADO',correction:'CORREÇÃO DA FONTE',event:'LANCE'}[this.kind(e)];}
 static team(e,s){
  const names=[e.player,...(e.players||[]).map(p=>p.name)].filter(Boolean);
  const matches=['home','away'].filter(side=>e.side===side||(e.team&&e.team===s[side]?.name)||names.some(name=>[...(s.lineups?.[side]?.starters||[]),...(s.lineups?.[side]?.bench||[])].some(p=>p.name===name)));
  return matches.length===1?matches[0]:null;
 }
}
