"""Optional local DOM/rendering harness. No browser policy changes.
This harness renders the current UI from local text, including its audio modules,
and forwards transport through an aiohttp WebSocket. PNG, OGG and WAV assets retain
their original binary bytes. AudioContext unlocking uses ordinary user gestures.
Preferences are held only in this test instance and never written to user files.
This is NOT Windows/Edge native-launch, device-audio or launcher-persistence QA;
real transport and launcher settings tests run separately.
"""
import asyncio,base64,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
import aiohttp
ROOT=Path(__file__).resolve().parents[1]/'Client/app'
MIME={'.json':'application/json','.png':'image/png','.ogg':'audio/ogg','.wav':'audio/wav','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css'}
def response_payload(data,mime='application/json',status=200):
 if isinstance(data,str):data=data.encode('utf-8')
 return {'status':status,'mime':mime,'body':base64.b64encode(data).decode('ascii')}
def source_bundle(observer=""):
 """Bundle the current modules for the optional local DOM-only fixture."""
 modules=[]
 for name in ('battle_timing.js','varieties.js','renderer.js','audio.js','audio_controls.js','battle_fx.js','app.js'):
  text=ROOT.joinpath(name).read_text(encoding='utf-8')
  text=re.sub(r"^import .*?;\n",'',text,flags=re.M)
  text=re.sub(r"^export (?=(?:const|function|class) )",'',text,flags=re.M)
  modules.append(text)
 return '(()=>{'+ '\n'.join(modules)+'\n'+observer+'\nwindow.__nxtAudioHarnessShutdown=()=>audio.shutdown();\n})()'
class Bridge:
 def __init__(self,page,endpoint='ws://127.0.0.1:7777/world',observer=''):
  self.page=page;self.endpoint=endpoint;self.observer=observer;self.http=None;self.sockets={};self.tasks=[];self.errors=[]
  self.audio_settings={'master':.8,'music':.65,'effects':.8,'cries':.85,'muted':False,'muteUnfocused':True,'lowHp':True,'chat':True}
 async def fetch_payload(self,url,options=None):
  options=options or {};path=unquote(urlsplit(url).path)
  if path=='/bootstrap':
   version=json.loads(ROOT.joinpath('assets/world/client.json').read_text(encoding='utf-8'))['version']
   return response_payload(json.dumps({'endpoint':self.endpoint,'host':'127.0.0.1','port':int(self.endpoint.split(':')[2].split('/')[0]),'tls':False,'pixelScale':0,'uiScale':0,'nonce':'render-test','version':version,'audio':self.audio_settings,'audioPersistenceMessage':'DOM test harness uses temporary sound preferences; launcher persistence is tested separately.'}))
  if path=='/audio-settings':
   if options.get('method')!='POST':return response_payload('Method not allowed','text/plain',405)
   incoming=json.loads(options.get('body','{}'))
   if isinstance(incoming,dict):self.audio_settings=dict(incoming)
   return response_payload(json.dumps({'audio':self.audio_settings,'persisted':False,'message':'Temporary harness preferences only.'}))
  p=(ROOT/path.lstrip('/')).resolve()
  if not p.is_relative_to(ROOT) or not p.is_file():return response_payload('Missing local test asset','text/plain',404)
  return response_payload(p.read_bytes(),MIME.get(p.suffix.lower(),'application/octet-stream'))
 async def start(self):
  self.http=aiohttp.ClientSession()
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
  await self.page.expose_function('hostFetch',self.fetch_payload);await self.page.expose_function('hostAsset',asset);await self.page.expose_function('hostSocketOpen',open_socket);await self.page.expose_function('hostSocketSend',send_socket);await self.page.expose_function('hostSocketClose',close_socket)
  html=ROOT.joinpath('index.html').read_text(encoding='utf-8');html=re.sub(r'<script.*?</script>','',html);html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+ROOT.joinpath('styles.css').read_text(encoding='utf-8')+'</style>')
  for path in re.findall(r'src="(assets/[^\"]+)"',html):html=html.replace('src="'+path+'"','src="'+await asset(path)+'"')
  await self.page.set_content(html)
  await self.page.add_script_tag(content='''
window.fetch=async(url,options={})=>{
 if(options.signal?.aborted)throw new DOMException('Request aborted','AbortError');
 if(String(url).startsWith('/heartbeat'))return new Response(null,{status:204});
 const payload=await hostFetch(String(url),{method:options.method||'GET',body:options.body||null});
 if(options.signal?.aborted)throw new DOMException('Request aborted','AbortError');
 const bytes=Uint8Array.from(atob(payload.body),char=>char.charCodeAt(0));
 return new Response(bytes,{status:payload.status,headers:{'Content-Type':payload.mime}});
};
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
  await self.page.add_script_tag(content=source_bundle(self.observer))
 async def event(self,id,type,data):
  if not self.page.is_closed():await self.page.evaluate('([id,type,data])=>window.__nxtTransportEvent(id,type,data)',[id,type,data])
 async def close(self):
  if not self.page.is_closed():await self.page.evaluate('()=>window.__nxtAudioHarnessShutdown?.()')
  for ws in list(self.sockets.values()):await ws.close()
  for task in self.tasks:task.cancel()
  await asyncio.gather(*self.tasks,return_exceptions=True);await self.http.close()
