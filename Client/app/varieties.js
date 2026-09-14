/** Cosmetic presentation of server-confirmed identities. No encounter RNG here. */
export const VARIETY_KEYS=Object.freeze(['normal','ancient','metallic','shiny','mystic','shadow']);
const FALLBACK_COLORS=Object.freeze({normal:'#BDCAD8',ancient:'#FFAA55',metallic:'#91DCEC',shiny:'#FFF07A',mystic:'#C49AFF',shadow:'#F879B3'});
export function varietyKey(mon){
 if(!mon||typeof mon!=='object')return 'normal';
 if(typeof mon.variety==='string'&&VARIETY_KEYS.includes(mon.variety))return mon.variety;
 return !Object.prototype.hasOwnProperty.call(mon,'variety')&&mon.shiny===true?'shiny':'normal';
}
export function varietyDefinition(content,mon){
 const key=varietyKey(mon),row=content?.varietyPolicy?.definitions?.[key];
 return {key,label:row?.label||key[0].toUpperCase()+key.slice(1),color:/^#[0-9a-f]{6}$/i.test(row?.color||'')?row.color:FALLBACK_COLORS[key],weight:row?.weight??0};
}
export function frontSprite(content,mon){
 const sp=content?.species?.[mon?.species];if(!sp)return '';
 const key=varietyKey(mon),path=sp.varieties?.[key]?.front||(key==='shiny'?sp.shiny:null)||sp.front;
 return path?'assets/'+path:'';
}
export function pokemonName(content,mon){
 const sp=content?.species?.[mon?.species],name=mon?.name||sp?.name||'Pokémon',v=varietyDefinition(content,mon);
 return v.key==='normal'?name:v.label+' '+name;
}
export function followerPokemon(entity){
 const value=entity?.followerVariety;
 return {species:entity?.follower,...(value===undefined?{shiny:entity?.shiny===true}:{variety:value})};
}
export function eventPokemon(snapshot,event,side){
 // UUID and event-time variety distinguish two same-species partners switching
 // during a turn. Never borrow the incoming partner's variety for the outgoing one.
 const own=side==='you',current=own?snapshot.you:snapshot.opponent;
 const matching=event.uid?(own?snapshot.party||[]:[current]).find(m=>m?.uid===event.uid):null;
 const base=matching||(current?.species===event.species?current:{});
 const explicit=typeof event.variety==='string'&&VARIETY_KEYS.includes(event.variety);
 const variety=explicit?event.variety:varietyKey(base);
 return {...base,species:event.species,uid:event.uid??base.uid,variety,shiny:variety==='shiny',name:undefined};
}
export function drawFollowerSparkles(ctx,content,entity,cx,feet,scale,now,reducedMotion=false){
 const definition=varietyDefinition(content,followerPokemon(entity));
 if(!entity?.follower||definition.key==='normal'||!Number.isFinite(scale)||scale<=0)return 0;
 // Four bounded stars per visible follower; no particles accumulate and no extra
 // packets/assets/timers are required. Reduced motion retains a static marker.
 const seed=(Math.abs(Number(entity.id)||0)%997)/997,count=reducedMotion?2:4;
 ctx.save();ctx.fillStyle=definition.color;
 for(let i=0;i<count;i++){
  const phase=reducedMotion?(.25+i*.5):((Math.max(0,now)/1800+seed+i*.25)%1);
  const angle=i*Math.PI*.5+seed*6.28;
  const x=cx+Math.cos(angle)*9*scale;
  const y=feet-(10+Math.sin(angle)*6+(reducedMotion?0:phase*5))*scale;
  const alpha=reducedMotion?.9:(.22+.78*Math.sin(Math.PI*phase)**2);
  const radius=(.7+alpha*.8)*scale;ctx.globalAlpha=alpha;
  ctx.beginPath();ctx.moveTo(x,y-radius*1.5);ctx.lineTo(x+radius*.35,y-radius*.35);
  ctx.lineTo(x+radius*1.5,y);ctx.lineTo(x+radius*.35,y+radius*.35);
  ctx.lineTo(x,y+radius*1.5);ctx.lineTo(x-radius*.35,y+radius*.35);
  ctx.lineTo(x-radius*1.5,y);ctx.lineTo(x-radius*.35,y-radius*.35);ctx.closePath();ctx.fill();
 }
 ctx.restore();return count;
}
