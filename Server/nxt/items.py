"""Authoritative item mechanics on detached character/battle snapshots.

Inventory IDs remain the 0.6.9 persistence contract. Held items additionally
carry a source namespace: Sigma reuses FireRed IDs for unrelated objects.
World owns locking, request receipts, database commits, and publication. This
module has no network or database access and never accepts client-supplied HP,
item effects, prices, species compatibility, RNG results, or stat modifiers.
"""
from __future__ import annotations
import copy
from .security import require, integer

STATS = ('HP','Attack','Defense','Speed','Special Attack','Special Defense')
HELD_FIELDS = ('heldItemId','heldItemSource','heldItemKey')
# Existing native FireRed holders remain correctly namespaced. These modifiers
# complement the original engine's berry/Focus Band/Choice Band handling.
KANTO_TYPE_ITEMS = {188:6,199:8,203:4,204:5,205:12,206:17,207:1,208:13,
                    209:11,210:2,211:3,212:15,213:7,214:14,215:10,216:16,217:0}
KANTO_NAMES = {44:'Berry Juice',133:'Cheri Berry',134:'Chesto Berry',135:'Pecha Berry',136:'Rawst Berry',137:'Aspear Berry',138:'Leppa Berry',139:'Oran Berry',140:'Persim Berry',141:'Lum Berry',142:'Sitrus Berry',179:'BrightPowder',180:'White Herb',181:'Macho Brace',182:'Exp. Share',183:'Quick Claw',184:'Soothe Bell',185:'Mental Herb',186:'Choice Band',187:'King’s Rock',188:'SilverPowder',189:'Amulet Coin',190:'Cleanse Tag',191:'Soul Dew',192:'DeepSeaTooth',193:'DeepSeaScale',194:'Smoke Ball',195:'Everstone',196:'Focus Band',197:'Lucky Egg',198:'Scope Lens',199:'Metal Coat',200:'Leftovers',201:'Dragon Scale',202:'Light Ball',203:'Soft Sand',204:'Hard Stone',205:'Miracle Seed',206:'BlackGlasses',207:'Black Belt',208:'Magnet',209:'Mystic Water',210:'Sharp Beak',211:'Poison Barb',212:'NeverMeltIce',213:'Spell Tag',214:'TwistedSpoon',215:'Charcoal',216:'Dragon Fang',217:'Silk Scarf',218:'Up-Grade',219:'Shell Bell',222:'Lucky Punch',223:'Metal Powder',224:'Thick Club',225:'Stick'}


def held_snapshot(mon):
    return {k:copy.deepcopy(mon[k]) for k in HELD_FIELDS if k in mon}


def replace_held(mon, value):
    for k in HELD_FIELDS:mon.pop(k,None)
    mon.update(copy.deepcopy(value));mon.setdefault('heldItemId',0)


