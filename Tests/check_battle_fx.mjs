import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const data=code=>'data:text/javascript;base64,'+Buffer.from(code).toString('base64');
const timing=fs.readFileSync(new URL('../Client/app/battle_timing.js',import.meta.url),'utf8');
const fxSource=fs.readFileSync(new URL('../Client/app/battle_fx.js',import.meta.url),'utf8').replace("'./battle_timing.js'",JSON.stringify(data(timing)));
const {BattleFX}=await import(data(fxSource));const {planBattleEvents}=await import(data(timing));
class Element{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.events={};this.style={};this.attributes={};this.className='';this.textContent='';this.open=false;this.disabled=false;this.animations=[];this.classList={add(){},remove(){},toggle(){},contains:()=>false};}
 append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}prepend(...nodes){for(const node of nodes)node.parent=this;this.children.unshift(...nodes);}replaceChildren(...nodes){this.children=[];this.append(...nodes);}remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}setAttribute(k,v){this.attributes[k]=v;}getAttribute(k){return this.attributes[k];}addEventListener(k,fn){this.events[k]=fn;}showModal(){this.open=true;}close(){this.open=false;}get firstChild(){return this.children[0];}querySelector(selector){const classes=selector.split('.').filter(Boolean);return flatten(this).find(n=>classes.every(c=>n.className.split(' ').includes(c)));}animate(frames,options){const a={frames,options,cancelled:false,cancel(){this.cancelled=true;}};this.animations.push(a);return a;}
}
const flatten=node=>[node,...node.children.flatMap(flatten)];const words=node=>node.textContent+node.children.map(words).join(' ');
function clock(){let now=0,n=0;const tasks=new Map();return{setTimer(fn,delay){const id=++n;tasks.set(id,{fn,at:now+delay});return id;},clearTimer:id=>tasks.delete(id),tick(ms){const end=now+ms;while(true){const next=[...tasks].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;tasks.delete(next[0]);now=next[1].at;next[1].fn();}now=end;},get size(){return tasks.size;}};}
function fixture(reduced=false){const time=clock(),doc={createElement(tag){const node=new Element(tag);node.ownerDocument=doc;return node;}},stage=doc.createElement('div');for(const side of ['you','enemy']){const sprite=doc.createElement('img');sprite.className='battle-sprite '+side;stage.append(sprite);}const fx=new BattleFX({...time,reducedMotion:()=>reduced}),shown=[];let done=0;return{time,stage,fx,shown,play(events,revision=1,id='battle'){return fx.play({id,audio:{revision,events}},stage,{moveName:()=>'<Ember>',showSpecies:(node,event,side)=>shown.push([side,event.species]),done:()=>done++});},get done(){return done;}};}
const move=(id,side='you')=>({id,cue:'move',side,move:52,species:side==='you'?'fr_155':'fr_1'});
const hit=(id,side='opponent')=>({id,cue:'hit',side,species:side==='you'?'fr_155':'fr_1',damage:23,effectiveness:2,critical:true});
test('shared compact timeline orders both sides without changing server events',()=>{const events=[move('a'),hit('b'),move('c','opponent'),hit('d','you')],before=JSON.stringify(events),plan=planBattleEvents(events);assert.deepEqual(plan.map(x=>x.at),[0,600,960,1560]);assert.equal(JSON.stringify(events),before);});
test('both attackers lunge toward enemy and authoritative hit labels anchor to each target',()=>{const f=fixture();f.play([move('a'),hit('b'),move('c','opponent'),hit('d','you')]);f.time.tick(440);assert.match(JSON.stringify(f.stage.querySelector('.you').animations[0].frames),/54px,-22px/);f.time.tick(160);assert.match(words(f.stage),/−23 Critical hit! Super effective!/);assert.ok(flatten(f.stage).some(n=>n.className==='battle-float enemy super'));f.time.tick(800);assert.match(JSON.stringify(f.stage.querySelector('.enemy').animations.at(-1).frames),/-54px,22px/);f.time.tick(160);assert.ok(flatten(f.stage).some(n=>n.className==='battle-float you super'));f.time.tick(2000);assert.equal(f.fx.busy,false);assert.equal(f.done,1);});
test('waiting snapshots and repeated event ids never replay',()=>{const f=fixture(),events=[move('a'),hit('b')];f.play(events);const count=f.time.size;assert.equal(f.play(events),false);assert.equal(f.time.size,count);f.time.tick(2000);assert.equal(f.play(events,2),false);assert.equal(f.done,1);});
test('new revision and reset cancel all stale animations, labels, timers and callbacks',()=>{const f=fixture();f.play([move('a'),hit('b')]);f.time.tick(600);const old=f.stage.querySelector('.enemy').animations[0];f.play([move('new')],2);assert.equal(old.cancelled,true);assert.doesNotMatch(words(f.stage),/−23/);f.fx.reset();f.time.tick(20000);assert.equal(f.done,0);assert.equal(f.fx.busy,false);assert.equal(f.time.size,0);});
test('new battle may reuse ids and reduced motion preserves readable hit feedback',()=>{const f=fixture(true);f.play([hit('a')]);f.time.tick(0);assert.match(words(f.stage),/−23/);assert.equal(f.stage.querySelector('.enemy').animations.length,0);f.time.tick(1000);assert.equal(f.play([hit('a')],1,'other'),true);});
test('resistance, immunity, misses and protection use explicit outcomes',()=>{const f=fixture();f.play([{...hit('a'),effectiveness:.5,critical:false},{id:'b',cue:'no_effect',side:'you'},{id:'c',cue:'miss',side:'you'},{id:'d',cue:'protected',side:'you'}]);f.time.tick(0);assert.match(words(f.stage),/Not very effective/);f.time.tick(360);assert.match(words(f.stage),/No effect/);f.time.tick(180);assert.ok(flatten(f.stage).some(n=>n.className==='battle-float enemy immune'&&words(n).includes('Missed')));f.time.tick(180);assert.match(words(f.stage),/Protected/);});
test('old defeated species is shown before replacement sendout, without guessed damage',()=>{const f=fixture();f.play([hit('old'),{id:'new',cue:'sendout',side:'opponent',species:'fr_4'}]);assert.deepEqual(f.shown[0],['enemy','fr_1']);f.time.tick(360);assert.deepEqual(f.shown.at(-1),['enemy','fr_4']);});

