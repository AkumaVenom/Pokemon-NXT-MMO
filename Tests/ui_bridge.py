"""Local DOM/rendering harness. No browser policy changes.
The environment blocks browser URL navigation. This harness renders the unchanged
UI from local text and forwards its transport through an aiohttp WebSocket.
It is NOT a Windows/Edge native-launch test; network service tests run separately.
"""
import asyncio,base64,json,re,time,uuid
from pathlib import Path
import aiohttp
ROOT=Path(__file__).resolve().parents[1]/'Client/app'
class Bridge:
 def __init__(self,page,endpoint='ws://127.0.0.1:7777/world'):self.page=page;self.endpoint=endpoint;self.http=None;self.sockets={};self.tasks=[];self.errors=[]
 async def start(self):
  self.http=aiohttp.ClientSession()
  async def fetch(url):
   if url=='/bootstrap':return json.dumps({'endpoint':self.endpoint,'host':'127.0.0.1','port':int(self.endpoint.split(':')[2].split('/')[0]),'tls':False,'pixelScale':0,'uiScale':0,'nonce':'render-test','version':'0.1.0-alpha'})
   p=(ROOT/url.lstrip('/')).resolve()
   if not p.is_relative_to(ROOT) or not p.is_file():raise ValueError('Missing local test asset '+url)
   return p.read_text()
  async def asset(path):
   p=(ROOT/path).resolve()
   if not p.is_relative_to(ROOT) or p.suffix!='.png':raise ValueError('Invalid asset')
   return 'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()
  async def open_socket(id,url,protocol):
   try:
    ws=await self.http.ws_connect(url,protocols=[protocol],headers={'Origin':'http://127.0.0.1:45678'},max_msg_size=2**22);self.sockets[id]=ws
    await self.event(id,'open',None)
    async def pump():
     async for m in ws:
      if m.type==aiohttp.WSMsgType.TEXT:await self.event(id,'message',m.data)
     await self.event(id,'close',None)
    self.tasks.append(asyncio.create_task(pump()))
   except Exception as e:self.errors.append(str(e));await self.event(id,'error',None);await self.event(id,'close',None)
  async def send_socket(id,data):await self.sockets[id].send_str(data)
  async def close_socket(id):
   if id in self.sockets:await self.sockets[id].close()
  await self.page.expose_function('hostFetch',fetch);await self.page.expose_function('hostAsset',asset);await self.page.expose_function('hostSocketOpen',open_socket);await self.page.expose_function('hostSocketSend',send_socket);await self.page.expose_function('hostSocketClose',close_socket)
  html=ROOT.joinpath('index.html').read_text();html=re.sub(r'<script.*?</script>','',html);html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+ROOT.joinpath('styles.css').read_text()+'</style>')
  for path in re.findall(r'src="(assets/[^\"]+)"',html):html=html.replace('src="'+path+'"','src="'+await asset(path)+'"')
  await self.page.set_content(html)
  await self.page.add_script_tag(content='''
window.fetch=async(url,options)=>String(url).startsWith('/heartbeat')?new Response(null,{status:204}):new Response(await hostFetch(String(url)),{status:200,headers:{'Content-Type':'application/json'}});
window.__nxtSockets={};let nextSocket=0;
window.WebSocket=class extends EventTarget {
 static CONNECTING=0;static OPEN=1;static CLOSING=2;static CLOSED=3;
 constructor(url,protocol){super();this.id=++nextSocket;this.readyState=0;window.__nxtSockets[this.id]=this;hostSocketOpen(this.id,url,protocol);}
 send(data){hostSocketSend(this.id,data);}close(){this.readyState=2;hostSocketClose(this.id);}
};
window.__nxtTransportEvent=(id,type,data)=>{const s=window.__nxtSockets[id];if(!s)return;if(type==='open')s.readyState=1;if(type==='close')s.readyState=3;s.dispatchEvent(type==='message'?new MessageEvent(type,{data}):new Event(type));};
const originalSrc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
Object.defineProperty(HTMLImageElement.prototype,'src',{get(){return originalSrc.get.call(this)},set(v){if(String(v).startsWith('assets/')){hostAsset(v).then(data=>originalSrc.set.call(this,data));}else originalSrc.set.call(this,v);}});
const originalSet=HTMLImageElement.prototype.setAttribute;
HTMLImageElement.prototype.setAttribute=function(k,v){if(k==='src'&&String(v).startsWith('assets/'))this.src=v;else originalSet.call(this,k,v);};
''')
  renderer=ROOT.joinpath('renderer.js').read_text().replace('export class WorldRenderer','class WorldRenderer')
  app=ROOT.joinpath('app.js').read_text().replace("import {WorldRenderer} from './renderer.js';",'')
  await self.page.add_script_tag(content='(()=>{'+renderer+'\n'+app+'\n})()')
 async def event(self,id,type,data):
  if not self.page.is_closed():await self.page.evaluate('([id,type,data])=>window.__nxtTransportEvent(id,type,data)',[id,type,data])
 async def close(self):
  for ws in list(self.sockets.values()):await ws.close()
  for task in self.tasks:task.cancel()
  await asyncio.gather(*self.tasks,return_exceptions=True);await self.http.close()
