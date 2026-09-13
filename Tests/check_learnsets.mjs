/** The shipped inspect / Move Reminder handlers with isolated DOM/socket adapters.
 * Run: node --test Tests/check_learnsets.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=fs.readFileSync(new URL('../Client/app/app.js',import.meta.url),'utf8');
const world=JSON.parse(fs.readFileSync(new URL('../Server/data/world.json',import.meta.url),'utf8'));
class Element{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.events=new Map();this.attributes={};this.style={};this.value='';this.textContent='';this.disabled=false;this.open=false;this.scrollTop=0;this.classes=new Set();this.classList={add:k=>this.classes.add(k),remove:k=>this.classes.delete(k),contains:k=>this.classes.has(k),toggle:(k,on)=>on??!this.classes.has(k)?this.classes.add(k):this.classes.delete(k)};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(k,v){this.attributes[k]=String(v);}getAttribute(k){return this.attributes[k]??null;}
 addEventListener(k,fn){if(!this.events.has(k))this.events.set(k,[]);this.events.get(k).push(fn);}dispatch(k){for(const fn of this.events.get(k)||[])fn({target:this,currentTarget:this,preventDefault(){}});}
 close(){this.open=false;}showModal(){this.open=true;}remove(){}focus(){}querySelector(){return null;}get firstChild(){return this.children[0];}
}
const flatten=node=>[node,...node.children.flatMap(flatten)];
const words=node=>node.textContent+node.children.map(words).join('');
function harness(){
 const nodes=new Map(),byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
 const document=new Element();Object.assign(document,{getElementById:byId,createElement:t=>new Element(t),createTextNode:t=>Object.assign(new Element('#text'),{textContent:t}),activeElement:null});
 const content={species:structuredClone(world.species),moves:structuredClone(world.moves),items:{}};
 const learnset=world.species.fr_155.learnset.map(([level,move])=>({level,move,name:world.moves[move].name}));
 const mon={uid:'cynda',species:'fr_155',name:'Cyndaquil',shiny:false,level:10,exp:1000,levelExp:1000,nextExp:1331,hp:30,maxHp:30,nature:'Hardy',originalTrainer:'Akumavenom',status:'',stats:[30,25,25,25,25,25],moves:[{id:33,pp:30},{id:43,pp:30}],pendingLearn:[],evolutions:[],levelUpMoves:learnset,relearnMoves:learnset.filter(m=>m.level<=10&&![33,43].includes(m.move))};
 const state={type:'state',ownerId:1,revision:1,money:3000,party:[mon.uid],creatures:[mon],items:{},adventure:{unlocks:[]}};
 const session={id:1,username:'Akumavenom'},own={id:1,map:'johto_3_0',x:5,y:5};
 const socket={readyState:1,sent:[],send(data){this.sent.push(JSON.parse(data));},close(){this.readyState=2;}};
 const audio=new Proxy({settings:{}},{get:(target,k)=>k in target?target[k]:()=>{}}),renderer={setCutTrees(){},objectVisible(){return true;},players:new Map(),resetSession(){},resize(){},scene(){},loadMap:async()=>true};
 const context=vm.createContext({Node:Element,document,window:new Element(),GameAudio:class{constructor(){return audio;}},WorldRenderer:class{},mountAudioControls(){},WebSocket:{OPEN:1},setInterval(){},setTimeout(){},clearTimeout(){},performance:{now:()=>0},console});
 vm.runInContext(source.replace(/^import .*?;\n/gm,'').replace(/boot\(\);\s*$/,`globalThis.api={showPokemon,showMoveReminder,handle,closeModal,loadMap,get state(){return state;},get modal(){return modalKind;},seed(values){({content,state,session,own,ws,renderer}=values);},busy(kind){trade=kind==='trade'?{}:null;activeBattle=kind==='battle'?{}:null;invite=kind==='invite'?{}:null;},changeSession(id){session=id===null?null:{id};}};`),context,{filename:'app.js'});
 context.api.seed({content,state,session,own,ws:socket,renderer});
 const find=label=>flatten(byId('modal-body')).find(n=>n.tagName==='BUTTON'&&words(n)===label);
 return {app:context.api,byId,content,mon,state,session,own,socket,find,text:()=>words(byId('modal-body')),rows:()=>flatten(byId('modal-body')).filter(n=>n.tagName==='TR').map(words),click(label){const b=find(label);assert.ok(b,'Missing button: '+label);b.dispatch('click');return b;}};
}
function openReminder(h){h.app.showPokemon(h.mon);h.click('Open Move Reminder');}
function fullMoves(h){h.mon.moves=[{id:33,pp:30},{id:43,pp:30},{id:98,pp:20},{id:52,pp:10}];}
function replacement(h){fullMoves(h);openReminder(h);h.click('Smokescreen · Lv. 6');h.click('Replace Leer · Slot 2');return h.find('Confirm: remember Smokescreen');}

test('level-10 Cyndaquil displays native Ember level 12 and labels learned / missed / upcoming moves',()=>{
 const h=harness();h.app.showPokemon(h.mon);assert.match(h.text(),/Next move: Ember at Lv\. 12/);assert.ok(h.rows().includes('Lv. 1TackleKnown'));assert.ok(h.rows().includes('Lv. 6SmokescreenMove Reminder'));assert.ok(h.rows().includes('Lv. 12EmberUpcoming'));assert.equal(h.socket.sent.length,0);
 openReminder(h);assert.ok(h.find('Smokescreen · Lv. 6'));assert.equal(h.find('Ember · Lv. 12'),undefined);
});
test('pending choices remain visible before the learnset and lock the reminder',()=>{
 const h=harness();h.mon.level=12;h.mon.pendingLearn=[{move:52,name:'Ember',level:12}];h.app.showPokemon(h.mon);assert.ok(h.text().indexOf('wants to learn Ember')<h.text().indexOf('LEVEL-UP MOVES'));assert.ok(h.rows().includes('Lv. 12EmberPending choice'));assert.equal(h.find('Open Move Reminder').disabled,true);h.click('Open Move Reminder');assert.equal(h.app.modal,'pokemon');h.click('Learn Ember');assert.deepEqual(h.socket.sent,[{op:'pokemon.learn',uid:'cynda',move:52,slot:2}]);
});
test('remembering into an empty slot sends one explicit command and leaves local moves untouched',()=>{
 const h=harness(),before=structuredClone(h.mon.moves);openReminder(h);h.click('Smokescreen · Lv. 6');assert.equal(h.socket.sent.length,0);const use=h.click('Use empty slot 3');use.dispatch('click');h.click('Back to Pokémon');assert.deepEqual(h.socket.sent,[{op:'pokemon.remember',uid:'cynda',move:108,slot:2}]);assert.deepEqual(h.mon.moves,before);assert.match(h.text(),/Waiting for the world/);
});
test('replacement requires a separate confirmation naming both moves; cancel preserves the set',()=>{
 const h=harness();const confirm=replacement(h);assert.equal(h.socket.sent.length,0);assert.match(h.text(),/Forget Leer and remember Smokescreen\?/);h.click('Keep Leer');confirm.dispatch('click');assert.equal(h.socket.sent.length,0,'retired confirmation must be inert');h.click('Replace Leer · Slot 2');h.click('Confirm: remember Smokescreen');assert.deepEqual(h.socket.sent,[{op:'pokemon.remember',uid:'cynda',move:108,slot:1}]);assert.equal(h.mon.moves[1].id,43);
});
test('reminder callbacks reject another owner, a renewed same-account session, and logout',()=>{
 for(const id of [2,1,null]){const h=harness(),confirm=replacement(h);h.app.changeSession(id);confirm.dispatch('click');assert.equal(h.socket.sent.length,0);}
});
test('reminder callbacks cannot submit during battle, trade, invitation, or disconnect',()=>{
 for(const kind of ['battle','trade','invite','disconnect']){const h=harness(),confirm=replacement(h);if(kind==='disconnect')h.socket.readyState=2;else h.app.busy(kind);confirm.dispatch('click');assert.equal(h.socket.sent.length,0,kind);}
});
test('changed owner state clears a selected replacement and invalidates old callbacks',()=>{
 const h=harness(),confirm=replacement(h),next=structuredClone(h.state);next.revision++;next.creatures[0].moves[1]={id:172,pp:10};h.app.handle(next);assert.equal(h.app.modal,'reminder');assert.match(h.text(),/1\. Choose a move/);assert.doesNotMatch(h.text(),/Forget Leer/);confirm.dispatch('click');assert.equal(h.socket.sent.length,0);
});
test('a new pending choice interrupts the reminder and returns to that growth choice',()=>{
 const h=harness(),confirm=replacement(h),next=structuredClone(h.state);next.revision++;next.creatures[0].pendingLearn=[{move:129,name:'Swift',level:36}];h.app.handle(next);assert.equal(h.app.modal,'pokemon');assert.match(h.text(),/wants to learn Swift/);confirm.dispatch('click');assert.equal(h.socket.sent.length,0);
});
test('losing ownership or changing maps retires the reminder',async()=>{
 const h=harness(),confirm=replacement(h),next=structuredClone(h.state);next.revision++;next.creatures=[];next.party=[];h.app.handle(next);assert.equal(h.app.modal,'');confirm.dispatch('click');assert.equal(h.socket.sent.length,0);
 const other=harness(),old=replacement(other);await other.app.loadMap({id:'kanto_3_0',entity:{...other.own,map:'kanto_3_0'},name:'Pallet Town',region:'Kanto'});old.dispatch('click');assert.equal(other.app.modal,'');assert.equal(other.socket.sent.length,0);
});
test('the authoritative success response refreshes known status without applying client-side mutations',()=>{
 const h=harness();openReminder(h);h.click('Smokescreen · Lv. 6');h.click('Use empty slot 3');const next=structuredClone(h.state);next.revision++;next.creatures[0].moves.push({id:108,pp:20});next.creatures[0].relearnMoves=[];h.app.handle(next);assert.match(h.text(),/No forgotten level-up moves/);h.click('Back to Pokémon');assert.ok(h.rows().includes('Lv. 6SmokescreenKnown'));assert.equal(h.find('Open Move Reminder').disabled,true);
});
test('sparse Sigma variant move IDs above the original move table pass through unchanged',()=>{
 for(const id of [512,1024+512]){const h=harness();h.mon.species='sg_256';h.mon.name='Charizardx';h.content.moves[id]={name:'Native Variant Move',pp:15};h.mon.levelUpMoves=[{move:id,name:'Native Variant Move',level:7}];h.mon.relearnMoves=structuredClone(h.mon.levelUpMoves);openReminder(h);h.click('Native Variant Move · Lv. 7');h.click('Use empty slot 3');assert.deepEqual(h.socket.sent,[{op:'pokemon.remember',uid:'cynda',move:id,slot:2}]);}
});
test('legacy state without learnset details and a native empty learnset remain inspectable',()=>{
 const h=harness();delete h.mon.levelUpMoves;delete h.mon.relearnMoves;h.app.showPokemon(h.mon);assert.match(h.text(),/Move details are unavailable/);assert.equal(h.find('Open Move Reminder'),undefined);h.mon.levelUpMoves=[];h.mon.relearnMoves=[];h.app.showPokemon(h.mon);assert.match(h.text(),/This form has no level-up moves/);assert.equal(h.find('Open Move Reminder').disabled,true);
});