class ItemSystem:
    def __init__(self, content):
        self.c=content
        self.native_keys={}
        for key,item in content.items.items():
            sid=item.get('sourceId')
            if type(sid) is int:self.native_keys[(item.get('source','johto'),sid)]=key

    def definition(self,key):
        require(isinstance(key,str) and key in self.c.items,'Select a valid item.')
        return self.c.items[key]

    def rule(self,key):
        item=self.definition(key)
        # Compatibility with small test/extension content packs predating the
        # reviewed sidecar. The shipped pack never uses these fallbacks.
        if 'mechanics' in item:return item['mechanics']
        if 'heal' in item:return dict(effect='medicine',field=True,battle=True,target='pokemon',heal=item['heal'])
        if 'capture' in item:return dict(effect='capture',battle=True,ballRule=key,capture=item['capture'])
        if item.get('evolutionStone'):return dict(effect='evolution',field=True,target='pokemon')
        return dict(effect='unavailable')

    def ensure_mon(self,mon):
        mon.setdefault('evs',[0]*6)
        mon.setdefault('heldItemSource',self.c.species[mon['species']].get('source','kanto'))
        # Absent ppUps is canonically zero. Do not rewrite old chosen move
        # slots or trigger another login migration after normal move learning.
        return mon

    def migrate(self,state):
        candidate=copy.deepcopy(state)
        for mon in candidate['creatures']:self.ensure_mon(mon)
        candidate.setdefault('repelSteps',0)
        candidate.setdefault('coins',0)
        candidate.setdefault('pokeblocks',[])
        candidate.setdefault('heldReserve',{})
        return candidate

    def held_source(self,mon):
        return mon.get('heldItemSource',self.c.species[mon['species']].get('source','kanto'))

    def held_key(self,mon):
        key=mon.get('heldItemKey');sid=mon.get('heldItemId',0);source=self.held_source(mon)
        if key in self.c.items and self.c.items[key].get('sourceId')==sid and self.c.items[key].get('source','johto')==source:return key
        return self.native_keys.get((source,sid))

    def held(self,mon):
        sid=mon.get('heldItemId',0)
        if not sid:return {}
        if self.held_source(mon)=='kanto':
            rule={'legacyCode':sid}
            if sid in KANTO_TYPE_ITEMS:rule.update(boostType=KANTO_TYPE_ITEMS[sid],boost=[11,10])
            if sid==181:rule.update(stats={'3':[1,2]},evMultiplier=2)
            if sid==186:rule['choice']=True
            if sid==197:rule['exp']=[3,2]
            if sid==194:rule['alwaysRun']=True
            return rule
        key=self.held_key(mon)
        return copy.deepcopy(self.rule(key).get('held',{})) if key else {}

    def held_code(self,mon):return int(self.held(mon).get('legacyCode',0))

    def held_label(self,mon):
        sid=mon.get('heldItemId',0)
        if not sid:return None
        key=self.held_key(mon)
        if key:return self.c.items[key]['name']
        if self.held_source(mon)=='kanto' and sid in KANTO_NAMES:return KANTO_NAMES[sid]
        return f'{self.held_source(mon).title()} native item #{sid}'

    def public_mon(self,mon):
        ability_slot=self.ability_slot(mon);abilities=self.c.species[mon['species']].get('abilities',[0,0])
        return dict(evs=list(mon.get('evs',[0]*6)),friendship=int(mon.get('friendship',70)),
                    abilitySlot=ability_slot,abilityId=abilities[ability_slot] if ability_slot<len(abilities) else 0,
                    heldItemId=mon.get('heldItemId',0),heldItemKey=self.held_key(mon),heldItemName=self.held_label(mon),
                    heldItemSource=self.held_source(mon),captureBall=mon.get('captureBall'),
                    condition=copy.deepcopy(mon.get('condition',{})))

    def ability_slot(self,mon):
        abilities=self.c.species[mon['species']].get('abilities',[0,0])
        if len(abilities)<2 or not abilities[1]:return 0
        return mon.get('abilitySlot',int(mon.get('personality',0))&1)&1

    def multiplier(self,key,battle,side):
        rule=self.rule(key);kind=rule.get('ballRule',key);enemy=battle.mon(1-side)
        if kind=='timerball':return min(4,(10+max(0,battle.turn-1))/10)
        if kind=='netball':return 3 if set(battle.types(enemy)) & {6,11} else 1
        if kind=='diveball':return 3.5 if battle.terrain=='underwater' else 1
        if kind=='nestball':return max(1,(40-enemy['level'])/10)
        if kind=='repeatball':return 3 if enemy['species'] in battle.caught_species[side] else 1
        if kind=='fastball':return 4 if self.c.species[enemy['species']]['baseStats'][3]>=100 else 1
        return self.c.items[key].get('capture',rule.get('capture',1))

    def increase_friendship(self,mon,amount):
        if amount>0 and mon.get('captureBall')=='luxuryball':amount+=1
        if amount>0 and self.held_code(mon)==184:amount=amount*3//2
        mon['friendship']=max(0,min(255,int(mon.get('friendship',70))+amount))

    def positive_friendship(self,mon):
        value=int(mon.get('friendship',70));self.increase_friendship(mon,5 if value<100 else 3 if value<200 else 2)

    def _bitter(self,mon,rule):
        values=rule.get('bitter')
        if values:self.increase_friendship(mon,values[1] if mon.get('friendship',70)>=200 else values[0])

    def _owned_item(self,inventory,key):
        self.definition(key);require(inventory.get(key,0)>0,'You have none of that item.')

    def _move_slot(self,mon,data):
        slot=integer(data.get('slot'),0,3,'Move slot');require(slot<len(mon['moves']),'Select an existing move.')
        if data.get('expectedMove') is not None:require(data['expectedMove']==mon['moves'][slot]['id'],'That move slot changed. Reopen the item menu.')
        return slot

    def apply_mon(self,key,original,data,*,battle=False,volatile=None):
        """Validate and calculate a single-target effect without changing inputs."""
        rule=self.rule(key);effect=rule['effect'];mon=copy.deepcopy(original);self.ensure_mon(mon)
        vol=copy.deepcopy(volatile or {});before=copy.deepcopy((mon,vol));maximum=self.c.stats(mon)[0]
        if effect=='medicine':
            require(mon['hp']>0,'That Pokémon has fainted. Use a revival item first.')
            if rule.get('heal'):mon['hp']=min(maximum,mon['hp']+rule['heal'])
            cure=rule.get('cure',[])
            if mon.get('status') and ('all' in cure or mon['status'] in cure):
                mon['status']='';mon['sleep']=0;vol.pop('toxicCounter',None);vol.pop('nightmare',None)
            if 'all' in cure or 'confusion' in cure:vol.pop('confusionTurns',None)
        elif effect=='revive':
            require(mon['hp']==0,'Revival items require a fainted Pokémon.')
            mon['hp']=max(1,int(maximum*rule['fraction']));mon['status']='';mon['sleep']=0
        elif effect=='pp':
            slots=range(len(mon['moves'])) if rule.get('allMoves') else [self._move_slot(mon,data)]
            for slot in slots:
                move=mon['moves'][slot];move['pp']=min(self.c.pp_max(move),move['pp']+rule['pp'])
        elif effect=='ppboost':
            require(not battle,'PP upgrades are used outside battle.')
            slot=self._move_slot(mon,data);move=mon['moves'][slot];base=self.c.moves[str(move['id'])]['pp']
            require(move['id']!=166 and base>1,'That move cannot receive PP upgrades.')
            require(move.get('ppUps',0)<3,'That move already has maximum PP upgrades.')
            old=self.c.pp_max(move);move['ppUps']=min(3,move.get('ppUps',0)+rule['increments']);move['pp']+=self.c.pp_max(move)-old
        elif effect=='vitamin':
            require(not battle,'Vitamins are used outside battle.');index=rule['stat'];evs=mon['evs']
            gain=max(0,min(10,100-evs[index],510-sum(evs)))
            require(gain>0,'That vitamin cannot add EVs: its stat cap is 100 and the total cap is 510.')
            oldhp=maximum;evs[index]+=gain;mon['hp']=min(self.c.stats(mon)[0],mon['hp']+self.c.stats(mon)[0]-oldhp) if mon['hp']>0 else 0
            self.positive_friendship(mon)
        elif effect=='level':
            require(not battle,'Rare Candy is used outside battle.');require(mon['level']<100,'That Pokémon is already level 100.')
            oldhp=mon['hp'];growth=self.c.species[mon['species']]['growth']
            self.c.gain_xp(mon,self.c.xp(mon['level']+1,growth)-mon['exp'])
            if oldhp==0:mon['hp']=max(1,self.c.stats(mon)[0]-maximum);mon['status']='';mon['sleep']=0
            self.positive_friendship(mon)
        elif effect=='ability':
            require(not battle,'A Skill Capsule is used outside battle.')
            abilities=self.c.species[mon['species']].get('abilities',[0,0])
            require(len(abilities)>=2 and abilities[0] and abilities[1] and abilities[0]!=abilities[1],'This species does not have two different regular abilities.')
            target=1-self.ability_slot(mon)
            require(1 <= abilities[target] <= 77,'The destination ability is outside this battle engine’s supported native ability set. The capsule was not consumed.')
            mon['abilitySlot']=target
        else:require(False,'This item uses a different action. Choose its displayed Bag action.')
        require((mon,vol)!=before,'That item would have no effect. Nothing was used.')
        self._bitter(mon,rule)
        return mon,vol

    def battle_action(self,battle,side,key,data,*,preview=False):
        self._owned_item(battle.items[side],key);rule=self.rule(key)
        require(rule.get('battle') and rule['effect'] not in ('capture','tera'),'That item cannot be used with this battle action.')
        active=battle.mon(side);effect=rule['effect'];target=active
        if effect in ('xstat','direhit','guardspec'):
            require(data.get('uid') in (None,active['uid']),'This item is only used on the active Pokémon.')
            if effect=='xstat':require(battle.tiers(active)[rule['stat']]<6,'That stat is already at its maximum battle stage.')
            elif effect=='direhit':require(not battle.vol(active).get('focusEnergy'),'Critical-hit focus is already active.')
            else:require(battle.side[side]['mist']<=0,'Guard Spec. protection is already active.')
            if not preview:
                if effect=='xstat':battle._change_stage(side,rule['stat'],1,source_side=side)
                elif effect=='direhit':battle.vol(active)['focusEnergy']=True
                else:battle.side[side]['mist']=5
        elif effect=='pokeflute':
            targets=[battle.mon(s) for s in (0,1) if battle.mon(s)['hp']>0 and battle.mon(s)['status']=='sleep']
            require(bool(targets),'Neither active Pokémon is asleep. Nothing was used.')
            if not preview:
                for mon in targets:mon['status']='';mon['sleep']=0;battle.vol(mon).pop('nightmare',None)
        else:
            uid=data.get('uid',active['uid']);require(isinstance(uid,str),'Select a party Pokémon.')
            target=next((m for m in battle.rosters[side] if m['uid']==uid),None)
            require(target is not None,'That Pokémon is not in your battle party.')
            if effect=='pp' and battle.vol(target).get('transformed'):require(False,'Switch out of Transform before restoring the original move’s PP.')
            result,vol=self.apply_mon(key,target,data,battle=True,volatile=battle.vol(target))
            if not preview:target.clear();target.update(result);battle.volatile[target['uid']]=vol
        if not preview:
            if not rule.get('reusable'):battle.items[side][key]-=1
            battle.logs.append(f'{battle.names[side]} used {self.c.items[key]["name"]}'+(f' on {battle.name(target)}.' if effect!='pokeflute' else '. Sleeping active Pokémon woke up.'))
            battle.audio('recover',side,species=target['species'],item=key)

    def evolve_with_item(self,state,key,data):
        mon=self.c.growth.owned(state,data.get('uid'));rule=self.rule(key);token=rule.get('evolutionAlias',key)
        options=[o for o in self.c.growth.options(mon) if o.get('item')==token and not o.get('deferred')]
        require(options,'That Pokémon has no available evolution using this item.')
        target=data.get('target');require(isinstance(target,str) and any(o['target']==target for o in options),'Choose and confirm an available evolution.')
        if token==key:return self.c.growth.evolve(state,mon['uid'],target,item=token)
        # Alias substitution happens only in the detached transaction. It does
        # not grant a real extra item or change the owner's original token stack.
        candidate=copy.deepcopy(state);original=candidate['items'].get(token,0)
        candidate['items'][key]-=1;candidate['items'][token]=original+1
        candidate=self.c.growth.evolve(candidate,mon['uid'],target,item=token)
        if original==0:candidate['items'].pop(token,None)
        else:candidate['items'][token]=original
        return candidate

    def field_use(self,state,key,data):
        self._owned_item(state['items'],key);rule=self.rule(key)
        require(rule.get('field'),'Use this item through its battle, held-item, or sale action.')
        candidate=copy.deepcopy(state);effect=rule['effect']
        if effect=='evolution':return self.evolve_with_item(candidate,key,data)
        if effect=='machine':
            mon=self.c.growth.owned(candidate,data.get('uid'));move=rule['move']
            require(key in self.c.species[mon['species']].get('machines',[]),'This Pokémon is not compatible with that Sigma machine.')
            require(move not in [m['id'] for m in mon['moves']],'That Pokémon already knows this move.')
            slot=integer(data.get('slot'),0,3,'Move slot');require(slot<=len(mon['moves']),'Choose an existing move or the next empty slot.')
            if slot<len(mon['moves']) and data.get('expectedMove') is not None:require(data['expectedMove']==mon['moves'][slot]['id'],'That move slot changed. Reopen the teaching menu.')
            value={'id':move,'pp':self.c.moves[str(move)]['pp'],'ppUps':0}
            if slot==len(mon['moves']):mon['moves'].append(value)
            else:mon['moves'][slot]=value
            mon['pendingLearn']=[p for p in mon.get('pendingLearn',[]) if p.get('move')!=move]
        elif effect in ('medicine','revive','pp','ppboost','vitamin','level','ability'):
            original=self.c.growth.owned(candidate,data.get('uid'));result,_=self.apply_mon(key,original,data)
            original.clear();original.update(result)
        elif effect in ('sacredash','pokeflute'):
            party=[m for m in candidate['creatures'] if m['uid'] in candidate['party']]
            targets=[m for m in party if m['hp']==0] if effect=='sacredash' else [m for m in party if m['hp']>0 and m['status']=='sleep']
            require(targets,'No current party member needs that item. Nothing was used.')
            for mon in targets:
                if effect=='sacredash':mon['hp']=self.c.stats(mon)[0]
                mon['status']='';mon['sleep']=0
        elif effect=='repel':
            require(candidate.get('repelSteps',0)<=0,'A Repel is already active. Wait until it wears off.')
            candidate['repelSteps']=rule['steps']
        else:require(False,'Choose this item’s dedicated service or field interaction.')
        if not rule.get('reusable'):candidate['items'][key]-=1
        return candidate

    def _return_held(self,candidate,mon):
        if not mon.get('heldItemId'):return
        key=self.held_key(mon)
        if key:
            require(candidate['items'].get(key,0)<999,'Make room in the Bag for the currently held item first.')
            candidate['items'][key]=candidate['items'].get(key,0)+1
        else:
            # Preserve older source-specific objects losslessly instead of
            # converting (for example) FireRed Berry Juice into Sigma Up-Grade.
            source=self.held_source(mon);sid=mon['heldItemId'];token=f'{source}:{sid}'
            reserve=candidate.setdefault('heldReserve',{});entry=reserve.get(token,{'id':sid,'source':source,'name':self.held_label(mon),'quantity':0})
            require(entry['quantity']<999,'Make room for this source-specific held item first.')
            entry['quantity']+=1;reserve[token]=entry
        replace_held(mon,{'heldItemId':0})

    def equip(self,state,data,*,take=False):
        candidate=copy.deepcopy(state);mon=self.c.growth.owned(candidate,data.get('uid'))
        if data.get('expectedHeld') is not None:require(data['expectedHeld']==mon.get('heldItemId',0),'The held item changed. Reopen this Pokémon’s summary.')
        if take:
            require(mon.get('heldItemId',0)>0,'This Pokémon is not holding an item.')
            self._return_held(candidate,mon);return candidate
        reserve_key=data.get('reserve')
        if reserve_key is not None:
            require(isinstance(reserve_key,str),'Select a source-specific held item.')
            entry=candidate.get('heldReserve',{}).get(reserve_key)
            require(entry and entry['quantity']>0,'That source-specific held item is unavailable.')
            # Decrement first so exchanging identical source items cannot fail
            # merely because the return stack was previously full.
            entry['quantity']-=1;value={'heldItemId':entry['id'],'heldItemSource':entry['source']}
        else:
            key=data.get('item');self._owned_item(candidate['items'],key);rule=self.rule(key)
            require(bool(rule.get('held')),'That item is not a held item. Use its displayed action instead.')
            item=self.c.items[key]
            require(self.held_key(mon)!=key,'This Pokémon is already holding that item.')
            candidate['items'][key]-=1
            value={'heldItemId':item['sourceId'],'heldItemSource':item.get('source','johto'),'heldItemKey':key}
        self._return_held(candidate,mon);replace_held(mon,value);return candidate

    def sell(self,state,key,quantity):
        self._owned_item(state['items'],key);count=integer(quantity,1,999,'Quantity')
        price=int(self.rule(key).get('sellPrice',0));require(price>0,'That item is not for sale.')
        require(state['items'].get(key,0)>=count,'You do not have that many items.')
        require(state['money']+price*count<=2_000_000_000,'Your money balance would exceed the limit.')
        candidate=copy.deepcopy(state);candidate['items'][key]-=count;candidate['money']+=price*count
        return candidate

    def award_experience(self,mon,enemy_species,amount):
        """Return actual EXP/levels; apply held training effects before level-up."""
        self.ensure_mon(mon);held=self.held(mon);oldhp=self.c.stats(mon)[0]
        yields=list(self.c.species[enemy_species].get('evYield',[0]*6))
        if 'evStat' in held:yields[held['evStat']]+=held.get('evAdd',4)
        for index,value in enumerate(yields):
            gain=max(0,min(value*held.get('evMultiplier',1),255-mon['evs'][index],510-sum(mon['evs'])))
            mon['evs'][index]+=gain
        if mon['hp']>0:mon['hp']+=self.c.stats(mon)[0]-oldhp
        num,den=held.get('exp',[1,1]);actual=max(1,amount*num//den);levels=self.c.gain_xp(mon,actual)
        for _ in range(levels):self.positive_friendship(mon)
        return actual,levels

    def service(self,state,key,data):
        """Small explicitly authored MMO services, after World location checks."""
        self._owned_item(state['items'],key);candidate=copy.deepcopy(state);action=data.get('action')
        if key=='whtapricorn':
            require(action=='craft','Choose Make Fast Ball.');require(candidate['items'].get('fastball',0)<999,'Your Fast Ball stack is full.')
            candidate['items'][key]-=1;candidate['items']['fastball']=candidate['items'].get('fastball',0)+1
        elif key=='coincase':
            if action=='buycoins':
                count=integer(data.get('quantity'),1,9999,'Coin quantity');cost=count*20
                require(candidate['money']>=cost,'You do not have enough money.');require(candidate.get('coins',0)+count<=9999,'The Coin Case holds at most 9,999 coins.')
                candidate['money']-=cost;candidate['coins']=candidate.get('coins',0)+count
            elif action=='prize':
                prizes={'greatball':60,'ultraball':120,'timerball':100,'netball':100,'rarecandy':500}
                reward=data.get('reward');require(isinstance(reward,str) and reward in prizes,'Choose a displayed exchange prize.')
                cost=prizes[reward];require(candidate.get('coins',0)>=cost,'You do not have enough coins.');require(candidate['items'].get(reward,0)<999,'That item stack is full.')
                candidate['coins']-=cost;candidate['items'][reward]=candidate['items'].get(reward,0)+1
            else:require(False,'Choose a Coin Case exchange action.')
        elif key=='pokeblockcas':
            blocks=candidate.setdefault('pokeblocks',[])
            if action=='blend':
                berry=data.get('berry');require(berry in ('lumberry','sitrusberry'),'Choose a Lum or Sitrus Berry.')
                require(candidate['items'].get(berry,0)>0,'You do not have that berry.');require(len(blocks)<40,'The case holds at most 40 blocks. Feed a block first.')
                candidate['items'][berry]-=1
                # Explicit, stable MMO recipe; no fabricated native contest data.
                blocks.append({'id':data['_blockId'],'flavor':'beauty' if berry=='sitrusberry' else 'smart','power':20,'feel':10})
            elif action=='feed':
                mon=self.c.growth.owned(candidate,data.get('uid'));bid=data.get('block');require(isinstance(bid,str),'Select a Pokéblock.')
                index=next((i for i,b in enumerate(blocks) if b['id']==bid),None);require(index is not None,'That block was already used or is unavailable.')
                block=blocks[index];condition=mon.setdefault('condition',{});require(condition.get('sheen',0)<255,'That Pokémon is too full for another Pokéblock.')
                require(condition.get(block['flavor'],0)<255 or mon.get('friendship',70)<255,'That block would have no effect.')
                condition[block['flavor']]=min(255,condition.get(block['flavor'],0)+block['power']);condition['sheen']=min(255,condition.get('sheen',0)+block['feel']);self.increase_friendship(mon,10);blocks.pop(index)
            else:require(False,'Choose Blend or Feed.')
        else:require(False,'This item has no exchange service.')
        return candidate
