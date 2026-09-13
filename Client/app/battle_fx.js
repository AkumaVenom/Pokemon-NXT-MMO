import {planBattleEvents} from './battle_timing.js';
/** Animates committed server events only. No local damage or type calculation. */
export class BattleFX {
 constructor({setTimer=(...args)=>globalThis.setTimeout(...args),clearTimer=(...args)=>globalThis.clearTimeout(...args),reducedMotion=()=>globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches??false}={}){this.setTimer=setTimer;this.clearTimer=clearTimer;this.reducedMotion=reducedMotion;this.timers=new Set();this.animations=new Set();this.nodes=new Set();this.seen=new Set();this.key=null;this.battle=null;this.busy=false;this.serial=0;this.onFailure=null;}
 reset(){this.serial++;this.busy=false;this.onFailure=null;for(const t of this.timers){try{this.clearTimer(t);}catch{}}this.timers.clear();for(const a of this.animations){try{a.cancel();}catch{}}this.animations.clear();for(const n of this.nodes){try{n.remove();}catch{}}this.nodes.clear();this.key=null;this.battle=null;this.seen.clear();}
 fail(error){const callback=this.onFailure;this.reset();callback?.(error);}
 skip(snapshot){this.reset();this.battle=snapshot.id;this.key=String(snapshot.id)+':'+String(snapshot.audio?.revision??snapshot.turn);}
 matches(snapshot){return this.key===String(snapshot?.id)+':'+String(snapshot?.audio?.revision??snapshot?.turn);}
 later(fn,delay){const serial=this.serial;const t=this.setTimer(()=>{this.timers.delete(t);if(serial===this.serial){try{fn();}catch(error){this.fail(error);}}},delay);this.timers.add(t);}
 animate(node,frames,options){if(!node?.animate||this.reducedMotion())return;for(const old of this.animations)if(old.__battleNode===node){old.cancel();this.animations.delete(old);}const a=node.animate(frames,options);a.__battleNode=node;this.animations.add(a);a.onfinish=()=>{if(options.fill!=='forwards')this.animations.delete(a);};}
 popup(stage,side,lines,tone='normal'){
  if(!lines.length)return;const node=stage.ownerDocument.createElement('div');node.className='battle-float '+side+' '+tone;node.setAttribute('role','status');
  for(const [index,line] of lines.entries()){const text=stage.ownerDocument.createElement(index?'span':'strong');text.textContent=line;node.append(text);}stage.append(node);this.nodes.add(node);
  this.animate(node,[{opacity:0,transform:'translateY(8px) scale(.92)'},{opacity:1,transform:'translateY(0) scale(1)',offset:.18},{opacity:1,transform:'translateY(-13px)',offset:.8},{opacity:0,transform:'translateY(-20px)'}],{duration:820,easing:'ease-out'});
  this.later(()=>{node.remove();this.nodes.delete(node);},850);
 }
 event(stage,event,moveName,showSpecies){
  const side=event.side==='you'?'you':'enemy',other=side==='you'?'enemy':'you';let image=stage.querySelector('.battle-sprite.'+side);
  if(event.species&&['move','hit','sendout'].includes(event.cue))showSpecies?.(image,event,side);
  const text=[];let tone='normal';
  if(event.cue==='move'){
   this.popup(stage,side,[moveName(event.move)],'move-name');
   this.later(()=>this.animate(image,[{transform:'translate(0,0)'},{transform:side==='you'?'translate(54px,-22px)':'translate(-54px,22px)',offset:.65},{transform:'translate(0,0)'}],{duration:240,easing:'cubic-bezier(.2,.7,.3,1)'}),440);return;
  }
  if(event.cue==='hit'){
   if(Number.isFinite(event.damage)&&event.damage>=0)text.push('−'+Math.round(event.damage));
   if(event.critical)text.push('Critical hit!');
   if(event.effectiveness===0){text.push('No effect');tone='immune';}else if(event.effectiveness>1){text.push('Super effective!');tone='super';}else if(event.effectiveness>0&&event.effectiveness<1){text.push('Not very effective');tone='resisted';}
   this.animate(image,[{filter:'brightness(1)'},{filter:'brightness(2.2)',transform:'translateX(-7px)',offset:.2},{filter:'brightness(1)',transform:'translateX(6px)',offset:.45},{transform:'translateX(-3px)',offset:.7},{transform:'translateX(0)'}],{duration:260,easing:'ease-out'});
  }else if(event.cue==='miss'){this.popup(stage,other,['Missed'],'immune');return;}
  else if(event.cue==='no_effect'){text.push('No effect');tone='immune';}
  else if(event.cue==='protected'){text.push('Protected');tone='immune';}
  else if(event.cue==='recover'){text.push(Number.isFinite(event.amount)?'+'+event.amount+' HP':'Recovered');tone='recover';}
  else if(event.cue==='damage'){text.push(Number.isFinite(event.damage)?'−'+event.damage:({recoil:'Recoil',burn:'Burn',poison:'Poison',seed:'Leech Seed'}[event.reason]||'Damage'));}
  else if(event.cue==='faint'){text.push('Fainted');this.animate(image,[{opacity:1},{opacity:.3,transform:'translateY(14px)'}],{duration:240,fill:'forwards'});}
  else if(event.cue==='sendout'){this.animate(image,[{opacity:0,transform:'scale(.8)'},{opacity:1,transform:'scale(1)'}],{duration:250,easing:'ease-out'});}
  this.popup(stage,side,text,tone);
 }
 play(snapshot,stage,{done=()=>{},failed=()=>{},moveName=id=>'Move '+id,showSpecies}={}){
  const key=String(snapshot.id)+':'+String(snapshot.audio?.revision??snapshot.turn);if(this.key===key)return false;
  const sameBattle=this.battle===snapshot.id,seen=sameBattle?new Set(this.seen):new Set();this.reset();this.onFailure=failed;this.seen=seen;this.battle=snapshot.id;this.key=key;
  const events=(snapshot.audio?.events||[]).filter((event,index)=>{if(!event)return false;const id=event.id!=null?String(snapshot.id)+':'+String(event.id):key+':'+index;if(this.seen.has(id))return false;this.seen.add(id);return true;});if(this.seen.size>512)this.seen=new Set([...this.seen].slice(-256));
  const timeline=planBattleEvents(events);if(!timeline.some(item=>!['battle_start','battle_end'].includes(item.event.cue)))return false;
  for(const side of ['you','opponent']){const first=events.find(event=>event.side===side&&event.species&&['move','hit','sendout'].includes(event.cue));if(first)showSpecies?.(stage.querySelector('.battle-sprite.'+(side==='you'?'you':'enemy')),first,side==='you'?'you':'enemy');}this.busy=true;for(const item of timeline)this.later(()=>this.event(stage,item.event,moveName,showSpecies),item.at);
  const duration=Math.min(15000,Math.max(...timeline.map(item=>item.at+item.duration))+500);this.later(()=>{this.busy=false;for(const a of this.animations)a.cancel();this.animations.clear();for(const node of this.nodes)node.remove();this.nodes.clear();done();},duration);return true;
 }
}
