"""Non-mutating configuration/content/dependency check. Does not create tables."""
from pathlib import Path
import importlib,sys
from nxt.config import Settings
from nxt.content import Content
root=Path(__file__).resolve().parent
try:
 s=Settings.load(root/'config.ini');c=Content(root/'data/world.json')
 print('Pokemon NXT MMO configuration check\n')
 print('Python:',sys.version.split()[0])
 for name in ('aiohttp','pymysql'):
  try:m=importlib.import_module(name);print(name+':',getattr(m,'__version__','installed'))
  except ImportError:print(name+': MISSING - run dependency setup')
 print('Content pack:',c.pack,'| Maps:',len(c.maps),'| Catalog:',len(c.species));print('Bind:',s.bind_ip+':'+str(s.port),'| Cap:',s.max_players)
 print('Database backend:',s.get('database','backend'),'| No credentials displayed')
 if s.get('database','backend')=='mysql':
  if s.password()=='CHANGE_ME_WITH_SETUP':print('MySQL: NOT CONFIGURED. Run 2 - Configure MySQL.cmd.')
  else:
   import pymysql
   ca=str(s.path('database','ssl_ca').resolve()) if s.get('database','ssl_ca') else None
   connection=pymysql.connect(ssl_ca=ca,ssl_verify_cert=bool(ca),ssl_verify_identity=bool(ca),host=s.get('database','host'),port=s.int('database','port'),user=s.get('database','user'),password=s.password(),database=s.get('database','database'),connect_timeout=5)
   with connection.cursor() as cur:cur.execute('SELECT 1');print('MySQL login: OK')
   connection.close()
 print('TLS:',s.flag('network','tls'))
 if not s.flag('network','tls'):print('PRIVATE LAN ONLY: internet peers are rejected until TLS is configured.')
 print('\nConfiguration and content parsing completed.')
except Exception as e:print('CHECK FAILED:',e);sys.exit(1)
