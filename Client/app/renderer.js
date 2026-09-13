/** Integer-scaled ROM assets, device-pixel-ratio canvas, interpolated replicated entities. */
export class WorldRenderer {
 constructor(canvas,content,onPick){
  this.canvas=canvas;this.ctx=canvas.getContext('2d',{alpha:false});this.content=content;this.onPick=onPick;this.images=new Map();this.players=new Map();this.cutTrees=new Map();this.map=null;this.pendingMap=null;this.selfId=null;this.scale=3;this.manualScale=0;this.hits=[];this.generation=0;this.cam={x:0,y:0};this.frames=0;this.lastFps=performance.now();this.fps=0;this.active=false;
  this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas);
  canvas.addEventListener('click',e=>{const r=canvas.getBoundingClientRect();const x=e.clientX-r.left,y=e.clientY-r.top;const candidates=this.hits.filter(h=>x>=h.x&&x<=h.x+h.w&&y>=h.y&&y<=h.y+h.h);const hit=candidates.find(h=>h.kind==='player'&&h.id!==this.selfId)||candidates.find(h=>h.kind==='npc');if(hit)this.onPick(hit,e.clientX,e.clientY);});
  canvas.addEventListener('mousemove',e=>{const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;canvas.style.cursor=this.hits.some(h=>x>=h.x&&x<=h.x+h.w&&y>=h.y&&y<=h.y+h.h&&!(h.kind==='player'&&h.id===this.selfId))?'pointer':'default';});
  requestAnimationFrame(t=>this.frame(t));
 }
 resize(){const r=this.canvas.getBoundingClientRect();if(!r.width||!r.height)return;this.width=r.width;this.height=r.height;this.dpr=Math.min(window.devicePixelRatio||1,4);this.rootFont=parseFloat(getComputedStyle(document.documentElement).fontSize);this.canvas.width=Math.round(r.width*this.dpr);this.canvas.height=Math.round(r.height*this.dpr);this.scale=this.manualScale||Math.max(2,Math.min(6,Math.floor(r.height/195)));}
 setScale(scale){this.manualScale=Math.max(1,Math.min(8,scale));this.resize();}
 image(path){if(!path)return null;if(!this.images.has(path)){const image=new Image();image.src='assets/'+path;this.images.set(path,image);}const img=this.images.get(path);return img.complete&&img.naturalWidth?img:null;}
 resetSession(){++this.generation;this.pendingMap=null;this.players.clear();this.cutTrees.clear();this.map=null;this.selfId=null;this.hits=[];this.active=false;}
 // Owner snapshots replace this private set; shared map JSON is never mutated.
 setCutTrees(cuts){
  const next=new Map();
  if(cuts&&typeof cuts==='object'&&!Array.isArray(cuts))for(const [map,ids] of Object.entries(cuts)){
   if(Array.isArray(ids))next.set(map,new Set(ids.filter(id=>Number.isSafeInteger(id)&&id>=0&&id<=255)));
  }
  this.cutTrees=next;
  this.hits=this.hits.filter(hit=>hit.kind!=='npc'||!this.map||this.objectVisible(this.map.objects.find(n=>n.id===hit.id),hit.map||this.map.id));
 }
 objectVisible(obj,mapId=this.map?.id){return !!obj&&!(obj.graphics===95&&this.cutTrees.get(mapId)?.has(obj.id));}
 async loadMap(id,initialEntity=null){
  const serial=++this.generation,pending={id,entities:new Map()};this.pendingMap=pending;this.players.clear();this.hits=[];
  if(initialEntity?.map===id)pending.entities.set(initialEntity.id,{...initialEntity});
  try{
   const response=await fetch('assets/world/maps/'+encodeURIComponent(id)+'.json');if(!response.ok)throw Error('Map data is missing: '+id);
   const map=await response.json();if(serial!==this.generation)return false;if(map.id!==id)throw Error('Map data does not match: '+id);
   if(this.map){for(const path of [this.map.image,this.map.ground,this.map.overlay]){if(path&&![map.image,map.ground,map.overlay].includes(path))this.images.delete(path);}}
   this.map=map;this.pendingMap=null;this.players.clear();for(const e of pending.entities.values())this.entity(e,true);
   this.image(map.ground||map.image);this.image(map.overlay);for(const obj of map.objects)this.image(this.content.objects[id.split('_')[0]]?.[obj.graphics]?.image);return true;
  }catch(error){if(serial!==this.generation)return false;this.pendingMap=null;this.map=null;this.players.clear();this.hits=[];throw error;}
 }
 entity(e,immediate=false){
  // Scene deltas can arrive before local map assets. Fold them until this generation is ready.
  if(this.pendingMap){if(e.map===this.pendingMap.id)this.pendingMap.entities.set(e.id,{...e});return;}
  if(!this.map||e.map!==this.map.id)return;const old=this.players.get(e.id);const now=performance.now();const current=old?this.position(old,now):{x:e.x,y:e.y,fx:e.fx,fy:e.fy};this.players.set(e.id,{...e,fromX:immediate?e.x:current.x,fromY:immediate?e.y:current.y,fromFX:immediate?e.fx:current.fx,fromFY:immediate?e.fy:current.fy,at:now,moving:!immediate&&!!old&&(old.x!==e.x||old.y!==e.y)});this.image(this.content.objects.kanto[e.appearance]?.image);if(e.follower)this.image(this.content.species[e.follower]?.icon);
 }
 scene(packet){const target=this.pendingMap?this.pendingMap.id:this.map?.id;if(packet.map!==target)return;for(const e of packet.players)this.entity(e);const players=this.pendingMap?this.pendingMap.entities:this.players;for(const id of packet.gone)players.delete(id);}
 position(e,now){const t=Math.min(1,Math.max(0,(now-e.at)/140));return{x:e.fromX+(e.x-e.fromX)*t,y:e.fromY+(e.y-e.fromY)*t,fx:e.fromFX+(e.fx-e.fromFX)*t,fy:e.fromFY+(e.fy-e.fromFY)*t};}
 frame(now){requestAnimationFrame(t=>this.frame(t));if(!this.active||!this.map||!this.width)return;this.frames++;if(now-this.lastFps>=1000){this.fps=Math.round(this.frames*1000/(now-this.lastFps));this.frames=0;this.lastFps=now;}
  const ctx=this.ctx,w=this.width,h=this.height,s=this.scale,tile=16*s;ctx.setTransform(this.dpr,0,0,this.dpr,0,0);ctx.imageSmoothingEnabled=false;ctx.fillStyle='#22443f';ctx.fillRect(0,0,w,h);
  const own=this.players.get(this.selfId),pos=own?this.position(own,now):{x:this.map.spawn[0],y:this.map.spawn[1]};const mw=this.map.width*tile,mh=this.map.height*tile;
  const ox=Math.round(mw<w?(w-mw)/2:Math.max(w-mw,Math.min(0,w/2-(pos.x+.5)*tile)));const oy=Math.round(mh<h?(h-mh)/2:Math.max(h-mh,Math.min(0,h/2-(pos.y+.5)*tile)));this.cam={x:ox,y:oy};this.hits=[];
  const ground=this.image(this.map.ground||this.map.image);if(ground)ctx.drawImage(ground,ox,oy,mw,mh);
  const drawables=[];const tag=this.map.id.split('_')[0];for(const n of this.map.objects){if(!this.objectVisible(n))continue;const spec=this.content.objects[tag]?.[n.graphics];if(spec)drawables.push({kind:'npc',n,spec,x:n.x,y:n.y});}
  for(const e of this.players.values()){const p=this.position(e,now);if(e.follower)drawables.push({kind:'follower',e,x:p.fx,y:p.fy});drawables.push({kind:'player',e,x:p.x,y:p.y});}
  drawables.sort((a,b)=>a.y-b.y||(a.kind==='follower'?-1:1));
  for(const d of drawables){const cx=ox+(d.x+.5)*tile,feet=oy+(d.y+1)*tile;if(cx<-tile||cx>w+tile||feet<-tile||feet>h+tile*2)continue;
   if(d.kind==='follower'){
    const sp=this.content.species[d.e.follower],img=this.image(sp?.icon);if(!img)continue;const frame=Math.floor(now/260)%2;const size=32*s*.8;ctx.fillStyle='#15332d40';ctx.beginPath();ctx.ellipse(cx,feet-2*s,6*s,2*s,0,0,Math.PI*2);ctx.fill();ctx.drawImage(img,Math.min(frame*32,img.naturalWidth-32),0,32,32,Math.round(cx-size/2),Math.round(feet-size+2*s),Math.round(size),Math.round(size));continue;
   }
   const spec=d.kind==='npc'?d.spec:this.content.objects.kanto[d.e.appearance]||this.content.objects.kanto['0'];const img=this.image(spec.image);if(!img)continue;
   const moving=d.kind==='player'&&d.e.moving&&now-d.e.at<175;const direction=d.kind==='player'?d.e.direction:'down';let frame=direction==='up'?1:direction==='left'||direction==='right'?2:0;if(moving)frame=(direction==='up'?5:direction==='left'||direction==='right'?7:3)+(Math.floor(now/120)%2);frame=Math.min(frame,spec.frames-1);
   const sw=spec.width*s,sh=spec.height*s,x=Math.round(cx-sw/2),y=Math.round(feet-sh);ctx.fillStyle='#11261f45';ctx.beginPath();ctx.ellipse(cx,feet-2*s,6*s,2*s,0,0,Math.PI*2);ctx.fill();
   ctx.save();if(direction==='right'){ctx.translate(Math.round(cx),0);ctx.scale(-1,1);ctx.drawImage(img,frame*spec.width,0,spec.width,spec.height,-Math.round(sw/2),y,sw,sh);}else ctx.drawImage(img,frame*spec.width,0,spec.width,spec.height,x,y,sw,sh);ctx.restore();
   this.hits.push({kind:d.kind,id:d.kind==='npc'?d.n.id:d.e.id,map:this.map.id,x,y,w:sw,h:sh});
   if(d.kind==='npc'&&d.n.trainerType){ctx.font='bold '+Math.max(12,s*5)+'px Segoe UI';ctx.textAlign='center';ctx.fillStyle='#fff2b0';ctx.strokeStyle='#263126';ctx.lineWidth=3;ctx.strokeText('!',cx,y-3);ctx.fillText('!',cx,y-3);}
  }
  const overlay=this.image(this.map.overlay);if(overlay)ctx.drawImage(overlay,ox,oy,mw,mh);
  // Nameplates are a UI layer, never blurred along with world pixels.
  const rootFont=this.rootFont;const fs=Math.max(11,rootFont*.76);ctx.font='600 '+fs+'px "Segoe UI",sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
  for(const e of this.players.values()){const p=this.position(e,now);const spec=this.content.objects.kanto[e.appearance]||this.content.objects.kanto['0'];const x=ox+(p.x+.5)*tile,y=oy+(p.y+1)*tile-(spec.height-(spec.visibleTop||0))*s-fs*.95;const label=e.username+(e.busy?' ···':'');const tw=ctx.measureText(label).width+14;ctx.fillStyle=e.id===this.selfId?'#0c2c24e8':'#071523e6';ctx.beginPath();ctx.roundRect(x-tw/2,y-fs*.7,tw,fs*1.45,4);ctx.fill();ctx.fillStyle=e.id===this.selfId?'#adf0cf':'#f1f5fa';ctx.fillText(label,x,y);this.hits.push({kind:'player',id:e.id,x:x-tw/2,y:y-fs*.7,w:tw,h:fs*1.45});}
 }
}
