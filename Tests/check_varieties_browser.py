"""Two-account Chromium acceptance of real variety UI, canvas and saved gameplay.

Use NXT_QA_BRIDGE=1 only for the documented local DOM/asset/aiohttp transport
fixture. This does not alter browser networking policy and is not Windows/Edge
or live MySQL acceptance. Test prerequisites use a disposable SQLite database.
"""
from __future__ import annotations
import asyncio,base64,copy,dataclasses,hashlib,json,os,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.varieties import VARIETIES
from server import Service
from ui_bridge import Bridge
PASSWORD='Variety_Browser_Fixture_928!'
OBSERVER=r'''
const __sparkleColours=new Set(Object.values(content?.varietyPolicy?.definitions||{}).map(d=>d.color.toLowerCase()));
const __colourCounts={};const __originalFill=CanvasRenderingContext2D.prototype.fill;
CanvasRenderingContext2D.prototype.fill=function(...args){const color=String(this.fillStyle).toLowerCase();if(/^#[a-f0-9]{6}$/.test(color))__colourCounts[color]=(__colourCounts[color]||0)+1;return __originalFill.apply(this,args);};
globalThis.__varietyQA={snapshot:()=>({owner:session?.id,revision:state?.revision,creatures:state?.creatures,party:state?.party,battle:activeBattle,fxBusy:!!battleFX?.busy,submitting:battleSubmitting,entities:[...(renderer?.players?.values()||[])].map(e=>({id:e.id,follower:e.follower,followerVariety:e.followerVariety})),map:renderer?.map?.id,pending:!!renderer?.pendingMap,images:[...(renderer?.images?.keys()||[])],colours:{...__colourCounts}})};
'''

