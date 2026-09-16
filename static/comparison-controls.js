let currentRecommendation=null,recommendationMatch='';
function comparisonIdentity(s){return JSON.stringify([s?.home?.name,s?.away?.name,s?.kickoff,s?.source]);}
function showRecommendation(report){
 currentRecommendation=report.recommendation;recommendationMatch=comparisonIdentity(S);
 const result=$('sourceRecommendation'),button=$('useRecommendedSource');
 if(!currentRecommendation){result.textContent='Reinicie o programa para habilitar a recomendação de fontes.';button.hidden=true;return;}
 const best=currentRecommendation.ranking.find(item=>item.provider===currentRecommendation.provider);
 result.innerHTML='<p><b>'+esc(best?'Indicada para narrar: '+best.name:'Sem recomendação disponível')+'</b></p><p>'+esc(currentRecommendation.reason)+'</p>'+
  currentRecommendation.ranking.map(item=>'<p><b>'+esc(item.name)+'</b> '+(item.eligible?'· cobertura '+item.score+'/85':'· indisponível para recomendação')+'<br>'+esc(item.reason)+'</p>').join('');
 button.hidden=!best||best.provider===report.primary;
 button.textContent=best?'Usar '+best.name+' para narrar':'Usar fonte recomendada';
}
$('useRecommendedSource').onclick=handle(async()=>{
 const selection=currentRecommendation?.selection;
 if(!selection||comparisonIdentity(S)!==recommendationMatch)throw new Error('A partida ou fonte mudou. Compare os dados novamente.');
 const button=$('useRecommendedSource');button.disabled=true;
 try{
  await post('/api/free/select',selection);
  $('dataSource').value=selection.provider;sourceChanged();
  await load();await refreshFreeStatus();
  button.hidden=true;currentRecommendation=null;
  $('sourceRecommendation').textContent='Fonte recomendada aplicada. A narração acompanha as próximas informações recebidas.';
  notice('Fonte principal atualizada para esta partida.');
 }finally{button.disabled=false;}
});
