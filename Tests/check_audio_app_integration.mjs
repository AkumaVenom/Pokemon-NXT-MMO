/** Execute the actual app functions against a small DOM/transport adapter.
 * Covers async lifecycle and mixer wiring; this is not a browser rendering test.
 * Run: node --test Tests/check_audio_app_integration.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const appSource = fs.readFileSync(new URL('../Client/app/app.js', import.meta.url), 'utf8');
const controlsSource = fs.readFileSync(new URL('../Client/app/audio_controls.js', import.meta.url), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

class Element {
 constructor(tag='div') { this.tagName=tag.toUpperCase();this.children=[];this.events=new Map();this.attributes={};this.style={};this.value='';this.textContent='';this.open=false;this.disabled=false;this.scrollTop=0;this.scrollHeight=0;this.clientHeight=100;this.classes=new Set(['hidden']);this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),contains:x=>this.classes.has(x),toggle:(x,on)=>{if(on??!this.classes.has(x))this.classes.add(x);else this.classes.delete(x);}}; }
 append(...items) { this.children.push(...items); }
 replaceChildren(...items) { this.children=[...items]; }
 get firstChild() { return this.children[0]; }
 setAttribute(k,v) { this.attributes[k]=v; }
 addEventListener(k,fn) { if(!this.events.has(k))this.events.set(k,[]);this.events.get(k).push(fn); }
 dispatch(k,event={}) { for(const fn of this.events.get(k)||[])fn({target:this,currentTarget:this,...event}); }
 showModal() { this.open=true; }
 close() { this.open=false; }
 focus() {}
 blur() {}
 remove() {}
 closest() { return null; }
}
class Audio {
 constructor() { this.calls=[];this.settings={master:.8,music:.65,effects:.8,cries:.85,muted:false,muteUnfocused:true,lowHp:true,chat:true}; }
 setScene(value) { this.calls.push(['scene',value]); }
 setBattle(value) { this.calls.push(['battle',value]); }
 setMap(id,surf) { this.surf=surf;this.calls.push(['map',id,surf]); }
 ui(value) { this.calls.push(['ui',value]); }
 inspectPokemon(value) { this.calls.push(['cry',value]); }
 movement(value) { this.calls.push(['movement',value]); }
 handleEvents(value) { for(const e of value.events||[])if(e.cue==='surf')this.surf=e.enabled;this.calls.push(['events',value]); }
 unlock() { this.calls.push(['unlock']);return Promise.resolve(true); }
 setSettings(value) { this.settings={...this.settings,...value};this.calls.push(['settings',value]); }
 subscribe(fn) { this.listener=fn;fn({status:'locked',settings:this.settings}); }
 init(value) { this.initial=value;return Promise.resolve(); }
}
class Socket {
 static OPEN=1;static CLOSED=3;static CLOSING=2;static instances=[];
 constructor() { this.readyState=1;this.events=new Map();this.sent=[];Socket.instances.push(this); }
 addEventListener(k,fn) { if(!this.events.has(k))this.events.set(k,[]);this.events.get(k).push(fn); }
 send(value) { this.sent.push(value); }
 close() { this.readyState=2; }
 emit(k,packet) { for(const fn of this.events.get(k)||[])fn(packet===undefined?{}:{data:JSON.stringify(packet)}); }
}
function descendants(node) { return [node,...node.children.filter(n=>n instanceof Element).flatMap(descendants)]; }
function text(node) { return node.textContent+node.children.map(n=>n instanceof Element?text(n):String(n)).join(''); }
function harness() {
 const nodes=new Map(),byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
 const document=new Element();Object.assign(document,{getElementById:byId,createElement:tag=>new Element(tag),createTextNode:value=>Object.assign(new Element('#text'),{textContent:String(value)}),activeElement:null,querySelector:()=>new Element()});
 const renderer={players:new Map(),active:true,resize(){},entity(){},scene(){},loadMap:()=>Promise.resolve(true)};
 const config={nonce:'unit+nonce',host:'localhost',port:7777,tls:false,endpoint:'ws://localhost/world'};
 const mon={uid:'test-mon',species:'fr_1',name:'Bulbasaur',level:5,hp:20,maxHp:20,status:'',shiny:false,moves:[{id:33,pp:20}],stats:[20,10,10,10,10,10],exp:100,nextExp:200,levelExp:100};
 const content={species:{fr_1:{front:'test.png',back:'back.png',types:[12],name:'Bulbasaur'}},moves:{33:{name:'Tackle',type:0,pp:20}},items:{},starters:['fr_1']};
 const mixer={opened:0,saves:[],open(){this.opened++;},setPersistence(value){this.saves.push(value);}};
 const context=vm.createContext({Node:Element,GameAudio:Audio,WebSocket:Socket,WorldRenderer:class{},mountAudioControls:()=>mixer,document,window:new Element(),performance:{now:()=>0},innerWidth:1600,innerHeight:1000,setInterval:()=>0,setTimeout:()=>0,clearTimeout(){},fetch:async()=>({ok:true,json:async()=>({persisted:true})}),console});
 const source=appSource.replace(/^import .*?;\n/gm,'').replace(/boot\(\);\s*$/,`globalThis.appTest={handle,loadMap,logout,connect,persistAudioSettings,renderBattle,setupInput,boot,get audio(){return audio;},get session(){return session;},seed(values){({config,content,renderer,session,state,audioControls}=values);}};`);
 vm.runInContext(source,context,{filename:'app.js'});
 context.appTest.seed({config,content,renderer,session:{id:1,username:'UnitTrainer'},state:{items:{},party:[mon.uid],creatures:[mon]},audioControls:mixer});
 return {app:context.appTest,context,byId,renderer,config,mon,mixer,document};
}
const mapPacket=()=>({type:'map',id:'kanto_3_0',name:'Pallet Town',region:'Kanto',transition:'travel',entity:{id:1,map:'kanto_3_0',x:10,y:10,surf:false}});

test('confirmed map context is applied before loading and a later Surf event is not overwritten',async()=>{
 const h=harness();let done;h.renderer.loadMap=()=>new Promise(resolve=>done=resolve);
 const loading=h.app.loadMap(mapPacket());assert.equal(h.app.audio.calls.at(-1)[0],'map');
 h.app.handle({type:'audio',id:'test:1',events:[{id:'test:1:0',cue:'surf',enabled:true}]});
 done(true);await loading;assert.equal(h.app.audio.surf,true);assert.equal(h.app.audio.calls.filter(c=>c[0]==='map').length,1);
});

test('late map completion after logout cannot play a stale warp',async()=>{
 const h=harness();let done;h.renderer.loadMap=()=>new Promise(resolve=>done=resolve);
 const loading=h.app.loadMap(mapPacket());h.app.logout();const count=h.app.audio.calls.length;done(true);await loading;
 assert.equal(h.app.audio.calls.length,count);assert.equal(h.app.session,null);assert.equal(h.byId('audio-dialog').open,false);
});

test('late failed map load after logout cannot display a stale error',async()=>{
 const h=harness();let fail;h.renderer.loadMap=()=>new Promise((_,reject)=>fail=reject);
 const loading=h.app.loadMap(mapPacket());h.app.logout();const count=h.byId('toasts').children.length;fail(Error('Old map unavailable'));await loading;
 assert.equal(h.byId('toasts').children.length,count);
});

test('messages from a closing socket cannot rejoin a logged-out session',async()=>{
 const h=harness();const connected=h.app.connect(),socket=Socket.instances.at(-1);socket.emit('hello');
 socket.emit('message',{type:'hello',world:'Unit world',online:1});await connected;
 h.app.logout();const count=h.app.audio.calls.length;socket.emit('message',{type:'joined',id:1,username:'StaleTrainer'});
 assert.equal(h.app.session,null);assert.equal(h.app.audio.calls.length,count);
});

test('disconnect closes top-layer dialogs so the reconnect overlay is reachable',async()=>{
 const h=harness();const connected=h.app.connect(),socket=Socket.instances.at(-1);socket.emit('message',{type:'hello',world:'Unit world',online:1});await connected;
 for(const id of ['audio-dialog','battle-dialog','modal'])h.byId(id).showModal();
 socket.readyState=Socket.CLOSED;socket.emit('close');
 for(const id of ['audio-dialog','battle-dialog','modal'])assert.equal(h.byId(id).open,false);
 assert.equal(h.byId('disconnect-overlay').classList.contains('hidden'),false);assert.equal(h.app.audio.calls.at(-1)[1],'disconnected');
});

test('battle has its own accessible Sound action while the topbar is inert',()=>{
 const h=harness();h.app.handle({type:'battle',battle:{id:'battle-1',kind:'wild',turn:2,seconds:45,opponentName:'Wild Bulbasaur',you:h.mon,opponent:h.mon,ended:true,result:'escaped',log:[],party:[h.mon]}});
 const button=descendants(h.byId('battle-content')).find(n=>n.tagName==='BUTTON'&&text(n)==='Sound');
 assert.ok(button);button.dispatch('click');assert.equal(h.mixer.opened,1);assert.equal(h.byId('battle-dialog').open,true);
});

test('audio preferences post full latest settings to the launcher with its token',async()=>{
 const h=harness(),requests=[];h.context.fetch=(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}));
 const first=h.app.persistAudioSettings({...h.app.audio.settings,music:.25});
 h.app.persistAudioSettings({...h.app.audio.settings,music:.4});h.app.persistAudioSettings({...h.app.audio.settings,music:.7});
 assert.equal(requests.length,1);assert.equal(requests[0].url,'/audio-settings?token=unit%2Bnonce');assert.equal(requests[0].options.method,'POST');
 requests[0].resolve({ok:true,json:async()=>({persisted:true})});await flush();assert.equal(requests.length,2);
 const posted=JSON.parse(requests[1].options.body);assert.equal(posted.music,.7);assert.equal(Object.keys(posted).length,8);assert.equal(requests[1].options.headers['Content-Type'],'application/json');
 requests[1].resolve({ok:true,json:async()=>({persisted:true})});await first;assert.equal(h.mixer.saves.at(-1),true);
});

test('mixer gesture handlers unlock synchronously and opening remains public for battle UI',()=>{
 const h=harness();vm.runInContext(controlsSource.replace('export function mountAudioControls','function mountActualAudioControls')+'\nglobalThis.mountActualAudioControls=mountActualAudioControls;',h.context);
 const controls=h.context.mountActualAudioControls(h.app.audio);h.document.dispatch('pointerdown');assert.equal(h.app.audio.calls.at(-1)[0],'unlock');
 controls.open();assert.equal(h.byId('audio-dialog').open,true);h.byId('audio-dialog').dispatch('cancel',{preventDefault(){},stopPropagation(){}});assert.equal(h.byId('audio-dialog').open,false);
 const slider=h.byId('audio-music');slider.value='37';slider.dispatch('input');assert.equal(h.app.audio.settings.music,.37);
});
