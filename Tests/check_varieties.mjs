/** Real presentation helpers and WAAPI keyframes; no browser pixels are claimed. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import {VARIETY_KEYS,varietyKey,varietyDefinition,frontSprite,pokemonName,followerPokemon,eventPokemon,drawFollowerSparkles} from '../Client/app/varieties.js';
import {BattleFX} from '../Client/app/battle_fx.js';
const content=JSON.parse(fs.readFileSync(new URL('../Client/app/assets/world/client.json',import.meta.url),'utf8'));

test('all 251 core Pokémon resolve each uploaded front and never a back',()=>{
 for(let i=1;i<=251;i++)for(const variety of VARIETY_KEYS){const mon={species:'fr_'+i,variety};const src=frontSprite(content,mon);assert.equal(src,'assets/'+content.species[mon.species].varieties[variety].front);assert.doesNotMatch(src,/back/i);}
});
test('canonical variety takes priority; only genuine legacy booleans migrate',()=>{
 assert.equal(varietyKey({shiny:true}),'shiny');assert.equal(varietyKey({shiny:'true'}),'normal');assert.equal(varietyKey({variety:'shadow',shiny:true}),'shadow');assert.equal(varietyKey({variety:'normal',shiny:true}),'normal');assert.equal(varietyKey({variety:['shiny'],shiny:true}),'normal');assert.equal(varietyKey(null),'normal');
});
test('variety labels distinguish all six identities without changing species',()=>{
 for(const variety of VARIETY_KEYS){const mon={species:'fr_25',variety};assert.equal(pokemonName(content,mon),variety==='normal'?'Pikachu':variety[0].toUpperCase()+variety.slice(1)+' Pikachu');assert.equal(mon.species,'fr_25');}
});
test('extra species use native shiny when supplied art is absent, never back art',()=>{
 const species=Object.keys(content.species).find(id=>content.species[id].varieties.shiny.source==='native');assert.ok(species);assert.equal(frontSprite(content,{species,variety:'shiny'}),'assets/'+content.species[species].shiny);
 const absent=Object.keys(content.species).find(id=>!content.species[id].varieties.ancient);assert.equal(frontSprite(content,{species:absent,variety:'ancient'}),'assets/'+content.species[absent].front);
});
test('all five follower colours are distinct valid published colours',()=>{
 const colors=VARIETY_KEYS.slice(1).map(variety=>varietyDefinition(content,{variety}).color);assert.equal(new Set(colors).size,5);for(const c of colors)assert.match(c,/^#[0-9A-F]{6}$/i);
 const bad={varietyPolicy:{definitions:{shadow:{color:'red;position:fixed'}}}};assert.match(varietyDefinition(bad,{variety:'shadow'}).color,/^#[0-9A-F]{6}$/i);
});
test('peer follower presentation reads replicated identity, not local owner party',()=>{
 assert.deepEqual(followerPokemon({follower:'fr_25',followerVariety:'shadow',shiny:false}),{species:'fr_25',variety:'shadow'});
 assert.deepEqual(followerPokemon({follower:'fr_25',shiny:true}),{species:'fr_25',shiny:true});
});
test('same-species outgoing and incoming event UUIDs retain their own variety',()=>{
 const ancient={species:'fr_25',uid:'a',variety:'ancient'},shadow={species:'fr_25',uid:'b',variety:'shadow'},snapshot={you:shadow,party:[ancient,shadow],opponent:{...ancient,uid:'e',variety:'mystic'}};
 const out=eventPokemon(snapshot,{species:'fr_25',uid:'a',variety:'ancient'},'you');const incoming=eventPokemon(snapshot,{species:'fr_25',uid:'b',variety:'shadow'},'you');assert.equal(out.variety,'ancient');assert.equal(incoming.variety,'shadow');assert.equal(frontSprite(content,out),'assets/pokemon/varieties/ancient/fr_25.png');
 const enemy=eventPokemon(snapshot,{species:'fr_25',uid:'old-enemy',variety:'metallic'},'enemy');assert.equal(enemy.variety,'metallic');assert.equal(enemy.uid,'old-enemy');
});
test('event-time identity cannot inherit cached incoming name or unrelated shiny',()=>{
 const snapshot={you:{species:'fr_1',uid:'a',name:'Bulbasaur',variety:'shiny'},party:[]};const shown=eventPokemon(snapshot,{species:'fr_25',variety:'mystic',uid:'old'},'you');assert.equal(pokemonName(content,shown),'Mystic Pikachu');assert.equal(shown.shiny,false);assert.equal(shown.uid,'old');
});
function canvas(){return{globalAlpha:1,fillStyle:'#123456',calls:[],saved:[],save(){this.saved.push([this.globalAlpha,this.fillStyle]);},restore(){[this.globalAlpha,this.fillStyle]=this.saved.pop();},beginPath(){this.calls.push(['path',this.fillStyle,this.globalAlpha]);},moveTo(...v){this.calls.push(['move',...v]);},lineTo(...v){this.calls.push(['line',...v]);},closePath(){},fill(){this.calls.push(['fill']);}};}
test('normal follower has no effect; variants retain exact native icon paths',()=>{
 const ctx=canvas();assert.equal(drawFollowerSparkles(ctx,content,{id:1,follower:'fr_25',followerVariety:'normal'},100,100,3,500),0);assert.deepEqual(ctx.calls,[]);assert.doesNotMatch(content.species.fr_25.icon,/varieties/);
});
test('each visible rare follower draws four bounded stars with correct colour',()=>{
 for(const variety of VARIETY_KEYS.slice(1)){const ctx=canvas();assert.equal(drawFollowerSparkles(ctx,content,{id:2,follower:'fr_25',followerVariety:variety},100,100,3,500),4);const paths=ctx.calls.filter(c=>c[0]==='path');assert.equal(paths.length,4);assert.ok(paths.every(c=>c[1]===content.varietyPolicy.definitions[variety].color));assert.ok(paths.every(c=>c[2]>=.22&&c[2]<=1));assert.equal(ctx.globalAlpha,1);assert.equal(ctx.fillStyle,'#123456');}
});
test('sparkles animate deterministically, do not accumulate and honour reduced motion',()=>{
 const e={id:6,follower:'fr_25',followerVariety:'ancient'},a=canvas(),b=canvas(),same=canvas();drawFollowerSparkles(a,content,e,100,100,3,100);drawFollowerSparkles(b,content,e,100,100,3,400);drawFollowerSparkles(same,content,e,100,100,3,100);assert.notDeepEqual(a.calls,b.calls);assert.deepEqual(a.calls,same.calls);
 const r1=canvas(),r2=canvas();assert.equal(drawFollowerSparkles(r1,content,e,100,100,3,100,true),2);drawFollowerSparkles(r2,content,e,100,100,3,20000,true);assert.deepEqual(r1.calls,r2.calls);
 for(let i=0;i<1000;i++){const ctx=canvas();assert.equal(drawFollowerSparkles(ctx,content,e,100,100,3,i),4);assert.equal(ctx.calls.filter(c=>c[0]==='fill').length,4);}
});
test('missing followers or invalid scales cannot draw effects',()=>{
 for(const scale of [0,-1,NaN,Infinity]){const ctx=canvas();assert.equal(drawFollowerSparkles(ctx,content,{follower:'fr_25',followerVariety:'shadow'},0,0,scale,0),0);assert.equal(ctx.calls.length,0);}
 assert.equal(drawFollowerSparkles(canvas(),content,{follower:null,followerVariety:'shadow'},0,0,1,0),0);
});
function spriteNode(className){return{className,calls:[],animate(frames,options){this.calls.push({frames,options});return{cancel(){}};}};}
test('every player sprite animation keyframe retains horizontal mirror and lunge direction',()=>{
 const fx=new BattleFX({reducedMotion:()=>false}),you=spriteNode('battle-sprite you'),original=[{opacity:0},{transform:'translate(54px,-22px)',filter:'brightness(2)'},{transform:'scale(1)',opacity:1}],copy=structuredClone(original);fx.animate(you,original,{duration:250});assert.deepEqual(original,copy);
 for(const f of you.calls[0].frames)assert.ok(f.transform.endsWith('scaleX(-1)'));
 assert.equal(you.calls[0].frames[1].transform,'translate(54px,-22px) scaleX(-1)');
});
test('opponent sprites and readable popup text are never mirrored',()=>{
 const fx=new BattleFX({reducedMotion:()=>false}),frames=[{transform:'translateX(5px)'},{opacity:0}];for(const classes of ['battle-sprite enemy','battle-float you']){const node=spriteNode(classes);fx.animate(node,frames,{duration:200});assert.deepEqual(node.calls[0].frames,frames);}
});
test('reduced-motion bypass still has permanent player CSS facing without back art',()=>{
 const fx=new BattleFX({reducedMotion:()=>true}),node=spriteNode('battle-sprite you');fx.animate(node,[{opacity:1}],{duration:200});assert.equal(node.calls.length,0);const css=fs.readFileSync(new URL('../Client/app/styles.css',import.meta.url),'utf8');assert.match(css,/\.battle-sprite\.you\s*\{\s*transform:scaleX\(-1\)/);
 const app=fs.readFileSync(new URL('../Client/app/app.js',import.meta.url),'utf8');assert.doesNotMatch(app,/\.backShiny|\.back\b/);
});
