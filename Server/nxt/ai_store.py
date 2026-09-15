"""Persistent autonomous trainer ladder storage."""
from __future__ import annotations
import json,time

class AIStoreMixin:
 def migrate_ai(self,c,suffix,large,identity):
  c.execute(f"CREATE TABLE IF NOT EXISTS ai_trainers (id BIGINT PRIMARY KEY, username VARCHAR(20) NOT NULL UNIQUE, rating INTEGER NOT NULL, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, tier VARCHAR(16) NOT NULL, state_json {large} NOT NULL, personality_json {large} NOT NULL, next_action_at BIGINT NOT NULL, last_action_at BIGINT NOT NULL DEFAULT 0, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL)"+suffix)
  c.execute(f"CREATE TABLE IF NOT EXISTS competitive_profiles (account_id BIGINT PRIMARY KEY, rating INTEGER NOT NULL DEFAULT 1000, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, tier VARCHAR(16) NOT NULL DEFAULT 'Bronze', updated_at BIGINT NOT NULL, FOREIGN KEY (account_id) REFERENCES accounts(id))"+suffix)
  c.execute(f"CREATE TABLE IF NOT EXISTS ai_activity (id {identity}, actor_ai_id BIGINT NOT NULL, opponent_kind VARCHAR(8) NOT NULL, opponent_id BIGINT NOT NULL, result VARCHAR(16) NOT NULL, summary VARCHAR(255) NOT NULL, rating_before INTEGER NOT NULL, rating_after INTEGER NOT NULL, created_at BIGINT NOT NULL)"+suffix)
  c.execute(f"CREATE TABLE IF NOT EXISTS ai_rivals (account_id BIGINT NOT NULL, ai_id BIGINT NOT NULL, battles INTEGER NOT NULL DEFAULT 0, human_wins INTEGER NOT NULL DEFAULT 0, ai_wins INTEGER NOT NULL DEFAULT 0, rivalry INTEGER NOT NULL DEFAULT 0, last_battle_at BIGINT NOT NULL, PRIMARY KEY(account_id,ai_id), FOREIGN KEY (account_id) REFERENCES accounts(id))"+suffix)
  for stmt in ('CREATE INDEX idx_ai_trainers_rating ON ai_trainers(rating)','CREATE INDEX idx_ai_trainers_due ON ai_trainers(next_action_at)','CREATE INDEX idx_ai_activity_time ON ai_activity(created_at)','CREATE INDEX idx_ai_activity_actor ON ai_activity(actor_ai_id,created_at)','CREATE INDEX idx_ai_rivals_account ON ai_rivals(account_id,rivalry)'):
   try:c.execute(stmt)
   except Exception:pass
 def _bot(self,r):
  return {'id':int(r[0]),'username':r[1],'rating':int(r[2]),'wins':int(r[3]),'losses':int(r[4]),'tier':r[5],'state':json.loads(r[6]),'personality':json.loads(r[7]),'next_action_at':int(r[8]),'last_action_at':int(r[9])}
 def ai_count(self):
  with self.transaction() as c:c.execute('SELECT COUNT(*) FROM ai_trainers');return int(c.fetchone()[0])
 def ai_ids(self):
  with self.transaction() as c:c.execute('SELECT id FROM ai_trainers ORDER BY id');return [int(r[0]) for r in c.fetchall()]
 def ai_seed(self,records):
  if not records:return
  now=int(time.time())
  with self.transaction() as c:
   self.fence(c)
   for r in records:c.execute(self.sql('INSERT INTO ai_trainers(id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at,created_at,updated_at) VALUES(%s,%s,%s,0,0,%s,%s,%s,%s,0,%s,%s)'),(r['id'],r['username'],r['rating'],r['tier'],json.dumps(r['state'],separators=(',',':')),json.dumps(r['personality'],separators=(',',':')),r['next_action_at'],now,now))
 def ai_get(self,ai_id):
  with self.transaction() as c:c.execute(self.sql('SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at FROM ai_trainers WHERE id=%s'),(ai_id,));r=c.fetchone();return self._bot(r) if r else None
 def ai_due(self,now,limit):
  with self.transaction() as c:c.execute(self.sql('SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at FROM ai_trainers WHERE next_action_at<=%s ORDER BY next_action_at,id LIMIT %s'),(int(now),int(limit)));rows=c.fetchall()
  return [self._bot(r) for r in rows]
 def ai_candidates(self,ai_id,rating,limit=24):
  with self.transaction() as c:c.execute(self.sql('SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at FROM ai_trainers WHERE id<>%s AND rating BETWEEN %s AND %s ORDER BY ABS(rating-%s),id LIMIT %s'),(ai_id,max(0,int(rating)-350),int(rating)+350,int(rating),int(limit)));rows=c.fetchall()
  return [self._bot(r) for r in rows]
 def ai_recent_opponents(self,ai_id,since,limit=12):
  with self.transaction() as c:c.execute(self.sql("SELECT opponent_id FROM ai_activity WHERE actor_ai_id=%s AND opponent_kind='ai' AND created_at>=%s ORDER BY created_at DESC LIMIT %s"),(ai_id,int(since),int(limit)));return [int(r[0]) for r in c.fetchall()]
 def ai_commit_pair(self,a,b,event_a,event_b):
  now=int(time.time())
  with self.transaction() as c:
   self.fence(c)
   for bot in (a,b):c.execute(self.sql('UPDATE ai_trainers SET rating=%s,wins=%s,losses=%s,tier=%s,state_json=%s,next_action_at=%s,last_action_at=%s,updated_at=%s WHERE id=%s'),(bot['rating'],bot['wins'],bot['losses'],bot['tier'],json.dumps(bot['state'],separators=(',',':')),bot['next_action_at'],now,now,bot['id']))
   for ev in (event_a,event_b):c.execute(self.sql('INSERT INTO ai_activity(actor_ai_id,opponent_kind,opponent_id,result,summary,rating_before,rating_after,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)'),(ev['actor'],ev['kind'],ev['opponent'],ev['result'],ev['summary'][:255],ev['before'],ev['after'],now))
   c.execute(self.sql('DELETE FROM ai_activity WHERE created_at<%s'),(now-3888000,))
 def ai_save_single(self,bot):
  now=int(time.time())
  with self.transaction() as c:self.fence(c);c.execute(self.sql('UPDATE ai_trainers SET state_json=%s,next_action_at=%s,last_action_at=%s,updated_at=%s WHERE id=%s'),(json.dumps(bot['state'],separators=(',',':')),bot['next_action_at'],now,now,bot['id']))
 def ai_rebalance_world(self,records):
  if not records:return
  now=int(time.time())
  with self.transaction() as c:
   self.fence(c)
   for bot in records:
    c.execute(self.sql('UPDATE ai_trainers SET state_json=%s,personality_json=%s,updated_at=%s WHERE id=%s'),(json.dumps(bot['state'],separators=(',',':')),json.dumps(bot['personality'],separators=(',',':')),now,bot['id']))
 def ai_save_world_states(self,records):
  if not records:return
  now=int(time.time())
  with self.transaction() as c:
   self.fence(c)
   for bot in records:
    c.execute(self.sql('UPDATE ai_trainers SET state_json=%s,updated_at=%s WHERE id=%s'),(json.dumps(bot['state'],separators=(',',':')),now,bot['id']))
 def ai_commit_field(self,bot,event):
  now=int(time.time())
  with self.transaction() as c:
   self.fence(c)
   c.execute(self.sql('UPDATE ai_trainers SET state_json=%s,personality_json=%s,next_action_at=%s,last_action_at=%s,updated_at=%s WHERE id=%s'),(json.dumps(bot['state'],separators=(',',':')),json.dumps(bot['personality'],separators=(',',':')),bot['next_action_at'],now,now,bot['id']))
   c.execute(self.sql('INSERT INTO ai_activity(actor_ai_id,opponent_kind,opponent_id,result,summary,rating_before,rating_after,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)'),(bot['id'],event.get('kind','wild'),int(event.get('opponent',0)),event.get('result','training')[:16],event.get('summary','Autonomous field training.')[:255],bot['rating'],bot['rating'],now))
   c.execute(self.sql('DELETE FROM ai_activity WHERE created_at<%s'),(now-3888000,))
 def competitive_profile(self,account_id):
  now=int(time.time())
  with self.transaction() as c:
   c.execute(self.sql('SELECT rating,wins,losses,tier FROM competitive_profiles WHERE account_id=%s'),(account_id,));r=c.fetchone()
   if r:return {'rating':int(r[0]),'wins':int(r[1]),'losses':int(r[2]),'tier':r[3]}
   self.fence(c);c.execute(self.sql("INSERT INTO competitive_profiles(account_id,rating,wins,losses,tier,updated_at) VALUES(%s,1000,0,0,'Bronze',%s)"),(account_id,now));return {'rating':1000,'wins':0,'losses':0,'tier':'Bronze'}
 def ai_ranked_human_result(self,account_id,ai_id,human_won,human_after,human_tier,ai_before,ai_after,ai_tier,ai_state,summary):
  now=int(time.time())
  with self.transaction() as c:
   self.fence(c)
   if self.mysql:c.execute(self.sql('INSERT INTO competitive_profiles(account_id,rating,wins,losses,tier,updated_at) VALUES(%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE rating=VALUES(rating),wins=wins+VALUES(wins),losses=losses+VALUES(losses),tier=VALUES(tier),updated_at=VALUES(updated_at)'),(account_id,human_after,1 if human_won else 0,0 if human_won else 1,human_tier,now))
   else:c.execute(self.sql('INSERT INTO competitive_profiles(account_id,rating,wins,losses,tier,updated_at) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(account_id) DO UPDATE SET rating=excluded.rating,wins=competitive_profiles.wins+excluded.wins,losses=competitive_profiles.losses+excluded.losses,tier=excluded.tier,updated_at=excluded.updated_at'),(account_id,human_after,1 if human_won else 0,0 if human_won else 1,human_tier,now))
   c.execute(self.sql('UPDATE ai_trainers SET rating=%s,wins=wins+%s,losses=losses+%s,tier=%s,state_json=%s,last_action_at=%s,next_action_at=%s,updated_at=%s WHERE id=%s'),(ai_after,0 if human_won else 1,1 if human_won else 0,ai_tier,json.dumps(ai_state,separators=(',',':')),now,now+120,now,ai_id))
   c.execute(self.sql("INSERT INTO ai_activity(actor_ai_id,opponent_kind,opponent_id,result,summary,rating_before,rating_after,created_at) VALUES(%s,'human',%s,%s,%s,%s,%s,%s)"),(ai_id,account_id,'loss' if human_won else 'win',summary[:255],ai_before,ai_after,now))
   if self.mysql:c.execute(self.sql('INSERT INTO ai_rivals(account_id,ai_id,battles,human_wins,ai_wins,rivalry,last_battle_at) VALUES(%s,%s,1,%s,%s,1,%s) ON DUPLICATE KEY UPDATE battles=battles+1,human_wins=human_wins+VALUES(human_wins),ai_wins=ai_wins+VALUES(ai_wins),rivalry=rivalry+1,last_battle_at=VALUES(last_battle_at)'),(account_id,ai_id,1 if human_won else 0,0 if human_won else 1,now))
   else:c.execute(self.sql('INSERT INTO ai_rivals(account_id,ai_id,battles,human_wins,ai_wins,rivalry,last_battle_at) VALUES(%s,%s,1,%s,%s,1,%s) ON CONFLICT(account_id,ai_id) DO UPDATE SET battles=ai_rivals.battles+1,human_wins=ai_rivals.human_wins+excluded.human_wins,ai_wins=ai_rivals.ai_wins+excluded.ai_wins,rivalry=ai_rivals.rivalry+1,last_battle_at=excluded.last_battle_at'),(account_id,ai_id,1 if human_won else 0,0 if human_won else 1,now))
 def ai_dashboard(self,account_id,activity_limit=60,ladder_limit=100,rival_limit=20):
  profile=self.competitive_profile(account_id)
  with self.transaction() as c:
   # Pull both populations, then merge them into one authoritative competitive ladder.
   c.execute(self.sql('SELECT id,username,rating,wins,losses,tier,state_json,last_action_at FROM ai_trainers ORDER BY rating DESC,wins DESC,id LIMIT %s'),(ladder_limit,));ai_ladder=c.fetchall()
   c.execute(self.sql('SELECT a.id,a.username,p.rating,p.wins,p.losses,p.tier,p.updated_at FROM competitive_profiles p JOIN accounts a ON a.id=p.account_id ORDER BY p.rating DESC,p.wins DESC,a.id LIMIT %s'),(ladder_limit,));human_ladder=c.fetchall()
   c.execute(self.sql('SELECT a.id,a.username,a.rating,a.wins,a.losses,a.tier,r.battles,r.human_wins,r.ai_wins,r.rivalry,r.last_battle_at,a.state_json FROM ai_rivals r JOIN ai_trainers a ON a.id=r.ai_id WHERE r.account_id=%s ORDER BY r.rivalry DESC,a.rating DESC LIMIT %s'),(account_id,rival_limit));rivals=c.fetchall()
   c.execute(self.sql('SELECT x.id,x.actor_ai_id,a.username,x.opponent_kind,x.opponent_id,x.result,x.summary,x.rating_before,x.rating_after,x.created_at FROM ai_activity x JOIN ai_trainers a ON a.id=x.actor_ai_id ORDER BY x.created_at DESC,x.id DESC LIMIT %s'),(activity_limit,));activity=c.fetchall()
   c.execute('SELECT COUNT(*),AVG(rating),MAX(rating),SUM(wins),SUM(losses) FROM ai_trainers');stats=c.fetchone()
   c.execute(self.sql('SELECT COUNT(*) FROM ai_trainers WHERE rating>%s'),(profile['rating'],));above_ai=int(c.fetchone()[0])
   c.execute(self.sql('SELECT COUNT(*) FROM competitive_profiles WHERE account_id<>%s AND rating>%s'),(account_id,profile['rating']));above_human=int(c.fetchone()[0]);human_rank=above_ai+above_human+1
  def state_summary(raw):
   s=json.loads(raw);lead=next((m for m in s.get('creatures',[]) if s.get('party') and m['uid']==s['party'][0]),None);return {'map':s.get('map'),'collection':len(s.get('creatures',[])),'partySize':len(s.get('party',[])),'leadSpecies':lead['species'] if lead else None,'leadLevel':lead['level'] if lead else 0}
  ladder=[]
  for r in ai_ladder:ladder.append({'id':int(r[0]),'username':r[1],'rating':int(r[2]),'wins':int(r[3]),'losses':int(r[4]),'tier':r[5],**state_summary(r[6]),'lastAction':int(r[7]),'autonomous':True})
  for r in human_ladder:ladder.append({'id':int(r[0]),'username':r[1],'rating':int(r[2]),'wins':int(r[3]),'losses':int(r[4]),'tier':r[5],'map':None,'collection':None,'partySize':None,'leadSpecies':None,'leadLevel':0,'lastAction':int(r[6]),'autonomous':False})
  ladder.sort(key=lambda x:(-x['rating'],-x['wins'],x['username'].lower(),x['id']));ladder=ladder[:int(ladder_limit)]
  return {'population':int(stats[0] or 0),'averageRating':round(float(stats[1] or 0),1),'topRating':int(stats[2] or 0),'totalWins':int(stats[3] or 0),'totalLosses':int(stats[4] or 0),'human':{**profile,'rank':human_rank},'ladder':ladder,'rivals':[{'id':int(r[0]),'username':r[1],'rating':int(r[2]),'wins':int(r[3]),'losses':int(r[4]),'tier':r[5],'battles':int(r[6]),'humanWins':int(r[7]),'aiWins':int(r[8]),'rivalry':int(r[9]),'lastBattle':int(r[10]),**state_summary(r[11])} for r in rivals],'activity':[{'id':int(r[0]),'actorId':int(r[1]),'actor':r[2],'opponentKind':r[3],'opponentId':int(r[4]),'result':r[5],'summary':r[6],'before':int(r[7]),'after':int(r[8]),'time':int(r[9])} for r in activity]}
 def ai_world_snapshot(self):
  with self.transaction() as c:c.execute('SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at FROM ai_trainers ORDER BY id');rows=c.fetchall()
  return [self._bot(r) for r in rows]
