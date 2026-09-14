"""Strict, typed configuration. Missing or unsafe values fail before listening."""
from __future__ import annotations
import configparser,os,re
from .admin_policy import ConsolePolicy
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class Settings:
 root:Path
 config:configparser.ConfigParser
 max_players:int
 tick_hz:int
 step_ms:int
 interest_radius:int
 save_seconds:int
 encounter_chance:float
 max_owned:int
 port:int
 bind_ip:str
 @classmethod
 def load(cls,path:Path):
  c=configparser.ConfigParser(interpolation=None)
  if not c.read(path,encoding='utf-8'):raise ValueError(f'Missing config: {path}')
  def integer(s,k,lo,hi):
   v=c.getint(s,k)
   if not lo<=v<=hi:raise ValueError(f'{s}.{k} must be {lo}..{hi}')
   return v
  ConsolePolicy.load(c)
  n=integer('world','max_players',1,1000);tick=integer('world','tick_hz',2,30);step=integer('world','step_ms',100,1000);radius=integer('world','interest_radius',8,64);save=integer('world','save_interval_seconds',5,300);owned=integer('world','max_owned_pokemon',6,720);port=integer('network','port',1024,65535)
  chance=c.getfloat('world','encounter_chance')
  if not 0<=chance<=1:raise ValueError('encounter_chance must be 0..1')
  if c.get('database','backend') not in ('mysql','sqlite'):raise ValueError('database.backend must be mysql or sqlite')
  re.compile(c.get('security','allowed_origin_pattern'))
  if not c.getboolean('network','tls') and not c.getboolean('network','allow_insecure_lan'):raise ValueError('Enable TLS or explicitly allow private-LAN testing')
  return cls(path.resolve().parent,c,n,tick,step,radius,save,chance,owned,port,c.get('network','bind_ip'))
 def get(self,s,k):return self.config.get(s,k)
 def int(self,s,k):return self.config.getint(s,k)
 def flag(self,s,k):return self.config.getboolean(s,k)
 def path(self,s,k):return self.root/self.get(s,k)
 def password(self):return os.environ.get(self.get('database','password_environment'),self.get('database','password'))
