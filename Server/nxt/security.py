"""Authentication, bounded input and monotonic token buckets."""
from __future__ import annotations
import base64,hashlib,hmac,re,secrets,time
class RequestError(Exception):
 """A safe message that may be sent to the requesting client."""
def require(condition,message):
 if not condition:raise RequestError(message)
def integer(value,lo,hi,label='Value'):
 require(isinstance(value,int) and not isinstance(value,bool) and lo<=value<=hi,f'{label} must be an integer between {lo} and {hi}.');return value
def credentials(username,password):
 require(isinstance(username,str) and re.fullmatch(r'[A-Za-z0-9_]{3,20}',username) is not None,'Username must be 3-20 letters, numbers or underscores.')
 require(isinstance(password,str) and 10<=len(password)<=128 and len(password.encode())<=512,'Password must contain 10-128 characters.')
 return username,password
def password_hash(password):
 salt=secrets.token_bytes(16)
 key=hashlib.scrypt(password.encode(),salt=salt,n=131072,r=8,p=1,maxmem=268435456,dklen=32)
 return 'scrypt$131072$8$1$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(key).decode()
def password_verify(password,encoded):
 try:
  method,n,r,p,salt,key=encoded.split('$')
  if (method,n,r,p)!=('scrypt','131072','8','1'):return False
  actual=hashlib.scrypt(password.encode(),salt=base64.b64decode(salt),n=int(n),r=int(r),p=int(p),maxmem=268435456,dklen=32)
  return hmac.compare_digest(actual,base64.b64decode(key))
 except (ValueError,TypeError):return False
class Bucket:
 def __init__(self,capacity,seconds):self.capacity=capacity;self.rate=capacity/seconds;self.tokens=float(capacity);self.at=time.monotonic()
 def take(self,amount=1):
  now=time.monotonic();self.tokens=min(self.capacity,self.tokens+(now-self.at)*self.rate);self.at=now
  if self.tokens<amount:return False
  self.tokens-=amount;return True
