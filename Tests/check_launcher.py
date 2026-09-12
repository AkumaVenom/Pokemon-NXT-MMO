import subprocess,re,urllib.request,urllib.error,json,time,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if len(sys.argv)!=2:raise SystemExit('Usage: python Tests/check_launcher.py PATH_TO_COMPILED_LAUNCHER')
p=subprocess.Popen([sys.argv[1],'--root',str(root/'Client'),'--headless'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
 line=p.stdout.readline();base=line.strip().split('app: ')[1];results={}
 def request(path,method='GET',headers=None):
  try:
   with urllib.request.urlopen(urllib.request.Request(base+path,method=method,headers=headers or {}),timeout=3)as r:return r.status,dict(r.headers),r.read()
  except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
 status,headers,body=request('/');results['index_served']=status==200 and b'Pokemon NXT' in body;results['content_policy']=headers.get('Content-Security-Policy','').startswith("default-src 'self'");results['no_sniff']=headers.get('X-Content-Type-Options')=='nosniff';results['frame_denial']=headers.get('X-Frame-Options')=='DENY'
 status,_,body=request('/bootstrap');cfg=json.loads(body);results['bootstrap_no_secrets']=status==200 and cfg['endpoint']=='ws://127.0.0.1:7777/world' and not any(x in str(cfg).lower() for x in ['password','mysql','database'])
 results['unexpected_host_blocked']=request('/',headers={'Host':'untrusted.example'})[0]==403
 results['server_config_inaccessible']=request('/Server/config.ini')[0]==404
 results['directory_listing_disabled']=request('/assets/maps')[0]==404
 results['traversal_blocked']=request('/%2e%2e/Server/config.ini')[0]==404
 results['heartbeat_requires_origin_and_token']=request('/heartbeat',method='POST')[0]==403
 results['heartbeat_accepted']=request('/heartbeat?token='+cfg['nonce'],method='POST',headers={'Origin':base})[0]==204
 results['js_served_as_module']=request('/app.js')[0]==200
 results['extracted_map_served']=request('/assets/maps/kanto/3_0.png')[0]==200
 print(json.dumps(results,indent=2));(root/'Tests/launcher_results.json').write_text(json.dumps(results,indent=2));assert all(results.values())
finally:p.terminate();p.wait(timeout=5)
