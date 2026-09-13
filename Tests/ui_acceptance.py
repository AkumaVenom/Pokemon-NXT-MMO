import asyncio,json,math,re,time,configparser,os,shutil,socket,subprocess,sys,tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from ui_bridge import Bridge
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'Tests/ui_artifacts';OUT.mkdir(exist_ok=True)
PASSWORD='AlphaOnly_Private_872!'
PROCESS=None;ENDPOINT=None
async def admin(text):
 PROCESS.stdin.write(text+'\n');PROCESS.stdin.flush()
 await asyncio.sleep(.25)
async def login(page,name,create=True,starter='fr_1'):
 await page.locator('#login').wait_for(state='visible')
 if create:await page.click('#register-tab')
 await page.fill('#username',name);await page.fill('#password',PASSWORD)
 if create and starter!='fr_1':await page.locator('.starter-choice').filter(has_text='Totodile').click()
 await page.click('#auth-submit');await page.locator('#game').wait_for(state='visible',timeout=15000);await page.wait_for_timeout(600)
async def click_trainer(page,x=10,y=10,ownx=10,owny=10):
 rect=await page.locator('#world-canvas').bounding_box();s=max(2,min(6,int(rect['height']//195)));tile=16*s;mw=24*tile;mh=20*tile;ox=(rect['width']-mw)/2 if mw<rect['width'] else max(rect['width']-mw,min(0,rect['width']/2-(ownx+.5)*tile));oy=(rect['height']-mh)/2 if mh<rect['height'] else max(rect['height']-mh,min(0,rect['height']/2-(owny+.5)*tile));cx=rect['x']+ox+(x+.5)*tile;cy=rect['y']+oy+(y+1)*tile-10*s
 print('PICK',cx,cy,rect,s,flush=True);await page.bring_to_front();await page.mouse.click(cx,cy);await page.locator('#context-menu').wait_for(state='visible')
async def main():
 errors=[];results={}
 async with async_playwright()as pw:
  browser=await pw.chromium.launch(executable_path=os.environ.get('NXT_BROWSER_PATH') or shutil.which('chromium') or shutil.which('msedge'),headless=True,args=['--no-sandbox']);context=await browser.new_context(viewport={'width':1600,'height':1000},device_scale_factor=1)
  context.set_default_timeout(5000);a=await context.new_page();b=await context.new_page();a.on('pageerror',lambda e:errors.append('A '+str(e)));b.on('pageerror',lambda e:errors.append('B '+str(e)))
  ba,bb=Bridge(a,ENDPOINT),Bridge(b,ENDPOINT);await ba.start();await bb.start()
  suffix=str(int(time.time()))[-5:];an='TrainerA_'+suffix;bn='TrainerB_'+suffix
  await login(a,an);await login(b,bn,starter='fr_158');await a.wait_for_timeout(800)
  await a.keyboard.press('ArrowRight');await a.wait_for_timeout(500);coords=await a.locator('#coords').inner_text();results['single_key_step']=coords.startswith('11, 10');print('STEP',coords)
  await b.fill('#chat-input','Hello Kanto - '+suffix);await b.locator('#chat-form button').click();await a.get_by_text('Hello Kanto - '+suffix,exact=True).wait_for();results['general_chat']=True
  await a.screenshot(path=str(OUT/'multiplayer.png'))
  await click_trainer(a,10,10,11,10);await a.get_by_role('button',name='Trade Pokemon & items',exact=True).click();print('INVITE SENT',flush=True);await b.get_by_role('button',name='Accept invitation',exact=True).click();print('INVITE ACCEPTED',flush=True);await a.get_by_text('Trade with '+bn,exact=True).wait_for();await b.get_by_text('Trade with '+an,exact=True).wait_for()
  await a.locator('.trade-picker input').first.check();await a.get_by_label('Money offered',exact=True).fill('100');assert await a.get_by_role('button',name='Lock current offer',exact=True).is_disabled();await a.get_by_label('Poke Ball offered',exact=True).fill('3');await a.get_by_role('button',name='Apply edited offer',exact=True).click();await a.wait_for_timeout(350)
  await b.locator('.trade-picker input').first.check();await b.get_by_label('Potion offered',exact=True).fill('1');await b.get_by_role('button',name='Apply edited offer',exact=True).click();await b.wait_for_timeout(350)
  await a.get_by_role('button',name='Lock current offer',exact=True).click();await a.wait_for_timeout(300);await b.get_by_role('button',name='Lock current offer',exact=True).click();await a.wait_for_timeout(400)
  await a.screenshot(path=str(OUT/'trade_review.png'))
  await a.get_by_role('button',name='Confirm this exact exchange',exact=True).click();await a.wait_for_timeout(300);await b.get_by_role('button',name='Confirm this exact exchange',exact=True).click();await a.locator('#modal').wait_for(state='hidden');await b.locator('#modal').wait_for(state='hidden');
  results['trade_swap']=await a.locator('#party-list').inner_text();assert 'Totodile' in results['trade_swap'];assert 'Bulbasaur' in await b.locator('#party-list').inner_text();assert await a.locator('#money').inner_text()=='₽ 2,900';assert await b.locator('#money').inner_text()=='₽ 3,100';results['trade_balances']=True
  await click_trainer(a,10,10,11,10);await a.get_by_role('button',name='Challenge to a duel',exact=True).click();await b.get_by_role('button',name='Accept invitation',exact=True).click();await a.locator('#battle-dialog').wait_for(state='visible');await b.locator('#battle-dialog').wait_for(state='visible');
  await a.locator('.move-button:not([disabled])').first.click();await b.locator('.move-button:not([disabled])').first.click();await a.wait_for_timeout(500);await a.screenshot(path=str(OUT/'duel.png'));await a.get_by_role('button',name='Forfeit',exact=True).click();await a.get_by_role('button',name='Return to adventure',exact=True).click();await b.get_by_role('button',name='Return to adventure',exact=True).click();results['duel_turn_and_forfeit']=True
  await admin('spawnwild '+an+' fr_129 2');await a.locator('#battle-dialog').wait_for(state='visible');
  caught=False
  for turn in range(20):
   if await a.get_by_role('button',name='Return to adventure',exact=True).count():caught='A new partner' in await a.locator('#battle-content').inner_text();break
   await a.get_by_label('Battle item',exact=True).select_option('pokeball');await a.wait_for_timeout(250)
  assert caught;await a.screenshot(path=str(OUT/'capture.png'));await a.get_by_role('button',name='Return to adventure',exact=True).click();assert 'Magikarp' in await a.locator('#party-list').inner_text();results['wild_capture']=True
  await a.click('#collection-button');await a.locator('.collection-card').filter(has_text='Magikarp').get_by_role('button',name='Lead',exact=True).click();await a.wait_for_timeout(400);await a.click('#modal-close');assert 'Magikarp' in await a.locator('.party-card').first.inner_text();results['change_lead']=True
  await a.click('#save-button');await a.wait_for_timeout(400);await a.click('#logout');await a.wait_for_timeout(300);await login(a,an,create=False);assert 'Magikarp' in await a.locator('.party-card').first.inner_text();results['relogin_persistence']=True
  await a.click('#atlas-button');await a.locator('.map-card').filter(has_text='New Bark Town').first.click();await a.wait_for_timeout(800);results['johto_travel']=await a.locator('#map-name').inner_text()=='New Bark Town'
  await a.set_viewport_size({'width':3840,'height':2160});await a.wait_for_timeout(900);await a.screenshot(path=str(OUT/'johto_4k_final.png'));metrics=await a.evaluate('({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,dpr:devicePixelRatio})');results['4k_no_page_overflow']=metrics['width']==metrics['scrollWidth']and metrics['height']==metrics['scrollHeight']
  results['browser_errors']=errors;results['bridge_errors']=ba.errors+bb.errors;results['content_pack']=json.loads((ROOT/'Client/app/assets/world/client.json').read_text())['pack'];results['render_method']='Local DOM + real server WebSocket bridge; Chromium navigation policy unchanged. Native Windows/Edge launch not exercised.';print(json.dumps(results,indent=2));(OUT/'ui_results.json').write_text(json.dumps(results,indent=2))
  await a.click('#logout');await b.click('#logout');await ba.close();await bb.close();await browser.close()
def run_isolated():
 global PROCESS,ENDPOINT
 browser=os.environ.get('NXT_BROWSER_PATH') or shutil.which('chromium') or shutil.which('msedge')
 if not browser:raise SystemExit('Set NXT_BROWSER_PATH to an installed Chromium/Edge executable. Playwright is a test-only dependency.')
 with tempfile.TemporaryDirectory(prefix='nxt-ui-test-')as tmp:
  temp=Path(tmp);(temp/'data').mkdir();shutil.copy2(ROOT/'Server/data/world.json',temp/'data/world.json')
  cfg=configparser.ConfigParser(interpolation=None);cfg.read(ROOT/'Build/config_templates/Server/config.ini');cfg.set('database','backend','sqlite');cfg.set('network','bind_ip','127.0.0.1');cfg.set('network','tls','false');cfg.set('network','allow_insecure_lan','true');cfg.set('security','auth_attempts_per_minute','100')
  with socket.socket()as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  cfg.set('network','port',str(port));ENDPOINT=f'ws://127.0.0.1:{port}/world'
  with (temp/'config.ini').open('w')as f:cfg.write(f)
  with (OUT/'isolated_server.log').open('w')as log:
   PROCESS=subprocess.Popen([sys.executable,str(ROOT/'Server/server.py'),'--config',str(temp/'config.ini'),'--dev-sqlite'],stdin=subprocess.PIPE,stdout=log,stderr=log,text=True)
   try:
    import urllib.request
    for attempt in range(100):
     if PROCESS.poll()is not None:raise RuntimeError('Isolated server failed; see ui_artifacts/isolated_server.log')
     try:
      with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=.2)as response:break
     except Exception:time.sleep(.1)
    else:raise RuntimeError('Isolated server did not start')
    asyncio.run(main())
   finally:
    if PROCESS.poll()is None:
     PROCESS.stdin.write('shutdown\n');PROCESS.stdin.flush()
     try:PROCESS.wait(timeout=12)
     except subprocess.TimeoutExpired:PROCESS.kill();PROCESS.wait()
if __name__=='__main__':run_isolated()