// Browser timers reject a foreign receiver. The historical injected clock did
// not model that contract, so default BattleFX timers must also run in the VM.
function appHarness({browserTimers=false,entryEvents=[],scheduleFailureAt=0,animationFailure=false}={}){
 const time=clock(),nodes=new Map(),doc={createElement(tag){const node=new Element(tag);node.ownerDocument=doc;return node;},createTextNode(text){const node=this.createElement('#text');node.textContent=String(text);return node;},getElementById(id){if(!nodes.has(id))nodes.set(id,this.createElement('div'));return nodes.get(id);}},socket={readyState:1,sent:[],send(text){this.sent.push(JSON.parse(text));}};
 const warnings=[],observed={scheduled:0,cleared:0,wrongReceiver:0,animationCalls:0,scheduleFailureAt,animationFailure};
 const makeElement=doc.createElement.bind(doc);doc.createElement=tag=>{const node=makeElement(tag);const animate=node.animate.bind(node);node.animate=(...args)=>{observed.animationCalls++;if(observed.animationFailure)throw Error('Animation backend unavailable');return animate(...args);};return node;};
 const source=fs.readFileSync(new URL('../Client/app/app.js',import.meta.url),'utf8');const context=vm.createContext({Node:Element,document:doc,window:{},BattleFX:class extends BattleFX{constructor(){super({...time,reducedMotion:()=>false});}},GameAudio:class{setBattle(){}ui(){}},WebSocket:{OPEN:1},setTimeout:time.setTimer,clearTimeout:time.clearTimer,console:{...console,warn:(...args)=>warnings.push(args)},__clock:time,__observed:observed,planBattleEvents});
 if(browserTimers){
  vm.runInContext(`
   globalThis.setTimeout=function(fn,delay){'use strict';if(this!==undefined&&this!==globalThis){__observed.wrongReceiver++;throw new TypeError('Illegal invocation');}__observed.scheduled++;if(__observed.scheduled===1)__observed.openedAtFirstTimer=document.getElementById('battle-dialog').open;if(__observed.scheduled===__observed.scheduleFailureAt)throw Error('Timer backend unavailable');return __clock.setTimer(fn,delay);};
   globalThis.clearTimeout=function(id){'use strict';if(this!==undefined&&this!==globalThis){__observed.wrongReceiver++;throw new TypeError('Illegal invocation');}__observed.cleared++;return __clock.clearTimer(id);};
  `,context);
  vm.runInContext(fxSource.replace(/^import .*?;\n/gm,'').replace('export class BattleFX','class BattleFX')+'\nglobalThis.BattleFX=BattleFX;',context);
 }
 vm.runInContext(source.replace(/^import .*?;\n/gm,'').replace(/boot\(\);\s*$/,`globalThis.api={renderBattle,battleAction,handle,get battle(){return activeBattle;},seed(values){({content,state,session,ws,activeBattle}=values);},resetBattlePresentation};`),context);
 const mon={uid:'a',species:'fr_1',name:'Bulbasaur',hp:20,maxHp:30,level:5,moves:[{id:33,pp:10}]},battle={id:'b',kind:'wild',turn:1,seconds:30,you:mon,opponent:{...mon,uid:'b'},party:[mon],log:['A battle begins.'],usable:[0],opponentName:'Wild Pokémon',audio:{revision:1,events:entryEvents}};
 context.api.seed({content:{species:{fr_1:{front:'f.png',back:'b.png'}},moves:{33:{name:'Tackle',type:0,pp:35}},items:{}},state:{items:{}},session:{id:1,username:'Trainer'},ws:socket,activeBattle:battle});context.api.renderBattle();return{api:context.api,socket,battle,time,observed,warnings,dialog:doc.getElementById('battle-dialog'),root:doc.getElementById('battle-content')};
}
test('real action handler blocks double submits, preserves server waiting and unlocks after rejection',()=>{const h=appHarness();h.api.battleAction('attack',{slot:0});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);h.api.handle({type:'battle',battle:{...h.battle,waiting:true}});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);h.api.handle({type:'battle',battle:{...h.battle,audio:{revision:2,events:[]}}});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,2);h.api.handle({type:'error',message:'Action rejected.'});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,3);});
test('real renderer retains stage on duplicate snapshots while effects play and cancels stale revisions',()=>{const h=appHarness();h.api.handle({type:'battle',battle:{...h.battle,audio:{revision:2,events:[move('a')]}}});const stage=h.root.querySelector('.battle-stage');h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,0);h.api.handle({type:'battle',battle:{...h.battle,waiting:true,audio:{revision:2,events:[move('a')]}}});assert.equal(h.root.querySelector('.battle-stage'),stage);h.time.tick(1200);assert.notEqual(h.root.querySelector('.battle-stage'),stage);h.api.handle({type:'battle',battle:h.battle});assert.equal(h.api.battle.audio.revision,2);});
test('socket send failure leaves actions available and sends no fabricated command',()=>{const h=appHarness();h.socket.send=()=>{throw Error('closed');};h.api.battleAction('attack',{slot:0});assert.equal(h.root.querySelector('.battle-choice-panel').disabled,false);});
test('completed faint pose is cancelled before replacement sendout animation',()=>{const f=fixture();f.play([{id:'f',cue:'faint',side:'opponent'},{id:'s',cue:'sendout',side:'opponent',species:'fr_4'}]);f.time.tick(0);const faint=f.stage.querySelector('.enemy').animations[0];faint.onfinish();f.time.tick(180);assert.equal(faint.cancelled,true);});