async def main():
 with tempfile.TemporaryDirectory(prefix='nxt-variety-browser-') as tmp:
  cfg=Path(tmp)/'config.ini';cfg.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes())
  s=Settings.load(cfg);s.config.set('database','backend','sqlite');s.config.set('security','auth_attempts_per_minute','100');s=dataclasses.replace(s,encounter_chance=0)
  c=Content(ROOT/'Server/data/world.json');db=Store(s);db.acquire_lease();service=Service(s,c,db);world=service.world
  app=web.Application();base=''
  async def bootstrap(request):return web.json_response({'host':'127.0.0.1','port':int(base.rsplit(':',1)[1]),'tls':False,'endpoint':base.replace('http','ws',1)+'/world','nonce':'variety-qa','pixelScale':3,'uiScale':1,'audio':{'muted':True}})
  async def noop(request):return web.json_response({'persisted':False})
  async def script(request):return web.Response(text=(ROOT/'Client/app/app.js').read_text()+OBSERVER,content_type='text/javascript')
  async def index(request):return web.FileResponse(ROOT/'Client/app/index.html')
  app.router.add_get('/world',service.socket);app.router.add_get('/bootstrap',bootstrap);app.router.add_post('/heartbeat',noop);app.router.add_post('/audio-settings',noop);app.router.add_get('/app.js',script);app.router.add_get('/',index);app.router.add_static('/',ROOT/'Client/app')
  runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start();base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
  output=Path(os.environ.get('NXT_QA_OUTPUT') or tempfile.mkdtemp(prefix='nxt-variety-screens-'));output.mkdir(parents=True,exist_ok=True)
  errors=[];checks=[];bridges={};bridge_mode=os.environ.get('NXT_QA_BRIDGE')=='1'
  async with async_playwright() as pw:
   browser=await pw.chromium.launch(headless=True,executable_path=os.environ.get('NXT_BROWSER_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage'])
   ctx=await browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1);ctx.set_default_timeout(10000)
   a,b=await ctx.new_page(),await ctx.new_page()
   def track(page):page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE ERROR',e,flush=True)))
   track(a);track(b)
   async def login(page,name,create=False):
    if bridge_mode:
     bridge=Bridge(page,base.replace('http','ws',1)+'/world',OBSERVER);bridges[page]=bridge;bridge.audio_settings['muted']=True;await bridge.start()
    else:await page.goto(base)
    await page.locator('#login').wait_for(state='visible')
    if create:await page.click('#register-tab')
    await page.fill('#username',name);await page.fill('#password',PASSWORD);await page.click('#auth-submit');await page.locator('#game').wait_for(state='visible')
    await page.wait_for_function('()=>__varietyQA.snapshot().owner&&Number.isSafeInteger(__varietyQA.snapshot().revision)')
    return await page.evaluate('()=>__varietyQA.snapshot().owner')
   async def settled(page):
    await page.bring_to_front();await page.wait_for_function('()=>{const s=__varietyQA.snapshot();return s.battle&&!s.fxBusy&&!s.submitting;}')
    await page.wait_for_function('()=>[...document.querySelectorAll(".battle-sprite")].length===2&&[...document.querySelectorAll(".battle-sprite")].every(i=>i.complete&&i.naturalWidth>0)')
   async def sprite_check(page,side,variety):
    node=page.locator('.battle-sprite.'+side);assert await node.get_attribute('data-variety')==variety
    image=await node.evaluate('(i)=>({src:i.currentSrc,transform:getComputedStyle(i).transform,alt:i.alt,width:i.naturalWidth})')
    expected=(ROOT/'Client/app/assets'/c.species['fr_25']['varieties'][variety]['front']).read_bytes()
    if bridge_mode:assert hashlib.sha256(base64.b64decode(image['src'].split(',',1)[1])).digest()==hashlib.sha256(expected).digest()
    else:assert image['src'].endswith(c.species['fr_25']['varieties'][variety]['front'])
    assert image['alt']==('Pikachu' if variety=='normal' else variety.title()+' Pikachu')
    if side=='you':assert image['transform']=='matrix(-1, 0, 0, 1, 0, 0)',image
    else:assert image['transform'] in ('none','matrix(1, 0, 0, 1, 0, 0)'),image
   async def retreat(page):
    await settled(page);await page.get_by_role('button',name='Run',exact=True).click();await settled(page);await page.get_by_role('button',name='Return to adventure',exact=True).click()
   try:
    aid=await login(a,'VarietyOwner',True);bid=await login(b,'VarietyPeer',True);print('Two accounts authenticated',flush=True)
    async with world.lock:
     for uid in (aid,bid):
      player=world.players[uid];state=copy.deepcopy(player.state);mons=[c.new_mon('fr_25',20,player.username,variety=v) for v in VARIETIES];state['creatures']+=mons;state['party']=[m['uid'] for m in mons];state['items']['pokeball']=50
      if uid==bid:
       m=c.maps[state['map']];x,y=state['x'],state['y'];state['x'],state['y']=next((x+dx,y+dy) for dx,dy in ((3,0),(-3,0),(0,3),(0,-3)) if world.walkable(m,x+dx,y+dy))
      await world.commit(player,state);world.follower_anchor(player);world.send_map(player)
    await world.tick();await a.wait_for_function('()=>__varietyQA.snapshot().creatures.length===7');await b.wait_for_function('()=>__varietyQA.snapshot().entities.length===2')
    # Native UI opens collection; filtering is local and never chooses an encounter identity.
    await a.bring_to_front();await a.keyboard.press('p');await a.locator('#modal').wait_for(state='visible');await a.get_by_label('Filter Pokémon variety',exact=True).select_option('shadow')
    assert await a.locator('.collection-card').count()==1;assert 'Shadow Pikachu' in await a.locator('.collection-card').inner_text()
    await a.screenshot(path=str(output/'collection-shadow.png'));await a.get_by_label('Filter Pokémon variety',exact=True).select_option('all');await a.screenshot(path=str(output/'collection-all-six.png'));print('Closing collection',flush=True);await a.locator('#modal-close').click();print('Collection closed',flush=True);checks.append('real collection dropdown filters six same-species identities with correct portraits')
    for index,variety in enumerate(VARIETIES):
     print('Battle and followers:',variety,flush=True)
     async with world.lock:
      for uid,v in ((aid,variety),(bid,VARIETIES[(index+1)%6])):
       player=world.players[uid];state=copy.deepcopy(player.state);lead=next(m for m in state['creatures'] if m['species']=='fr_25' and m['variety']==v);state['party']=[lead['uid']]+[i for i in state['party'] if i!=lead['uid']]
       for mon in state['creatures']:c.heal(mon)
       await world.commit(player,state)
     await world.tick()
     for page in (a,b):
      await page.bring_to_front();await page.wait_for_function('([id,v])=>__varietyQA.snapshot().entities.some(e=>e.id===id&&e.followerVariety===v)',arg=[aid,variety]);await page.wait_for_timeout(120)
      snap=await page.evaluate('()=>__varietyQA.snapshot()');assert c.species['fr_25']['icon'] in snap['images'];assert not any('/varieties/' in path for path in snap['images'])
      if variety!='normal':assert snap['colours'].get(c.data['varietyPolicy']['definitions'][variety]['color'].lower(),0)>0
     await a.bring_to_front();await a.screenshot(path=str(output/('followers-'+variety+'.png')))
     with patch.object(c.varieties,'roll',return_value=variety):
      async with world.lock:await world.start_wild(world.players[aid],('fr_25',20))
     await a.locator('#battle-dialog').wait_for(state='visible');await settled(a);await sprite_check(a,'you',variety);await sprite_check(a,'enemy',variety);await a.screenshot(path=str(output/('battle-'+variety+'.png')))
     if index==0:
      # Sample the actual computed transform while production WAAPI effects run.
      print('Attacking via UI',flush=True);await a.locator('.battle-choice-panel .move-button:enabled').first.click();print('Attack submitted',flush=True)
      samples=await asyncio.wait_for(a.evaluate("""()=>new Promise(resolve=>{const values=[];const sample=()=>{const i=document.querySelector('.battle-sprite.you');if(i){const m=new DOMMatrixReadOnly(getComputedStyle(i).transform);values.push(m.a*m.d-m.b*m.c);}};sample();const interval=setInterval(sample,25);setTimeout(()=>{clearInterval(interval);resolve(values);},2000);})"""),8)
      print('Animation samples',len(samples),flush=True)
      assert samples and all(d<=0 for d in samples),samples;await settled(a);checks.append('actual player WAAPI attack/hit transforms keep negative determinant; no mid-animation unmirror')
      target=next(m['uid'] for m in world.players[aid].state['creatures'] if m['species']=='fr_25' and m['variety']=='ancient')
      print('Switching via UI',flush=True);await a.get_by_label('Switch active Pokemon',exact=True).select_option(target);await settled(a);print('Switch settled',flush=True);await sprite_check(a,'you','ancient');await sprite_check(a,'enemy','normal');checks.append('same-species normal-to-Ancient switch preserves separate opponent identity and correct incoming portrait')
     if variety=='shadow':
      await a.set_viewport_size({'width':900,'height':680});await a.screenshot(path=str(output/'battle-compact.png'));assert await a.locator('.battle-sprite.you').is_visible();await a.set_viewport_size({'width':1440,'height':1000})
      battle=world.battles[world.players[aid].battle];caught_uid=battle.mon(1)['uid']
      with patch.object(c.rng,'random',return_value=0.0):
       await a.get_by_label('Battle item',exact=True).select_option('pokeball');await a.wait_for_function('()=>__varietyQA.snapshot().battle?.result==="caught"');await settled(a)
      assert any(m['uid']==caught_uid and m['variety']=='shadow' for m in db.load(aid)['creatures']);await a.get_by_role('button',name='Return to adventure',exact=True).click();checks.append('real item selector captures server-rolled Shadow Pikachu; original UUID/variety saved in SQLite')
     else:
      print('Retreating',flush=True);await retreat(a);print('Retreated',flush=True)
     checks.append(variety+': correct front bytes on both battle sides, flipped player only, peer-replicated native follower icon and bounded colour effect')
    await a.emulate_media(reduced_motion='reduce');await a.wait_for_timeout(200);await a.screenshot(path=str(output/'followers-reduced-motion.png'));checks.append('browser reduced-motion setting keeps readable static follower markers')
    # New page / ordinary login reads the completed capture, not in-memory fixtures.
    if a in bridges:await bridges.pop(a).close()
    await a.close()
    async with asyncio.timeout(5):
     while aid in world.players:await asyncio.sleep(.02)
    a=await ctx.new_page();track(a);assert await login(a,'VarietyOwner')==aid
    await a.wait_for_function('uid=>__varietyQA.snapshot().creatures.some(m=>m.uid===uid&&m.variety==="shadow")',arg=caught_uid);checks.append('fresh-page relog restores captured variety and collection; second account does not acquire it')
    assert not any(m['uid']==caught_uid for m in db.load(bid)['creatures'])
    assert not errors,errors;assert not any(v.errors for v in bridges.values())
    result={'result':'PASS','browser':browser.version,'transport':'DOM/asset bridge + real aiohttp WebSocket / temporary SQLite' if bridge_mode else 'native browser WebSocket / temporary SQLite','checks':checks,'pageErrors':errors,'sourcePack':c.pack,'screenshots':str(output)}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
   except BaseException:
    traceback.print_exc();raise
   finally:
    for bridge in list(bridges.values()):
     try:await asyncio.wait_for(bridge.close(),5)
     except Exception:pass
    await ctx.close();await browser.close();await runner.cleanup();db.close()

async def bounded_main():
 async with asyncio.timeout(180):await main()
if __name__=='__main__':asyncio.run(bounded_main())
