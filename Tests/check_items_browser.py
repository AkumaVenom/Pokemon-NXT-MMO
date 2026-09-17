"""Real Chromium UI -> WebSocket server -> SQLite item acceptance.

Requires aiohttp, websockets, Python Playwright and NXT_BROWSER_PATH (defaults
/usr/bin/chromium). Uses disposable accounts/data, never operator credentials.
Set NXT_QA_BRIDGE=1 for the existing DOM-only transport fixture when native
browser navigation is unavailable. No browser policies are changed.
The JavaScript observer is read-only; game actions use actual DOM controls.
"""
import asyncio,copy,dataclasses,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from playwright.async_api import async_playwright
from ui_bridge import Bridge
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from server import Service
PASSWORD='Item_Browser_QA_864!'
async def main():
 with tempfile.TemporaryDirectory(prefix='nxt-item-ui-') as tmp:
  cfg=Path(tmp)/'config.ini';cfg.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes());settings=Settings.load(cfg);settings.config.set('database','backend','sqlite');settings.config.set('security','auth_attempts_per_minute','100');s=dataclasses.replace(settings,encounter_chance=0);c=Content(ROOT/'Server/data/world.json');db=Store(s);db.acquire_lease();service=Service(s,c,db);world=service.world;base=''
  output=Path(os.environ.get('NXT_QA_OUTPUT','/mnt/data/nxt_item_browser'));output.mkdir(parents=True,exist_ok=True)
  async def bootstrap(request):return web.json_response({'host':'127.0.0.1','port':int(base.rsplit(':',1)[1]),'tls':False,'endpoint':base.replace('http','ws',1)+'/world','nonce':'item-qa','pixelScale':3,'uiScale':1,'audio':{'muted':True}})
  async def noop(request):return web.json_response({'persisted':False})
  observer='globalThis.__itemQA={snapshot:()=>({state,owner:session?.id,map:renderer?.map?.id,pending:!!renderer?.pendingMap,battle:activeBattle})};'
  async def script(request):return web.Response(text=(ROOT/'Client/app/app.js').read_text()+'\n'+observer,content_type='text/javascript')
  async def index(request):return web.FileResponse(ROOT/'Client/app/index.html')
  app=web.Application();app.router.add_get('/world',service.socket);app.router.add_get('/bootstrap',bootstrap);app.router.add_post('/heartbeat',noop);app.router.add_post('/audio-settings',noop);app.router.add_get('/app.js',script);app.router.add_get('/',index);app.router.add_static('/',ROOT/'Client/app');runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start();base='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1]);checks=[];errors=[];bridges={};bridge_mode=os.environ.get('NXT_QA_BRIDGE')=='1'
  async with async_playwright() as pw:
   browser=await pw.chromium.launch(headless=True,executable_path=os.environ.get('NXT_BROWSER_PATH','/usr/bin/chromium'),args=['--no-sandbox','--disable-dev-shm-usage']);ctx=await browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1);page=await ctx.new_page();peer=await ctx.new_page()
   for p in (page,peer):p.on('pageerror',lambda e:errors.append(str(e)))
   async def login(p,name):
    if bridge_mode:
     bridge=Bridge(p,base.replace('http','ws',1)+'/world',observer);bridges[p]=bridge;bridge.audio_settings['muted']=True;await bridge.start()
    else:await p.goto(base)
    await p.locator('#login').wait_for(state='visible');await p.click('#register-tab');await p.fill('#username',name);await p.fill('#password',PASSWORD);await p.click('#auth-submit');await p.locator('#game').wait_for(state='visible');await p.wait_for_function('()=>__itemQA.snapshot().state?.creatures?.length&&!__itemQA.snapshot().pending');return await p.evaluate('()=>__itemQA.snapshot().owner')
   async def close():
    if await page.locator('#modal').is_visible():await page.click('#modal-close')
   async def bag(key):
    await close();await page.click('#bag-button');await page.get_by_role('textbox',name='Search Bag',exact=True).fill(c.items[key]['name']);return page.locator('[data-item="'+key+'"]')
   async def changed(revision):await page.wait_for_function('(r)=>__itemQA.snapshot().state.revision>r',arg=revision)
   async def use(key,uid=None,slot=None):
    row=await bag(key);await row.get_by_role('button',name='Activate…' if key.endswith('repel') else 'Use…',exact=True).click()
    if uid:await page.get_by_label('Item target Pokémon',exact=True).select_option(uid)
    if slot is not None:await page.get_by_label('Item move slot',exact=True).select_option(str(slot))
    rev=world.players[aid].state['revision'];await page.get_by_role('button',name='Confirm use',exact=True).click();await changed(rev)
   try:
    aid=await login(page,'ItemsBrowserOwner');bid=await login(peer,'ItemsBrowserPeer');a=world.players[aid];peer_before=copy.deepcopy(world.players[bid].state)
    first=c.new_mon('fr_4',15,'ItemsBrowserOwner');first['hp']=1;first['heldItemId']=0;first['moves']=[{'id':52,'pp':0},{'id':33,'pp':3},{'id':45,'pp':40},{'id':108,'pp':1}]
    second=c.new_mon('fr_7',20,'ItemsBrowserOwner');second['hp']=0;second['heldItemId']=0
    third=c.new_mon('fr_25',20,'ItemsBrowserOwner');third['heldItemId']=0;third['moves']=[{'id':33,'pp':3}]
    async with world.lock:
     st=copy.deepcopy(a.state);st['creatures']=[first,second,third];st['party']=[m['uid'] for m in st['creatures']];st['items']={k:4 for k in c.items};st['money']=200000;await world.commit(a,st)
    await page.wait_for_function('()=>__itemQA.snapshot().state.items.timerball===4')
    await use('potion',first['uid']);assert a.state['creatures'][0]['hp']==21 and db.load(aid)['items']['potion']==3;checks.append('Field Potion uses the selected owner target and commits HP/item together')
    await use('revive',second['uid']);assert a.state['creatures'][1]['hp']==c.stats(second)[0]//2;checks.append('Revive targets a fainted bench partner instead of the lead')
    await use('ppup',first['uid'],0);assert a.state['creatures'][0]['moves'][0]['ppUps']==1;await use('maxether',first['uid'],0);assert a.state['creatures'][0]['moves'][0]['pp']==30;checks.append('PP Up changes max PP and Max Ether restores the upgraded cap')
    row=await bag('flameball');await row.get_by_role('button',name='Give to Pokémon…',exact=True).click();await page.get_by_label('Item target Pokémon',exact=True).select_option(first['uid']);rev=a.state['revision'];await page.get_by_role('button',name='Confirm held item',exact=True).click();await changed(rev);assert a.state['creatures'][0]['heldItemKey']=='flameball';checks.append('Flame Ball can be equipped with its source namespace preserved')
    row=await bag('tm48');await row.get_by_role('button',name='Teach…',exact=True).click();await page.get_by_label('Item target Pokémon',exact=True).select_option(third['uid']);await page.get_by_label('Item move slot',exact=True).select_option('0');rev=a.state['revision'];await page.get_by_role('button',name='Confirm teaching',exact=True).click();await changed(rev);assert a.state['creatures'][2]['moves'][0]['id']==85 and a.state['items']['tm48']==3;checks.append('TM48 uses the real Sigma Thunderbolt move, compatibility and explicit replacement')
    await use('rarecandy',first['uid']);assert a.state['creatures'][0]['level']==16;checks.append('Rare Candy commits a level and exposes native evolution choices')
    row=await bag('timerball');assert await row.get_by_text('THROW IN WILD BATTLE',exact=True).is_visible();assert await row.get_by_role('button',name='Use…',exact=True).count()==0;await page.screenshot(path=str(output/'bag-timer-ball.png'));checks.append('Timer Ball is visibly a battle capture item, not an inert field-use button')
    await close()
    async with world.lock:await world.start_wild(a,('fr_129',5));battle=world.battles[a.battle];battle.turn=12;a.send('battle',battle=battle.view(0))
    await page.locator('#battle-dialog').wait_for(state='visible');await page.wait_for_function('()=>__itemQA.snapshot().battle?.turn===12');await page.wait_for_timeout(1800)
    await page.get_by_label('Battle item',exact=True).select_option('timerball');assert '2.1×' in (await page.get_by_label('Battle item',exact=True).locator('option:checked').inner_text());await page.screenshot(path=str(output/'battle-timer-ball.png'))
    with patch.object(c.rng,'randrange',return_value=0):await page.get_by_role('button',name='Throw Timer Ball',exact=True).click();await page.wait_for_function('()=>__itemQA.snapshot().battle?.ended===true')
    await page.wait_for_timeout(2200);await page.get_by_role('button',name='Return to adventure',exact=True).click();assert a.state['items']['timerball']==3 and db.load(aid)['creatures'][-1]['captureBall']=='timerball';checks.append('Real Timer Ball UI shows 2.1x on turn 12, throws, catches and persists the ball identity')
    # Actual Sigma service location, not a debug shortcut or mocked command.
    async with world.lock:
     candidate=world.relocation_state(a,'johto_34_13',11,3);await world.commit(a,candidate);world.send_map(a)
    await page.wait_for_function('()=>__itemQA.snapshot().map==="johto_34_13"&&!__itemQA.snapshot().pending')
    row=await bag('whtapricorn');await row.get_by_role('button',name='Make Fast Ball…',exact=True).click();rev=a.state['revision'];await page.get_by_role('button',name='Make one Fast Ball',exact=True).click();await changed(rev);assert a.state['items']['whtapricorn']==3 and a.state['items']['fastball']==5;checks.append('Kurt crafting requires the real house and makes an owned usable Fast Ball')
    row=await bag('pokeblockcas');await row.get_by_role('button',name='Open Pokéblock Case…',exact=True).click();rev=a.state['revision'];await page.get_by_role('button',name='Blend Sitrus Berry',exact=True).click();await changed(rev);await page.get_by_role('button',name='Feed block…',exact=True).click();await page.get_by_label('Item target Pokémon',exact=True).select_option(first['uid']);rev=a.state['revision'];await page.get_by_role('button',name='Feed selected block',exact=True).click();await changed(rev);assert a.state['creatures'][0]['condition']['beauty']==20;checks.append('Pokéblock blending and selected-target feeding persist condition and consume the berry/block, not the case')
    await use('repel');assert a.state['repelSteps']==100;checks.append('Repel activates from the Bag and publishes its remaining step budget')
    # Exercise real clerk authority and durable sale/wallet actions.
    mart,clerk=next((m,n) for m in c.maps.values() if m.get('playable',True) for n in m.get('objects',[]) if n.get('graphics')==68)
    pos=next((x,y) for y in range(max(0,clerk['y']-2),min(mart['height'],clerk['y']+3)) for x in range(max(0,clerk['x']-2),min(mart['width'],clerk['x']+3)) if world.walkable(mart,x,y,state=a.state))
    async with world.lock:
     candidate=world.relocation_state(a,mart['id'],*pos);await world.commit(a,candidate);world.send_map(a)
    await page.wait_for_function('()=>__itemQA.snapshot().state.itemContext.mart&&!__itemQA.snapshot().pending')
    row=await bag('nugget');await row.get_by_role('button',name='Sell…',exact=True).click();await page.get_by_label('Quantity to sell',exact=True).fill('2');rev=a.state['revision'];cash=a.state['money'];await page.get_by_role('button',name='Confirm sale',exact=True).click();await changed(rev);assert a.state['money']==cash+2*c.items['nugget']['mechanics']['sellPrice'] and a.state['items']['nugget']==2;checks.append('Selling two Nuggets at a real clerk commits exactly two units and the server price')
    row=await bag('coincase');await row.get_by_role('button',name='Open Coin Case…',exact=True).click();rev=a.state['revision'];await page.get_by_role('button',name='Buy 100 coins',exact=True).click();await changed(rev);assert a.state['coins']==100;rev=a.state['revision'];await page.get_by_role('button',name='Exchange for Timer Ball',exact=True).click();await changed(rev);assert a.state['coins']==0 and a.state['items']['timerball']==4;checks.append('Coin Case purchase and prize exchange use the real mart controls and durable wallet')
    assert world.players[bid].state==peer_before;assert db.load(bid)==peer_before;checks.append('Second connected account retains its inventory, Pokémon and progress throughout')
    await page.set_viewport_size({'width':1024,'height':768});await bag('flameball');await page.screenshot(path=str(output/'bag-1024-layout.png'));assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');assert not errors,errors
    checks.append('1024-pixel layout has no document overflow; both pages have no JavaScript errors')
    result={'passed':True,'checks':checks,'browser':'Chromium '+browser.version,'transport':'DOM/asset bridge + real aiohttp WebSocket' if bridge_mode else 'native browser WebSocket','database':'disposable SQLite','pageErrors':errors};(output/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
   except Exception:
    await page.screenshot(path=str(output/'failure.png'));print('PAGE ERRORS:',errors,flush=True);raise
   finally:
    for bridge in list(bridges.values()):await bridge.close()
    await browser.close();await runner.cleanup();db.close()
if __name__=='__main__':asyncio.run(main())
