import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import os from 'node:os';
import {fileURLToPath,pathToFileURL} from 'node:url';

// Optional real-browser regression. Browser execution was unavailable during
// the 0.3.3 release build; this file was syntax-checked, not browser QA passed.
const moduleLocation=process.env.NXT_PLAYWRIGHT_MODULE;
const {chromium}=await import(moduleLocation?(path.isAbsolute(moduleLocation)?pathToFileURL(moduleLocation).href:moduleLocation):'playwright');

const rootArgument=process.argv.slice(2).find(value=>!value.startsWith('--'));
const sourceRoot=rootArgument?path.resolve(rootArgument):fileURLToPath(new URL('..',import.meta.url));
const expectBroken=process.argv.includes('--expect-broken');
const app=path.join(sourceRoot,'Client/app');
const output=fs.mkdtempSync(path.join(os.tmpdir(),'nxt-battle-browser-'));
const api=`
window.__battleTest={
 seed(data){content=data;session={id:1,username:'Akuma'};state={items:{}};ws={readyState:1,sent:[],send(text){this.sent.push(JSON.parse(text));}};audio.setBattle=b=>{window.__audioBattle=b?.id;};audio.ui=()=>{};$('boot').classList.add('hidden');$('login').classList.add('hidden');$('game').classList.remove('hidden');},
 handle, resetBattlePresentation,
 summary(){return {dialogOpen:$('battle-dialog').open,busy:battleFX?.busy,sent:ws.sent,revision:activeBattle?.audio?.revision};},
 failTimer(){const timer=battleFX.setTimer;battleFX.setTimer=()=>{throw new Error('Injected timer creation failure');};window.__restoreTimer=()=>{battleFX.setTimer=timer;};},
 restoreTimer(){window.__restoreTimer?.();}
};`;
const server=http.createServer((request,response)=>{
 const pathname=new URL(request.url,'http://localhost').pathname;
 const filename=path.resolve(app,'.'+(pathname==='/'?'/index.html':pathname));
 if(!filename.startsWith(app+path.sep)){response.writeHead(403).end();return;}
 try {
  let body=fs.readFileSync(filename);
  if(pathname==='/app.js'){
   const original=body.toString();assert.match(original,/\nboot\(\);\s*$/);
   body=Buffer.from(original.replace(/\nboot\(\);\s*$/,api));
  }
  const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'}[path.extname(filename)]||'application/octet-stream';
  response.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'}).end(body);
 }catch {response.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,...(process.env.NXT_BROWSER_PATH?{executablePath:process.env.NXT_BROWSER_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage']});
const page=await browser.newPage({viewport:{width:1365,height:900}}),errors=[];
page.on('pageerror',error=>errors.push(error.stack));
const content=JSON.parse(fs.readFileSync(path.join(app,'assets/world/client.json')));
const cyndaquil={uid:'your-mon',species:'fr_155',name:'Cyndaquil',level:12,hp:34,maxHp:34,status:'',moves:[{id:33,pp:35},{id:52,pp:25}]};
const enemy={uid:'enemy-mon',species:'fr_1',name:'Bulbasaur',level:10,hp:28,maxHp:28,status:'',moves:[{id:33,pp:35}]};
const battle={id:'native-browser-battle',kind:'wild',turn:1,seconds:30,you:cyndaquil,opponent:enemy,party:[cyndaquil],log:['A wild Bulbasaur appeared!'],usable:[0,1],opponentName:'Wild Pokémon',audio:{revision:0,events:[{id:'start',cue:'battle_start'},{id:'send-you',cue:'sendout',side:'you',species:'fr_155'},{id:'send-enemy',cue:'sendout',side:'opponent',species:'fr_1'}]}};
try{
 await page.goto('http://127.0.0.1:'+server.address().port);
 await page.waitForFunction(()=>!!window.__battleTest);
 await page.evaluate(data=>window.__battleTest.seed(data),content);
 const first=await page.evaluate(b=>{try{window.__battleTest.handle({type:'battle',battle:b});return window.__battleTest.summary();}catch(e){return {error:e.message,stack:e.stack,...window.__battleTest.summary()};}},battle);
 if(expectBroken){
  assert.match(first.error,/Illegal invocation/);assert.equal(first.dialogOpen,false);
  console.log(JSON.stringify({result:'REPRODUCED',browser:browser.version(),first},null,2));
 }else{
  assert.equal(first.error,undefined);assert.equal(first.dialogOpen,true);
  await page.waitForFunction(()=>!window.__battleTest.summary().busy);
  const ember=page.locator('.move-button',{hasText:'Ember'});
  assert.equal(await ember.isEnabled(),true);
  await ember.click();
  await page.evaluate(()=>document.querySelectorAll('.move-button')[1].click());
  assert.equal((await page.evaluate(()=>window.__battleTest.summary())).sent.length,1);
  const next={...battle,turn:2,you:{...cyndaquil,hp:29},opponent:{...enemy,hp:10},log:['Cyndaquil used Ember!','It is super effective!','Bulbasaur used Tackle!'],audio:{revision:1,events:[
   {id:'move-you',cue:'move',side:'you',species:'fr_155',move:52},
   {id:'hit-enemy',cue:'hit',side:'opponent',species:'fr_1',damage:18,effectiveness:2},
   {id:'move-enemy',cue:'move',side:'opponent',species:'fr_1',move:33},
   {id:'hit-you',cue:'hit',side:'you',species:'fr_155',damage:5,effectiveness:1}
  ]}};
  await page.evaluate(b=>window.__battleTest.handle({type:'battle',battle:b}),next);
  await page.waitForFunction(()=>document.querySelector('.battle-float.enemy')?.textContent.includes('Super effective!'));
  assert.match(await page.locator('.battle-float.enemy').textContent(),/18/);
  await page.screenshot({path:path.join(output,'battle-hit-browser.png')});
  await page.waitForFunction(()=>[...document.querySelectorAll('.battle-float.you')].some(n=>n.textContent.includes('−5')));
  await page.waitForFunction(()=>!window.__battleTest.summary().busy);
  assert.equal(await page.locator('.move-button').first().isEnabled(),true);
  await page.locator('.move-button').first().click();
  assert.equal((await page.evaluate(()=>window.__battleTest.summary())).sent.length,2);
  await page.evaluate(()=>window.__battleTest.failTimer());
  await page.evaluate(b=>window.__battleTest.handle({type:'battle',battle:b}),{...battle,audio:{revision:2,events:[{id:'timer-fault',cue:'sendout',side:'you',species:'fr_155'}]}});
  assert.equal(await page.locator('#battle-dialog').evaluate(n=>n.open),true);
  assert.equal(await page.locator('.move-button').first().isEnabled(),true);
  await page.evaluate(()=>{window.__battleTest.restoreTimer();window.__battleTest.resetBattlePresentation();window.__originalAnimate=Element.prototype.animate;Element.prototype.animate=function(){throw new Error('Injected asynchronous animation failure');};});
  await page.evaluate(b=>window.__battleTest.handle({type:'battle',battle:b}),{...battle,audio:{revision:3,events:[{id:'animation-fault',cue:'sendout',side:'you',species:'fr_155'}]}});
  await page.waitForFunction(()=>!window.__battleTest.summary().busy);
  assert.equal(await page.locator('#battle-dialog').evaluate(n=>n.open),true);
  assert.equal(await page.locator('.move-button').first().isEnabled(),true);
  await page.evaluate(()=>{Element.prototype.animate=window.__originalAnimate;window.__battleTest.resetBattlePresentation();});
  await page.evaluate(b=>window.__battleTest.handle({type:'battle',battle:b}),{...battle,ended:true,result:'won',audio:{revision:4,events:[]}});
  await page.getByRole('button',{name:'Return to adventure'}).click();
  assert.equal(await page.locator('#battle-dialog').evaluate(n=>n.open),false);
  assert.equal((await page.evaluate(()=>window.__battleTest.summary())).busy,false);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',browser:browser.version(),artifacts:output,checks:['native revision-zero sendout opens dialog','animation queue unlocks actions','rapid duplicate click sends one attack','player hit shows authoritative damage and effectiveness','opponent attack shows damage','next turn accepts action','timer creation failure retains playable dialog','asynchronous animation failure retains playable dialog','return to adventure cleans effects and closes dialog'],errors},null,2));
 }
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
