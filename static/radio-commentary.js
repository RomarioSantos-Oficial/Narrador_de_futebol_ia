// Short commentary grounded in the current snapshot, with no simulated play-by-play.
class RadioCommentary {
 constructor(){this.reported=new Map();}
 pair(s,key,max=Infinity){
  const values=s.stats?.[key];
  if(!Array.isArray(values)||values.length!==2)return null;
  if(values.some(v=>v==null||v===''||!Number.isFinite(Number(v))||Number(v)<0||Number(v)>max))return null;
  return values.map(Number);
 }
 number(value){return Number(value).toLocaleString('pt-BR',{maximumFractionDigits:1});}
 candidates(s){
  const result=[],home=s.home.name,away=s.away.name;
  const shots=this.pair(s,'shots'),on=this.pair(s,'shots_on'),possession=this.pair(s,'possession',100);
  const add=(key,values,text)=>result.push({key,signature:JSON.stringify(values),text});
  if(shots){
   const validOn=on&&on.every((v,i)=>v<=shots[i]);
   let text=`Nas finalizações, ${home} tem ${this.number(shots[0])} e ${away}, ${this.number(shots[1])}.`;
   if(validOn)text+=` No gol, são ${this.number(on[0])} a ${this.number(on[1])}.`;
   add('shots',[shots,validOn?on:null],text);
  }else if(on)add('shots',[null,on],`Finalizações no gol: ${home}, ${this.number(on[0])}. ${away}, ${this.number(on[1])}.`);
  if(possession&&Math.abs(possession[0]+possession[1]-100)<=1){
   let text=`Na posse de bola, ${home} tem ${this.number(possession[0])} por cento e ${away}, ${this.number(possession[1])} por cento.`;
   if(shots){
    const leader=possession[0]>=55?0:possession[1]>=55?1:null;
    if(leader!==null&&shots[leader]<shots[1-leader])text+=` Apesar de mais posse, ${leader===0?home:away} soma menos finalizações.`;
   }
   add('possession',[possession,shots],text);
  }
  for(const [key,label] of [['corners','Escanteios'],['fouls','Faltas cometidas'],['offsides','Impedimentos']]){
   const values=this.pair(s,key);
   if(values)add(key,values,`${label} na partida: ${home}, ${this.number(values[0])}. ${away}, ${this.number(values[1])}.`);
  }
  const accuracy=this.pair(s,'pass_accuracy',100);
  if(accuracy)add('accuracy',accuracy,`Precisão de passe: ${home}, ${this.number(accuracy[0])} por cento. ${away}, ${this.number(accuracy[1])} por cento.`);
  return result;
 }
 reset(s){this.reported=new Map(this.candidates(s).map(c=>[c.key,c.signature]));}
 next(s){
  const candidate=this.candidates(s).find(c=>this.reported.get(c.key)!==c.signature);
  if(!candidate)return '';
  this.reported.set(candidate.key,candidate.signature);
  return 'Vamos aos números da partida. '+candidate.text;
 }
 score(s){
  if([s.home.score,s.away.score].some(v=>v==null||v===''||!Number.isFinite(Number(v))))return 'Placar não informado.';
  return `No placar, ${s.home.name}, ${s.home.score}. ${s.away.name}, ${s.away.score}.`;
 }
 clock(s){
  const value=String(s.clock_display??s.minute??'').replace(/['′\s]/g,'').match(/^(\d+)(?:\+(\d+))?$/);
  return value?`${value[1]} minutos${value[2]?`, mais ${value[2]} de acréscimo`:''}`:'';
 }
 snapshot(s){
  const intro=`Você acompanha ${s.home.name} e ${s.away.name}${s.competition?' pela '+s.competition:''}.`;
  if(s.phase==='pre'){
   const ranks=['home','away'].map(side=>{
    const r=s.standings?.[side];
    return r?.rank&&r.points!=null?`${s[side].name}: posição ${r.rank}, com ${r.points} pontos.`:'';
   }).filter(Boolean).join(' ');
   return `${intro} Pré-jogo.${ranks?' Na classificação informada pela fonte: '+ranks:''}`;
  }
  const moment=s.phase==='post'?'Partida encerrada.':s.status==='INTERVALO'?'Intervalo.':s.source==='manual'?'Dados do controle manual.':this.clock(s)?`Na última atualização, ${this.clock(s)}.`:'Na última informação recebida.';
  const numbers=this.candidates(s).slice(0,2).map(c=>c.text).join(' ');
  this.reset(s);
  return `${intro} ${moment} ${this.score(s)}${numbers?' '+numbers:''}`;
 }
 fresh(s){
  if(s.phase!=='in'||s.status==='INTERVALO'||s.source==='manual')return false;
  const received=Date.parse(s.updated_at);
  return Number.isFinite(received)&&Date.now()-received>=-5000&&Date.now()-received<=90000;
 }
}
