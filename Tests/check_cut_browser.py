"""Chromium DOM + real game-service/SQLite acceptance on the actual client.

Default transport is native browser WebSocket on a permitted local host. Optional
NXT_QA_BRIDGE=1 uses the existing DOM/asset/aiohttp transport fixture without
changing browser policies. Both run real input handlers and server persistence.
A read-only observer exposes renderer state; no game action is implemented by it.
No operator configuration/database is opened. Requires Python Playwright and an
installed browser (NXT_BROWSER_PATH). Not Windows/Edge/MySQL deployment QA.
"""
from __future__ import annotations
import asyncio,copy,dataclasses,json,os,sys,tempfile
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from server import Service
from ui_bridge import Bridge

PASSWORD='Cut_Browser_Fixture_938!'

async def main():
 with tempfile.TemporaryDirectory(prefix='nxt-cut-browser-') as tmp:
  cfg=Path(tmp)/'config.ini';cfg.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes())
  s=Settings.load(cfg);s.config.set('database','backend','sqlite');s.config.set('security','auth_attempts_per_minute','100');s=dataclasses.replace(s,encounter_chance=0)
  c=Content(ROOT/'Server/data/world.json');db=Store(s);db.acquire_lease();service=Service(s,c,db);world=service.world
  app=web.Application();base=''
  async def bootstrap(request):return web.json_response({'host':'127.0.0.1','port':int(base.rsplit(':',1)[1]),'tls':False,'endpoint':base.replace('http','ws',1)+'/world','nonce':'disposable-cut-qa','pixelScale':3,'uiScale':1,'audio':{'muted':True}})
  async def noop(request):return web.json_response({'persisted':False})
  async def script(request):
   text=(ROOT/'Client/app/app.js').read_text(encoding='utf-8')
   return web.Response(text=text+'\nglobalThis.__cutQA={snapshot:()=>({map:renderer?.map?.id,pending:!!renderer?.pendingMap,hits:renderer?.hits||[],cuts:state?.adventure?.cutTrees||{},owner:session?.id,revision:state?.revision,x:own?.x,y:own?.y,pendingMove})};\n',content_type='text/javascript')
  async def index(request):return web.FileResponse(ROOT/'Client/app/index.html')
  app.router.add_get('/world',service.socket);app.router.add_get('/bootstrap',bootstrap);app.router.add_post('/heartbeat',noop);app.router.add_post('/audio-settings',noop);app.router.add_get('/app.js',script);app.router.add_get('/',index);app.router.add_static('/',ROOT/'Client/app')
  runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start();base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
  output=Path(os.environ.get('NXT_QA_OUTPUT') or tempfile.mkdtemp(prefix='nxt-cut-screens-'));output.mkdir(parents=True,exist_ok=True)
  print('HTTP fixture ready',base,flush=True)
  errors=[];checks=[];bridges={};bridge_mode=os.environ.get('NXT_QA_BRIDGE')=='1'
  observer='globalThis.__cutQA={snapshot:()=>({map:renderer?.map?.id,pending:!!renderer?.pendingMap,hits:renderer?.hits||[],cuts:state?.adventure?.cutTrees||{},owner:session?.id,revision:state?.revision,x:own?.x,y:own?.y,pendingMove})};'
  async with async_playwright() as pw:
   browser=await pw.chromium.launch(headless=True,executable_path=os.environ.get('NXT_BROWSER_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
   ctx=await browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1)
   a,b=await ctx.new_page(),await ctx.new_page()
   for p in (a,b):p.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE ERROR',e,flush=True)))
   async def login(p,name,create=False):
    print('Login',name,create,flush=True)
    if bridge_mode:
     bridge=Bridge(p,base.replace('http','ws',1)+'/world',observer);bridges[p]=bridge;bridge.audio_settings['muted']=True;await bridge.start()
    else:await p.goto(base)
    print('UI loaded',name,flush=True)
    await p.locator('#login').wait_for(state='visible')
    if create:await p.click('#register-tab')
    await p.fill('#username',name);await p.fill('#password',PASSWORD);await p.click('#auth-submit');await p.locator('#game').wait_for(state='visible');await p.wait_for_function('()=>__cutQA.snapshot().owner&&Number.isSafeInteger(__cutQA.snapshot().revision)')
    return await p.evaluate('()=>__cutQA.snapshot().owner')
   async def click_tree(p,key,npc):
    print('Click tree',key,npc,flush=True)
    await p.bring_to_front();await p.wait_for_timeout(250)
    await p.wait_for_function('([key,npc])=>{const s=__cutQA.snapshot();return s.map===key&&!s.pending&&s.hits.some(h=>h.kind==="npc"&&h.id===npc)}',arg=[key,npc])
    xy=await p.evaluate('npc=>{const s=__cutQA.snapshot(),h=s.hits.find(h=>h.kind==="npc"&&h.id===npc),r=document.querySelector("#world-canvas").getBoundingClientRect();return [r.left+h.x+h.w/2,r.top+h.y+h.h/4]}',npc)
    await p.mouse.click(*xy);await p.locator('#modal').wait_for(state='visible')
   try:
    aid=await login(a,'CutBrowserOwner',True);bid=await login(b,'CutBrowserPeer',True)
    for region in ('kanto','johto'):
     # Real map geometry and original graphic-95 object, not a synthetic browser sprite.
     key=next(key for key,m in c.maps.items() if key.startswith(region+'_') and m['name']==('Route 2' if region=='kanto' else 'Ilex Forest') and any(o['graphics']==95 for o in m['objects']))
     m=c.maps[key];tree=next(o for o in m['objects'] if o['graphics']==95 and any(world.walkable(m,o['x']+dx,o['y']+dy) for dx,dy in ((-1,0),(1,0),(0,1),(0,-1))))
     x,y=next((tree['x']+dx,tree['y']+dy) for dx,dy in ((-1,0),(1,0),(0,1),(0,-1)) if world.walkable(m,tree['x']+dx,tree['y']+dy))
     async with world.lock:
      for uid in (aid,bid):
       player=world.players[uid];state=world.relocation_state(player,key,x,y);state['adventure']['badges']=[region+'_1',region+'_2'] if uid==aid else []
       await world.commit(player,state);world.send_map(player)
     await click_tree(b,key,tree['id']);assert await b.get_by_role('button',name='Cut tree — locked',exact=True).is_disabled();assert await b.locator('#modal-body').inner_text()
     await b.screenshot(path=str(output/(region+'-locked.png')));await b.get_by_role('button',name='Close',exact=True).click()
     await click_tree(a,key,tree['id']);assert await a.get_by_role('button',name='Cut tree',exact=True).is_enabled();await a.screenshot(path=str(output/(region+'-unlocked.png')))
     await a.get_by_role('button',name='Cut tree',exact=True).click();await a.get_by_text('Path cleared',exact=True).wait_for()
     await a.wait_for_function('([key,npc])=>{const s=__cutQA.snapshot();return s.cuts[key]?.includes(npc)&&!s.hits.some(h=>h.kind==="npc"&&h.id===npc)}',arg=[key,tree['id']])
     assert world.walkable(m,tree['x'],tree['y'],state=world.players[aid].state)
     assert not world.walkable(m,tree['x'],tree['y'],state=world.players[bid].state)
     assert tree['id'] in db.load(aid)['adventure']['cutTrees'][key]
     assert not db.load(bid)['adventure']['cutTrees']
     await a.get_by_role('button',name='Close',exact=True).click();await a.screenshot(path=str(output/(region+'-cleared-owner.png')))
     await click_tree(b,key,tree['id']);assert await b.get_by_role('button',name='Cut tree — locked',exact=True).is_disabled();await b.get_by_role('button',name='Close',exact=True).click()
     # Real keyboard input must also respect the per-account obstacle state.
     arrow={(-1,0):'ArrowLeft',(1,0):'ArrowRight',(0,-1):'ArrowUp',(0,1):'ArrowDown'}[(tree['x']-x,tree['y']-y)]
     await a.bring_to_front();await a.keyboard.press(arrow)
     await a.wait_for_function('([x,y])=>{const s=__cutQA.snapshot();return s.x===x&&s.y===y&&!s.pendingMove}',arg=[tree['x'],tree['y']])
     assert (world.players[aid].state['x'],world.players[aid].state['y'])==(tree['x'],tree['y'])
     await b.bring_to_front();await b.keyboard.press(arrow);await b.wait_for_timeout(250)
     assert (world.players[bid].state['x'],world.players[bid].state['y'])==(x,y)
     checks.append(region+': real keyboard movement enters cleared tile for owner and remains blocked for peer')
     checks.append(region+': native canvas click -> enabled/locked menu -> real nxt.v1 command through selected QA transport -> SQLite commit -> owner sprite/hit removed -> peer retained')
    # A completely new browser page loads the stored flags through normal authentication.
    if a in bridges:await bridges.pop(a).close()
    await a.close()
    async with asyncio.timeout(5):
     while aid in world.players:await asyncio.sleep(.02)
    a=await ctx.new_page();a.on('pageerror',lambda e:errors.append(str(e)));assert await login(a,'CutBrowserOwner')==aid
    await a.wait_for_function('()=>Object.keys(__cutQA.snapshot().cuts).length===2')
    await a.wait_for_function('npc=>!__cutQA.snapshot().pending&&!__cutQA.snapshot().hits.some(h=>h.kind==="npc"&&h.id===npc)',arg=tree['id'])
    checks.append('fresh-page relog restores both regional cut flags without affecting peer')
    assert not errors,errors
    assert not any(bridge.errors for bridge in bridges.values()),[bridge.errors for bridge in bridges.values()]
    result={'result':'PASS','browser':browser.version,'transport':('DOM/asset bridge + real aiohttp WebSocket / temporary SQLite' if bridge_mode else 'native browser WebSocket / aiohttp service / temporary SQLite'),'checks':checks,'pageErrors':errors,'screenshots':str(output)}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
   finally:
    for bridge in list(bridges.values()):await bridge.close()
    await ctx.close();await browser.close();await runner.cleanup();db.close()

async def bounded_main():
 async with asyncio.timeout(120):await main()

if __name__=='__main__':asyncio.run(bounded_main())