// Mirrors Battle.__init__: entry always contains battle_start and both sendouts.
const entryEvents=()=>[
 {id:'entry:0',cue:'battle_start',kind:'wild'},
 {id:'entry:1',cue:'sendout',side:'opponent',species:'fr_1'},
 {id:'entry:2',cue:'sendout',side:'you',species:'fr_1'},
];
test('native-receiver timer defaults show the very first battle and both sendouts',()=>{
 const h=appHarness({browserTimers:true,entryEvents:entryEvents()});
 assert.equal(h.dialog.open,true);assert.equal(h.warnings.length,0);assert.equal(h.observed.wrongReceiver,0);
 assert.equal(h.root.querySelector('.battle-choice-panel').disabled,true);assert.equal(h.observed.openedAtFirstTimer,true);
 const stage=h.root.querySelector('.battle-stage');assert.equal(h.time.size,4);
 h.time.tick(300);assert.equal(stage.querySelector('.enemy').animations.length,1);assert.equal(stage.querySelector('.you').animations.length,1);
 h.time.tick(1000);assert.equal(h.dialog.open,true);assert.equal(h.root.querySelector('.battle-choice-panel').disabled,false);assert.equal(h.time.size,0);
 h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);assert.equal(h.observed.wrongReceiver,0);
});
test('default clear timer receives the browser global and cancels an interrupted entry',()=>{
 const h=appHarness({browserTimers:true,entryEvents:entryEvents()});
 h.time.tick(0);const enemyAnimation=h.root.querySelector('.enemy').animations[0];
 h.api.resetBattlePresentation();assert.equal(h.time.size,0);assert.equal(enemyAnimation.cancelled,true);assert.ok(h.observed.cleared>=2);assert.equal(h.observed.wrongReceiver,0);
 h.time.tick(20000);assert.equal(h.warnings.length,0);
});
test('partly scheduled entry failure keeps battle usable and cancels already queued effects',()=>{
 const h=appHarness({browserTimers:true,entryEvents:entryEvents(),scheduleFailureAt:2});
 assert.equal(h.dialog.open,true);assert.equal(h.warnings.length,1);assert.equal(h.time.size,0);
 assert.equal(h.root.querySelector('.battle-choice-panel').disabled,false);
 assert.equal(h.observed.animationCalls,0);
 for(let i=0;i<3;i++)h.api.handle({type:'battle',battle:h.battle});
 h.time.tick(20000);assert.equal(h.observed.scheduled,2);assert.equal(h.warnings.length,1);assert.equal(h.observed.animationCalls,0);
 h.api.battleAction('attack',{slot:0});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);
});
test('asynchronous sendout failure releases controls without replaying failed snapshots',()=>{
 const h=appHarness({browserTimers:true,entryEvents:entryEvents(),animationFailure:true});
 assert.equal(h.dialog.open,true);assert.equal(h.root.querySelector('.battle-choice-panel').disabled,true);
 h.time.tick(0);assert.equal(h.dialog.open,true);assert.equal(h.warnings.length,1);assert.equal(h.time.size,0);
 assert.equal(h.root.querySelector('.battle-choice-panel').disabled,false);assert.equal(h.observed.animationCalls,1);
 assert.equal(h.root.querySelector('.battle-sprite.you').getAttribute('src'),'assets/b.png');
 assert.equal(h.root.querySelector('.battle-sprite.enemy').getAttribute('src'),'assets/f.png');
 for(let i=0;i<3;i++)h.api.handle({type:'battle',battle:h.battle});
 h.time.tick(20000);assert.equal(h.observed.animationCalls,1);assert.equal(h.warnings.length,1);assert.equal(h.time.size,0);
 h.api.battleAction('attack',{slot:0});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);
});
test('animation fallback still obeys server waiting and cannot enable a second submitted action',()=>{
 const h=appHarness({browserTimers:true,entryEvents:entryEvents(),animationFailure:true});h.time.tick(0);
 h.api.handle({type:'battle',battle:{...h.battle,waiting:true}});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,0);
 h.api.handle({type:'battle',battle:{...h.battle,waiting:false,audio:{revision:2,events:[]}}});h.api.battleAction('attack',{slot:0});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);
 assert.equal(h.dialog.open,true);assert.equal(h.warnings.length,1);
});

