import * as varietyPresentation from '../Client/app/varieties.js';
/** Actual app registration and owner-session lifecycle using DOM/socket adapters.
 * Run: node --test Tests/check_registration.mjs
 * These exercise the shipped handlers, not a duplicate registration algorithm.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=fs.readFileSync(new URL('../Client/app/app.js',import.meta.url),'utf8');
class Element {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.events=new Map();this.attributes={};this.style={};this.value='';this.textContent='';this.disabled=false;this.open=false;this.classes=new Set();this.classList={add:k=>this.classes.add(k),remove:k=>this.classes.delete(k),contains:k=>this.classes.has(k),toggle:(k,on)=>on??!this.classes.has(k)?this.classes.add(k):this.classes.delete(k)};}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;}
 setAttribute(k,v){this.attributes[k]=String(v);} get firstChild(){return this.children[0];}
 addEventListener(k,fn){if(!this.events.has(k))this.events.set(k,[]);this.events.get(k).push(fn);}
 dispatch(k,event={}){return (this.events.get(k)||[]).map(fn=>fn({target:this,currentTarget:this,preventDefault(){},...event}));}
 close(){this.open=false;} showModal(){this.open=true;} remove(){} focus(){} blur(){} closest(){return null;}
}
class Socket {
 static OPEN=1;static CLOSING=2;static CLOSED=3;static instances=[];
 constructor(){this.readyState=1;this.sent=[];this.events=new Map();Socket.instances.push(this);}
 addEventListener(k,fn){if(!this.events.has(k))this.events.set(k,[]);this.events.get(k).push(fn);}
 send(data){this.sent.push(JSON.parse(data));} close(){this.readyState=2;}
 emit(k,packet){for(const fn of this.events.get(k)||[])fn(packet===undefined?{}:{data:JSON.stringify(packet)});}
}
const names={fr_1:'Bulbasaur',fr_4:'Charmander',fr_7:'Squirtle',fr_152:'Chikorita',fr_155:'Cyndaquil',fr_158:'Totodile'};
class Clock {
 constructor(){this.now=0;this.next=0;this.timers=new Map();}
 set=(fn,delay)=>{const id=++this.next;this.timers.set(id,{fn,at:this.now+delay});return id;};
 clear=id=>this.timers.delete(id);
 tick(ms){const end=this.now+ms;for(;;){const next=[...this.timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;this.timers.delete(next[0]);this.now=next[1].at;next[1].fn();}this.now=end;}
}
function harness(){
 const nodes=new Map(),byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
 const document=new Element();Object.assign(document,{getElementById:byId,createElement:t=>new Element(t),createTextNode:t=>Object.assign(new Element('#text'),{textContent:t}),activeElement:null});
 const renderer={setCutTrees(){},objectVisible(){return true;},players:new Map(),active:false,resize(){},scene(){},entity(e){this.lastEntity=e;},loadMap:async()=>true};
 const content={pack:'registration-test-pack',starters:Object.keys(names),species:Object.fromEntries(Object.entries(names).map(([key,name])=>[key,{name,front:key+'.png'}])),items:{}};
 const config={endpoint:'ws://localhost/world',host:'localhost',port:7777,tls:false};
 const audio=new Proxy({settings:{}},{get:(target,k)=>k in target?target[k]:()=>{}});
 const clock=new Clock();
 const context=vm.createContext({...varietyPresentation,Node:Element,document,window:new Element(),GameAudio:class{constructor(){return audio;}},WorldRenderer:class{},mountAudioControls(){},WebSocket:Socket,setInterval:()=>0,setTimeout:clock.set,clearTimeout:clock.clear,performance:{now:()=>clock.now},console});
 const script=source.replace(/^import .*?;\n/gm,'').replace(/boot\(\);\s*$/,`globalThis.api={authenticate,setMode,starterChoices,handle,connect,logout,setupInput,get state(){return state;},get own(){return own;},get session(){return session;},get starter(){return starter;},get mode(){return mode;},get busy(){return loggingIn;},seed(values){({content,config,renderer}=values);}};`);
 vm.runInContext(script,context,{filename:'app.js'});context.api.seed({content,config,renderer});
 byId('home').value='Kanto';byId('appearance').value='0';byId('username').value='Akumavenom';byId('password').value='test-password-123';
 context.api.starterChoices();context.api.setupInput();context.api.setMode('register');
 const choose=key=>byId('starters').children[content.starters.indexOf(key)].dispatch('click');
 const region=value=>{byId('home').value=value;byId('home').dispatch('change');};
 return {app:context.api,byId,choose,region,renderer,content,clock,document};
}
const submit=h=>h.app.authenticate({preventDefault(){}});
const hello=socket=>socket.emit('message',{type:'hello',world:'Registration world',online:0,pack:'registration-test-pack'});
const joined=(id,name)=>({type:'joined',id,username:name,world:'Registration world',online:2,cap:1000,motd:'Welcome',alphaAtlas:true,alphaSurf:true});

test('every explicit starter survives changing either region, including Charmander then Johto',()=>{
 const h=harness();for(const key of Object.keys(names)){h.choose(key);for(const region of ['Johto','Kanto','Johto']){h.region(region);assert.equal(h.app.starter,key,`${names[key]} changed when selecting ${region}`);assert.equal(h.byId('starters').children[h.content.starters.indexOf(key)].attributes['aria-pressed'],'true');}}
});

test('independent Akumavenom and Spidermight forms send Chikorita and Charmander in Johto',async()=>{
 const a=harness(),b=harness();a.choose('fr_152');a.region('Johto');b.byId('username').value='Spidermight';b.choose('fr_4');b.region('Johto');
 const pa=submit(a),sa=Socket.instances.at(-1),pb=submit(b),sb=Socket.instances.at(-1);hello(sa);hello(sb);await Promise.all([pa,pb]);
 assert.deepEqual(sa.sent.map(p=>[p.username,p.home,p.starter]),[['Akumavenom','Johto','fr_152']]);assert.deepEqual(sb.sent.map(p=>[p.username,p.home,p.starter]),[['Spidermight','Johto','fr_4']]);
});

test('auth locks controls, ignores duplicate submits and snapshots choices before the connection awaits',async()=>{
 const h=harness();h.choose('fr_4');h.region('Johto');const first=submit(h),socket=Socket.instances.at(-1);await submit(h);
 for(const id of ['username','password','home','appearance','login-tab','register-tab','auth-submit'])assert.equal(h.byId(id).disabled,true,id+' should be locked');
 assert.ok(h.byId('starters').children.every(b=>b.disabled));h.app.setMode('login');h.choose('fr_152');
 // Programmatic edits bypass disabled DOM fields; the sent snapshot must still be immutable.
 h.byId('username').value='ChangedName';h.byId('password').value='changed-password';h.byId('home').value='Kanto';h.byId('appearance').value='7';
 hello(socket);assert.equal(h.byId('auth-submit').disabled,true,'hello must not unlock an outstanding authentication');await first;
 assert.equal(socket.sent.length,1);assert.deepEqual(socket.sent[0],{op:'auth',mode:'register',username:'Akumavenom',password:'test-password-123',pack:'registration-test-pack',home:'Johto',starter:'fr_4',appearance:0});
});

test('the registration summary names the selected partner and home without replacing either',()=>{
 const h=harness();h.choose('fr_4');h.region('Johto');assert.match(h.byId('registration-summary').textContent,/Charmander/);assert.match(h.byId('registration-summary').textContent,/Johto/);h.region('Kanto');assert.match(h.byId('registration-summary').textContent,/Charmander/);assert.match(h.byId('registration-summary').textContent,/Kanto/);
});

test('server auth rejection unlocks choices for a deliberate retry',async()=>{
 const h=harness(),pending=submit(h),socket=Socket.instances.at(-1);hello(socket);await pending;socket.emit('message',{type:'error',login:true,message:'That username is already registered.'});
 assert.equal(h.app.busy,false);for(const id of ['username','password','home','appearance','login-tab','register-tab','auth-submit'])assert.equal(h.byId(id).disabled,false,id);h.choose('fr_7');assert.equal(h.app.starter,'fr_7');
});

test('logout cancels a waiting authentication so its late connection cannot submit',async()=>{
 const h=harness(),pending=submit(h),socket=Socket.instances.at(-1);h.app.logout();socket.readyState=Socket.CLOSED;socket.emit('close');await pending;
 assert.equal(socket.sent.length,0);assert.equal(h.app.session,null);assert.equal(h.app.busy,false);assert.equal(h.app.mode,'login');
});

test('owner packets are ignored before joining or when the entity belongs to another trainer',()=>{
 const h=harness();h.app.handle({type:'state',money:9999,party:[],creatures:[]});assert.equal(h.app.state,null);
 h.app.handle(joined(1,'Akumavenom'));h.app.handle({type:'move',seq:1,entity:{id:2,map:'johto_3_0',x:1,y:1}});assert.equal(h.app.own,null);
 h.app.handle({type:'map',id:'johto_3_0',entity:{id:2,surf:false}});assert.equal(h.app.own,null);
});

test('private state belongs to the current account and cannot roll back to an older revision',()=>{
 const h=harness();h.app.handle(joined(1,'Akumavenom'));
 const packet={type:'state',ownerId:1,money:3000,party:[],creatures:[],items:{},revision:5};h.app.handle(packet);assert.equal(h.app.state.money,3000);
 h.app.handle({...packet,ownerId:2,money:6000,revision:6});assert.equal(h.app.state.money,3000);
 h.app.handle({...packet,money:1000,revision:4});assert.equal(h.app.state.money,3000);
 h.app.handle({...packet,money:3200,revision:6});assert.equal(h.app.state.money,3200);
 // Older compatible servers have no ownerId; the socket remains account-bound.
 const legacy={...packet,money:3300,revision:7};delete legacy.ownerId;h.app.handle(legacy);assert.equal(h.app.state.money,3300);
 h.app.handle(joined(2,'Spidermight'));assert.equal(h.app.state,null);assert.equal(h.byId('party-list').children.length,0);
 h.app.handle({...packet,ownerId:2,money:2000,revision:1});assert.equal(h.app.state.money,2000,'revision restarts with a new account');
});

test('joining a new account clears previous private state and retired socket messages cannot restore it',async()=>{
 const h=harness(),connected=h.app.connect(),old=Socket.instances.at(-1);hello(old);await connected;
 old.emit('message',joined(1,'Akumavenom'));old.emit('message',{type:'state',money:3000,party:[],creatures:[],items:{},revision:1});assert.equal(h.app.state.money,3000);
 h.app.logout();const next=h.app.connect(),fresh=Socket.instances.at(-1);hello(fresh);await next;fresh.emit('message',joined(2,'Spidermight'));assert.equal(h.app.state,null);
 old.readyState=Socket.OPEN;old.emit('message',{type:'state',money:7777,party:[],creatures:[],items:{},revision:2});old.emit('message',joined(1,'Akumavenom'));assert.equal(h.app.session.id,2);assert.equal(h.app.state,null);
});

test('default registration visibly sends Bulbasaur in Kanto',async()=>{
 const h=harness(),pending=submit(h),socket=Socket.instances.at(-1);hello(socket);await pending;
 assert.equal(h.app.starter,'fr_1');assert.equal(socket.sent[0].home,'Kanto');assert.equal(socket.sent[0].starter,'fr_1');assert.match(h.byId('registration-summary').textContent,/Bulbasaur.*Kanto/);
});

test('all twelve region and starter pairs submit exactly through the form Enter/click handler',async()=>{
 for(const region of ['Kanto','Johto'])for(const key of Object.keys(names)){
  const h=harness();h.region(region);h.choose(key);const pending=Promise.all(h.byId('auth-form').dispatch('submit',{submitter:region==='Kanto'?h.byId('auth-submit'):undefined})),socket=Socket.instances.at(-1);hello(socket);await pending;
  assert.equal(socket.sent.length,1);assert.equal(socket.sent[0].home,region);assert.equal(socket.sent[0].starter,key);assert.equal(h.app.busy,true);
 }
});

test('rapid region, appearance, mode and starter edits send only the final visible choices',async()=>{
 const h=harness();for(const key of Object.keys(names)){h.choose(key);h.region('Johto');h.app.setMode('login');h.app.setMode('register');h.region('Kanto');}h.region('Johto');h.byId('appearance').value='7';
 const pending=submit(h),socket=Socket.instances.at(-1);hello(socket);await pending;assert.equal(socket.sent[0].starter,'fr_158');assert.equal(socket.sent[0].home,'Johto');assert.equal(socket.sent[0].appearance,7);assert.equal(socket.sent[0].mode,'register');
});

test('auth rejection retires the old socket before an immediate retry with corrected choices',async()=>{
 const h=harness();h.choose('fr_4');const first=submit(h),old=Socket.instances.at(-1);hello(old);await first;
 old.emit('message',{type:'error',login:true,message:'That username is already registered.'});assert.equal(old.readyState,Socket.CLOSING);
 h.byId('username').value='Spidermight';h.choose('fr_158');h.region('Johto');const next=submit(h),fresh=Socket.instances.at(-1);assert.notEqual(fresh,old);
 old.readyState=Socket.CLOSED;old.emit('close');assert.equal(h.app.busy,true,'the old close must not unlock a new request');hello(fresh);await next;assert.equal(old.sent.length,1);assert.equal(fresh.sent[0].username,'Spidermight');assert.equal(fresh.sent[0].starter,'fr_158');assert.equal(fresh.sent[0].home,'Johto');
});

test('a missing hello times out and a retry keeps the selected starter',async()=>{
 const h=harness();h.choose('fr_155');h.region('Johto');const first=submit(h),old=Socket.instances.at(-1);h.clock.tick(12001);await first;
 assert.equal(h.app.busy,false);assert.equal(old.sent.length,0);assert.match(h.byId('auth-error').textContent,/did not respond/);const next=submit(h),fresh=Socket.instances.at(-1);hello(fresh);await next;assert.equal(fresh.sent[0].starter,'fr_155');
});

test('network failure and content mismatch never send an auth request or replace the selection',async()=>{
 for(const failure of ['network','pack']){const h=harness();h.choose('fr_7');h.region('Johto');const pending=submit(h),socket=Socket.instances.at(-1);
  if(failure==='network'){socket.emit('error');socket.readyState=Socket.CLOSED;socket.emit('close');}else socket.emit('message',{type:'hello',world:'Other world',online:0,pack:'wrong-pack'});
  await pending;assert.equal(socket.sent.length,0);assert.equal(h.app.busy,false);assert.equal(h.app.starter,'fr_7');assert.equal(h.byId('home').value,'Johto');assert.ok(h.byId('auth-error').textContent);
 }
});

test('an unresponsive auth result unlocks safely without automatically creating a second account',async()=>{
 const h=harness();h.choose('fr_4');h.region('Johto');const pending=submit(h),socket=Socket.instances.at(-1);hello(socket);await pending;h.clock.tick(45001);
 assert.equal(h.app.busy,false);assert.equal(socket.readyState,Socket.CLOSING);assert.equal(socket.sent.length,1);assert.match(h.byId('auth-error').textContent,/Log in/);assert.equal(h.app.starter,'fr_4');
 socket.emit('message',joined(1,'Akumavenom'));assert.equal(h.app.session,null,'a late response from a retired timeout socket must not join');
});

test('create, logout and login sends the same account credentials without registering it again',async()=>{
 const h=harness();h.choose('fr_4');h.region('Johto');const created=submit(h),old=Socket.instances.at(-1);hello(old);await created;old.emit('message',joined(1,'Akumavenom'));h.clock.tick(45001);assert.equal(h.app.session.id,1,'a completed login must cancel the auth timer');
 assert.equal(h.byId('password').value,'');h.app.logout();assert.equal(h.app.mode,'login');h.byId('password').value='test-password-123';const pending=submit(h),fresh=Socket.instances.at(-1);assert.notEqual(fresh,old);hello(fresh);await pending;
 assert.equal(fresh.sent[0].mode,'login');assert.equal(fresh.sent[0].username,'Akumavenom');assert.equal(fresh.sent[0].password,'test-password-123');fresh.emit('message',joined(1,'Akumavenom'));assert.equal(h.app.session.id,1);assert.equal(h.app.busy,false);
});

test('map loading cannot send old-map NPC interactions or blind movement to the destination map',async()=>{
 const h=harness(),connected=h.app.connect(),socket=Socket.instances.at(-1);hello(socket);await connected;socket.emit('message',joined(1,'Akumavenom'));
 socket.emit('message',{type:'move',seq:1,entity:{id:1,map:'johto_3_0',x:5,y:5,surf:false}});h.renderer.map={id:'kanto_3_0',objects:[{id:77,x:5,y:5}]};h.renderer.pendingMap={id:'johto_3_0'};
 const key=value=>{h.document.dispatch('keydown',{key:value,repeat:false});h.document.dispatch('keyup',{key:value});};key('e');key('w');assert.equal(socket.sent.length,0);
 h.renderer.pendingMap=null;key('e');key('w');assert.equal(socket.sent.length,0,'mismatched old map stays inert even if pending flag is gone');
 h.renderer.map={id:'johto_3_0',objects:[{id:99,x:5,y:5}]};key('e');key('w');assert.deepEqual(socket.sent.map(p=>p.op),['npc','move']);assert.equal(socket.sent[0].npc,99);assert.equal(socket.sent[1].direction,'up');
});
