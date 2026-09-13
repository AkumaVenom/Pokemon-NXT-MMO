/** Exercise the shipped adventure UI handlers with isolated DOM and socket adapters.
 * Run: node --test Tests/check_adventure_ui.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=fs.readFileSync(new URL('../Client/app/app.js',import.meta.url),'utf8');
const html=fs.readFileSync(new URL('../Client/app/index.html',import.meta.url),'utf8');
class Element{
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.events=new Map();this.attributes={};this.style={};this.value='';this.textContent='';this.disabled=false;this.open=false;this.scrollTop=0;this.classes=new Set();this.classList={add:k=>this.classes.add(k),remove:k=>this.classes.delete(k),contains:k=>this.classes.has(k),toggle:(k,on)=>on??!this.classes.has(k)?this.classes.add(k):this.classes.delete(k)};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(k,v){this.attributes[k]=String(v);}getAttribute(k){return this.attributes[k]??null;}
 addEventListener(k,fn){if(!this.events.has(k))this.events.set(k,[]);this.events.get(k).push(fn);}dispatch(k,event={}){return (this.events.get(k)||[]).map(fn=>fn({target:this,currentTarget:this,preventDefault(){},...event}));}
 close(){this.open=false;}showModal(){this.open=true;}remove(){}focus(){}blur(){}closest(){return null;}querySelector(){return null;}
 get firstChild(){return this.children[0];}
}
const flatten=node=>[node,...node.children.flatMap(flatten)];
const text=node=>node.textContent+node.children.map(text).join('');
function harness(){
 const nodes=new Map(),byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
 const document=new Element();Object.assign(document,{getElementById:byId,createElement:t=>new Element(t),createTextNode:t=>Object.assign(new Element('#text'),{textContent:t}),activeElement:null});
 const species={fr_1:{name:'Bulbasaur',front:'bulbasaur.png',back:'bulbasaur-back.png',shiny:'bulbasaur-shiny.png',types:[12]},fr_2:{name:'Ivysaur',front:'ivysaur.png',types:[12]},fr_4:{name:'Charmander',front:'charmander.png',types:[10]},fr_152:{name:'Chikorita',front:'chikorita.png',types:[12]}};
 const content={pack:'adventure-test-pack',species,starters:['fr_1','fr_4','fr_152'],items:{potion:{name:'Potion',price:100,heal:20},leaf_stone:{name:'Leaf Stone',price:2100,evolutionStone:true}},moves:{1:{name:'Tackle',pp:35},2:{name:'Growl',pp:40},3:{name:'Vine Whip',pp:10},4:{name:'Poison Powder',pp:35},5:{name:'Razor Leaf',pp:25}},objects:{kanto:{}},maps:{},homes:{Kanto:'kanto_3_0',Johto:'johto_3_0'}};
 const mon=(uid,species='fr_1')=>({uid,species,name:content.species[species].name,shiny:false,level:16,exp:4096,levelExp:4096,nextExp:4913,hp:35,maxHp:40,nature:'Hardy',originalTrainer:'Akumavenom',status:'',stats:[40,30,30,30,30,30],moves:[{id:1,pp:30},{id:2,pp:40}],pendingLearn:[],evolutions:[]});
 const state={type:'state',ownerId:1,revision:2,money:3000,party:['a'],creatures:[mon('a'),mon('b','fr_4')],items:{potion:1},adventure:{regions:[{id:'kanto',name:'Kanto',badges:[{id:'boulder',name:'Boulder Badge',leader:'Brock',order:1,earned:true},{id:'cascade',name:'Cascade Badge',leader:'Misty',order:2,earned:false}],nextGym:{name:'Cascade Badge',leader:'Misty'}}],goals:[{id:'first',title:'First steps',description:'Visit two towns.',current:2,target:2,complete:true,claimed:false,reward:{money:500,items:{potion:2}}},{id:'later',title:'Keep exploring',description:'Visit five towns.',current:2,target:5,complete:false,claimed:false,reward:{money:100}}],trainers:{defeated:['youngster'],count:1},dex:{seen:['fr_1','fr_4'],caught:['fr_1']},visited:['kanto_3_0','kanto_3_1'],unlocks:['route_2'],pcAvailable:false}};
 const session={id:1,username:'Akumavenom',world:'Adventure world',cap:1000,alphaAtlas:true,alphaSurf:true};
 const own={id:1,map:'kanto_5_4',x:7,y:5,appearance:0};
 const socket={readyState:1,sent:[],send(data){this.sent.push(JSON.parse(data));},close(){this.readyState=2;}};
 const audioCalls=[];const audio=new Proxy({settings:{}},{get:(target,key)=>key in target?target[key]:(...args)=>audioCalls.push([key,...args])});
 const renderer={cutTrees:{},setCutTrees(cuts){this.cutTrees=cuts||{};},players:new Map(),active:true,resize(){},scene(){},entity(){},resetSession(){},loadMap:async()=>true};
 const context=vm.createContext({Node:Element,document,window:new Element(),GameAudio:class{constructor(){return audio;}},WorldRenderer:class{},mountAudioControls(){},WebSocket:{OPEN:1},setInterval(){},setTimeout(){},clearTimeout(){},performance:{now:()=>0},console});
 const script=source.replace(/^import .*?;\n/gm,'').replace(/boot\(\);\s*$/,`globalThis.api={showPokemon,showCollection,showJournal,showDex,showBag,showNpcDialog,showAtlas,canTravelTo,updateAdventureAccess,setupInput,handle,loadMap,closeModal,get state(){return state;},get modal(){return modalKind;},seed(values){({content,state,session,own,ws,renderer}=values);},busy(kind){trade=kind==='trade'?{}:null;activeBattle=kind==='battle'?{}:null;},changeOwner(){session={id:2};}};`);
 vm.runInContext(script,context,{filename:'app.js'});context.api.seed({content,state,session,own,ws:socket,renderer});
 byId('home').value='Kanto';
 return{app:context.api,byId,document,state,content,mon,own,session,renderer,socket,audioCalls,all:()=>flatten(byId('modal-body')),buttons:()=>flatten(byId('modal-body')).filter(n=>n.tagName==='BUTTON'),findButton:label=>flatten(byId('modal-body')).find(n=>n.tagName==='BUTTON'&&text(n)===label),words:()=>text(byId('modal-body'))};
}

test('there is no menu healing command; Nurse Joy requests explicit nearby NPC healing',()=>{
 const h=harness();assert.doesNotMatch(html,/heal-button|Restore party/);assert.doesNotMatch(source,/send\('heal'/);
 h.app.showNpcDialog({title:'Nurse Joy',message:'Welcome to our Pokémon Center.',npc:3,actions:['heal','pc']});
 assert.match(h.words(),/Would you like her to take care/);const heal=h.findButton('Yes, please heal my party');heal.dispatch('click');heal.dispatch('click');assert.deepEqual(h.socket.sent,[{op:'npc',npc:3,action:'heal'}]);
});
test('old Nurse Joy dialog actions are invalidated on map transition',async()=>{
 const h=harness();h.app.showNpcDialog({title:'Nurse Joy',message:'Hello',npc:3,actions:['heal']});const heal=h.findButton('Yes, please heal my party');await h.app.loadMap({id:'johto_3_0',entity:{...h.own,map:'johto_3_0'},name:'New Bark Town',region:'Johto'});heal.dispatch('click');assert.equal(h.socket.sent.length,0);assert.equal(h.app.modal,'');
});
test('party and storage transfer controls require a Pokémon Center PC',()=>{
 const h=harness();h.app.showCollection('storage');const withdraw=h.findButton('Withdraw');assert.equal(withdraw.disabled,true);withdraw.dispatch('click');assert.equal(h.socket.sent.length,0);
 h.state.adventure.pcAvailable=true;h.app.showCollection('storage');h.findButton('Withdraw').dispatch('click');assert.deepEqual(h.socket.sent,[{op:'pc',action:'withdraw',uid:'b'}]);
});
test('deposits use the PC operation, preserve at least one party member and never fake a party reorder',()=>{
 const h=harness();h.state.adventure.pcAvailable=true;h.app.showCollection('party');assert.equal(h.findButton('Deposit').disabled,true);
 h.state.party.push('b');h.app.showCollection('party');h.findButton('Deposit').dispatch('click');assert.deepEqual(h.socket.sent,[{op:'pc',action:'deposit',uid:'a'}]);
});
test('full parties cannot withdraw, and movement away closes a storage session',()=>{
 const h=harness();for(let i=0;i<5;i++){const mon=h.mon('extra'+i);h.state.creatures.push(mon);h.state.party.push(mon.uid);}h.state.adventure.pcAvailable=true;h.app.showCollection('storage');assert.equal(h.findButton('Withdraw').disabled,true);
 h.app.handle({type:'move',seq:1,entity:h.own,pcAvailable:false});assert.equal(h.app.modal,'');assert.equal(h.state.adventure.pcAvailable,false);
});
test('a foreign owner state cannot grant PC access or change the open collection',()=>{
 const h=harness();h.app.showCollection('storage');h.app.handle({...h.state,ownerId:2,revision:99,adventure:{...h.state.adventure,pcAvailable:true}});assert.equal(h.app.state.ownerId,1);assert.equal(h.findButton('Withdraw').disabled,true);
});
test('journal reflects saved badges and allows only a completed unclaimed reward',()=>{
 const h=harness();h.app.showJournal();assert.match(h.words(),/Boulder Badge/);assert.match(h.words(),/Misty/);assert.match(h.words(),/1Trainers defeated/);const claim=h.findButton('Claim reward');claim.dispatch('click');claim.dispatch('click');assert.deepEqual(h.socket.sent,[{op:'journal.claim',id:'first'}]);assert.equal(h.findButton('In progress').disabled,true);
 const saved=structuredClone(h.state);saved.revision++;saved.adventure.goals[0].claimed=true;h.app.handle(saved);assert.equal(h.findButton('Reward collected').disabled,true);
});
test('Pokédex includes only discoveries, keeps historical catches and does not reveal unseen search results',()=>{
 const h=harness();h.app.showDex();assert.match(h.words(),/Bulbasaur/);assert.match(h.words(),/Charmander/);assert.doesNotMatch(h.words(),/Ivysaur|Chikorita/);assert.deepEqual(h.all().filter(n=>n.tagName==='IMG').map(n=>n.getAttribute('alt')),['Bulbasaur','Charmander']);
 const search=h.all().find(n=>n.getAttribute('data-focus')==='dex-search');search.value='Chikorita';search.dispatch('input');assert.equal(h.all().filter(n=>n.tagName==='IMG').length,0);
 h.state.adventure.dex.caught.push('fr_152');h.app.showDex();assert.match(h.words(),/Chikorita/);assert.equal(h.state.creatures.some(m=>m.species==='fr_152'),false);
});
test('move learning explicitly sends the chosen forget slot for the first queued move only',()=>{
 const h=harness(),mon=h.state.creatures[0];mon.moves=[{id:1,pp:30},{id:2,pp:40},{id:3,pp:10},{id:4,pp:35}];mon.pendingLearn=[{move:5,name:'Razor Leaf',level:20},{move:3,name:'Vine Whip',level:21}];h.app.showPokemon(mon);h.findButton('Forget Growl').dispatch('click');assert.deepEqual(h.socket.sent,[{op:'pokemon.learn',uid:'a',move:5,slot:1}]);assert.match(h.words(),/1 more move choices/);
});
test('move learning fills a free slot or declines explicitly without replacing another move',()=>{
 const h=harness(),mon=h.state.creatures[0];mon.pendingLearn=[{move:3,name:'Vine Whip',level:7}];h.app.showPokemon(mon);h.findButton('Learn Vine Whip').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'pokemon.learn',uid:'a',move:3,slot:2});h.app.showPokemon(mon);h.findButton('Do not learn this move').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'pokemon.learn',uid:'a',move:3,slot:null});
});
test('evolution can be accepted, deferred and resumed through explicit owner commands',()=>{
 const h=harness(),mon=h.state.creatures[0];mon.evolutions=[{target:'fr_2',name:'Ivysaur',method:'level',level:16,deferred:false}];h.app.showPokemon(mon);h.findButton('Evolve into Ivysaur').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'pokemon.evolve',uid:'a',target:'fr_2'});h.app.showPokemon(mon);h.findButton('Not now').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'pokemon.evolution.defer',uid:'a',target:'fr_2'});mon.evolutions[0].deferred=true;h.app.showPokemon(mon);assert.equal(h.findButton('Evolve into Ivysaur'),undefined);h.findButton('Resume evolution').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'pokemon.evolution.resume',uid:'a',target:'fr_2'});
});
test('item evolution is disabled without the required item',()=>{
 const h=harness(),mon=h.state.creatures[0];mon.evolutions=[{target:'fr_2',name:'Ivysaur',method:'stone',item:'leaf_stone',deferred:false}];h.app.showPokemon(mon);assert.equal(h.findButton('Evolve into Ivysaur').disabled,true);h.state.items.leaf_stone=1;h.app.showPokemon(mon);assert.equal(h.findButton('Evolve into Ivysaur').disabled,false);
});
test('stale growth and journal controls cannot act for another owner or during a trade',()=>{
 const h=harness(),mon=h.state.creatures[0];mon.pendingLearn=[{move:3,name:'Vine Whip',level:7}];h.app.showPokemon(mon);const learn=h.findButton('Learn Vine Whip');h.app.changeOwner();learn.dispatch('click');assert.equal(h.socket.sent.length,0);
 const other=harness();other.app.showJournal();const claim=other.findButton('Claim reward');other.app.busy('trade');claim.dispatch('click');assert.equal(other.socket.sent.length,0);
});
test('owner state refresh updates inspected growth without replaying Pokémon cries',()=>{
 const h=harness(),mon=h.state.creatures[0];h.app.showPokemon(mon);const next=structuredClone(h.state);next.revision++;next.creatures[0].pendingLearn=[{move:3,name:'Vine Whip',level:7}];h.app.handle(next);assert.ok(h.findButton('Learn Vine Whip'));assert.equal(h.audioCalls.filter(([op])=>op==='inspectPokemon').length,1);
});
test('adventure hotkeys preserve WASD movement and use G for the Pokédex',()=>{
 const h=harness();h.app.setupInput();h.document.dispatch('keydown',{key:'g',repeat:false});assert.equal(h.app.modal,'dex');h.app.closeModal(true);h.document.dispatch('keydown',{key:'j',repeat:false});assert.equal(h.app.modal,'journal');assert.match(html,/Pokédex <kbd>G<\/kbd>/);
});

test('earned regional Surf licenses update controls without enabling the other region',()=>{
 const h=harness();h.session.alphaSurf=false;h.app.updateAdventureAccess();assert.equal(h.byId('surf-button').disabled,true);h.state.adventure.unlocks.push('surf_kanto');h.app.updateAdventureAccess();assert.equal(h.byId('surf-button').disabled,false);
 h.own.map='johto_3_0';h.app.updateAdventureAccess();assert.equal(h.byId('surf-button').disabled,true);h.own.surf=true;h.app.updateAdventureAccess();assert.equal(h.byId('surf-button').disabled,false,'Surf can always be switched off');assert.equal(h.byId('atlas-button').disabled,false,'The atlas is always readable');
});
test('Travel Pass enables only visited waypoints and starting towns while preserving explicit exploration override',()=>{
 const h=harness();h.session.alphaAtlas=false;assert.equal(h.app.canTravelTo({id:'kanto_3_0',mapType:1}),false);h.state.adventure.unlocks.push('travel_pass');assert.equal(h.app.canTravelTo({id:'kanto_3_1',mapType:2}),true);assert.equal(h.app.canTravelTo({id:'johto_3_0',mapType:1}),true);assert.equal(h.app.canTravelTo({id:'johto_3_20',mapType:3}),false);h.session.alphaAtlas=true;assert.equal(h.app.canTravelTo({id:'johto_3_20',mapType:3}),true);assert.equal(h.app.canTravelTo({id:'johto_3_20',playable:false}),false);
});
test('bag distinguishes evolution items and enables buying only at a nearby Mart',()=>{
 const h=harness();h.session.alphaAtlas=false;h.renderer.map={id:h.own.map,objects:[]};h.app.showBag();assert.equal(h.findButton('Buy 1').disabled,true);assert.match(h.words(),/Evolution item/);h.findButton('Use on lead').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'use',item:'potion',uid:'a'});
 h.renderer.map.objects=[{graphics:68,x:h.own.x+1,y:h.own.y}];h.app.showBag();assert.equal(h.findButton('Buy 1').disabled,false);h.findButton('Buy 1').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'buy',item:'potion',quantity:1});
});

test('Sigma Link Cable and Fairy Dust use their actual names and generic item keys',()=>{
 for(const [key,name] of [['linkcable','Link Cable'],['fairydust','Fairy Dust']]){
  const h=harness(),mon=h.state.creatures[0];h.content.items[key]={name,price:2100,evolutionStone:true};mon.evolutions=[{target:'fr_2',name:'Ivysaur',method:'stone',item:key,deferred:false}];h.app.showPokemon(mon);assert.match(h.words(),new RegExp('Uses one '+name));assert.equal(h.findButton('Evolve into Ivysaur').disabled,true);
  h.state.items[key]=1;h.app.showPokemon(mon);h.findButton('Evolve into Ivysaur').dispatch('click');assert.deepEqual(h.socket.sent.at(-1),{op:'pokemon.evolve',uid:'a',target:'fr_2'});
  h.app.showBag();assert.match(h.words(),new RegExp(name));assert.match(h.words(),/Evolution item/);
 }
});
test('PC deposit keeps one healthy partner instead of leaving only fainted party members',()=>{
 const h=harness();h.state.adventure.pcAvailable=true;h.state.party.push('b');h.state.creatures[1].hp=0;h.app.showCollection('party');const deposits=h.buttons().filter(b=>text(b)==='Deposit');assert.equal(deposits[0].disabled,true);assert.equal(deposits[1].disabled,false);
});

test('earned atlas travel locks visited interiors while keeping their browse cards and admin override',()=>{
 const h=harness();h.session.alphaAtlas=false;h.state.adventure.unlocks.push('travel_pass');h.state.adventure.visited.push('kanto_5_4');
 const inside={id:'kanto_5_4',mapType:8,name:'Pokémon Center',region:'Kanto'},outside={id:'kanto_3_1',mapType:2,name:'Viridian City',region:'Kanto'};h.content.maps={[inside.id]:inside,[outside.id]:outside};
 assert.equal(h.app.canTravelTo(inside),false);assert.equal(h.app.canTravelTo(outside),true);h.app.showAtlas();const filter=h.all().find(n=>n.getAttribute('aria-label')==='Atlas region');filter.value='all';filter.dispatch('change');
 const card=h.buttons().find(n=>text(n).includes('Pokémon Center'));assert.ok(card,'Interior remains in atlas browse');assert.equal(card.disabled,true);assert.match(text(card),/Enter through its door/);assert.equal(h.byId('modal').open,true);assert.match(h.words(),/outdoor waypoints/);
 h.session.alphaAtlas=true;assert.equal(h.app.canTravelTo(inside),true);
});

test('locked Cut is visible, disabled and sends no command',()=>{
 const h=harness();h.app.showNpcDialog({title:'Small HM tree',message:'Defeat Misty for the Cascade Badge.',npc:95,map:h.own.map,actions:['cut'],disabledActions:['cut'],fieldMove:{unlocked:false,badgeName:'Cascade Badge'}});
 const cut=h.findButton('Cut tree — locked');assert.ok(cut);assert.equal(cut.disabled,true);assert.equal(cut.getAttribute('aria-disabled'),'true');cut.dispatch('click');assert.equal(h.socket.sent.length,0);assert.match(h.words(),/saved for your character only/);
});
test('unlocked Cut sends exactly one map-bound command and never removes a tree optimistically',()=>{
 const h=harness();h.app.showNpcDialog({title:'Small HM tree',message:'Cut this tree.',npc:95,map:h.own.map,actions:['cut'],disabledActions:[],fieldMove:{unlocked:true}});
 const cut=h.findButton('Cut tree');assert.equal(cut.disabled,false);cut.dispatch('click');cut.dispatch('click');assert.deepEqual(h.socket.sent,[{op:'npc',npc:95,map:h.own.map,action:'cut'}]);assert.deepEqual(h.renderer.cutTrees,{});
 const next=structuredClone(h.state);next.revision++;next.adventure.cutTrees={[h.own.map]:[95]};h.app.handle(next);assert.deepEqual(h.renderer.cutTrees,next.adventure.cutTrees);
});
test('foreign and stale snapshots cannot hide an owner tree',()=>{
 const h=harness();h.app.handle({...h.state,ownerId:2,revision:90,adventure:{...h.state.adventure,cutTrees:{[h.own.map]:[95]}}});assert.deepEqual(h.renderer.cutTrees,{});
 h.app.handle({...h.state,revision:0,adventure:{...h.state.adventure,cutTrees:{[h.own.map]:[95]}}});assert.deepEqual(h.renderer.cutTrees,{});
});
test('delayed tree menus and old Cut controls cannot act after a map change',async()=>{
 const h=harness(),oldMap=h.own.map;
 h.app.showNpcDialog({title:'Small HM tree',message:'Cut.',npc:95,map:oldMap,actions:['cut'],fieldMove:{unlocked:true}});const cut=h.findButton('Cut tree');
 await h.app.loadMap({id:'johto_3_0',entity:{...h.own,map:'johto_3_0'},name:'New Bark Town',region:'Johto'});cut.dispatch('click');assert.equal(h.socket.sent.length,0);
 h.app.showNpcDialog({title:'Small HM tree',message:'Old map.',npc:95,map:oldMap,actions:['cut'],fieldMove:{unlocked:true}});assert.equal(h.app.modal,'');
});
test('journal shows independent Cut badge requirements for both regions',()=>{
 const h=harness();h.state.adventure.fieldMoves=[{region:'kanto',unlocked:true,leader:'Misty',city:'Cerulean City',badgeName:'Cascade Badge'},{region:'johto',unlocked:false,leader:'Bugsy',city:'Azalea Town',badgeName:'Hive Badge'}];h.app.showJournal();assert.match(h.words(),/CUT UNLOCKED/);assert.match(h.words(),/CUT LOCKED/);assert.match(h.words(),/Defeat Bugsy in Azalea Town/);assert.match(h.words(),/does not replace a partner/);
});