test('duplicate snapshots after animation failure preserve the submitted-action lock until a new revision',()=>{
 const h=appHarness({browserTimers:true,entryEvents:entryEvents(),animationFailure:true});h.time.tick(0);
 h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,1);
 assert.equal(h.root.querySelector('.battle-choice-panel').disabled,true);assert.equal(h.time.size,1);
 for(let i=0;i<3;i++){
  h.api.handle({type:'battle',battle:h.battle});h.api.battleAction('attack',{slot:0});
  assert.equal(h.root.querySelector('.battle-choice-panel').disabled,true);assert.equal(h.socket.sent.length,1);
 }
 assert.equal(h.time.size,1);assert.equal(h.observed.animationCalls,1);assert.equal(h.warnings.length,1);
 h.api.handle({type:'battle',battle:{...h.battle,turn:2,audio:{revision:2,events:[move('resolved')]}}});
 assert.equal(h.root.querySelector('.battle-choice-panel').disabled,false);assert.equal(h.time.size,0);
 h.api.battleAction('attack',{slot:0});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,2);
 h.api.handle({type:'battle',battle:h.battle});h.api.battleAction('attack',{slot:0});assert.equal(h.socket.sent.length,2);
 assert.equal(h.dialog.open,true);assert.equal(h.observed.animationCalls,1);assert.equal(h.warnings.length,1);
});
