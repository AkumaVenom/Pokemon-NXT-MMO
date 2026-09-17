"""Reviewed NXT item behavior registry, separate from extracted ROM evidence.

A ROM name/hold-effect byte is not a complete implementation. Every published
item has an explicit action contract; unsupported IDs cannot fall through into
an inert generic item. Custom MMO adaptations are named as such in the UI/audit.
"""
from __future__ import annotations
import copy

TYPES = ['Normal','Fighting','Flying','Poison','Ground','Rock','Bug','Ghost','Steel','Mystery','Fire','Water','Grass','Electric','Psychic','Ice','Dragon','Dark','Fairy']


def build_rules(items, native, machines):
    rules = {}
    def put(key, effect, description, **params):
        if key not in items:
            raise ValueError('Behavior references missing item: '+key)
        rules[key] = dict(effect=effect, description=description, field=False,
                          battle=False, reusable=False, target='none',
                          policy='reviewed-native-role', **{})
        rules[key].update(params)

    for key, item in items.items():
        if item.get('evolutionStone'):
            put(key, 'evolution', 'Evolves a compatible Pokémon. Choose the Pokémon and confirm its available evolution; consumed only on success.', field=True, target='pokemon')
    for key, value in [('pokeball',1),('greatball',1.5),('ultraball',2),('masterball',1),('netball',1),('diveball',1),('nestball',1),('repeatball',1),('timerball',1),('luxuryball',1)]:
        desc = {
            'pokeball':'A standard wild capture ball (1×).',
            'greatball':'A wild capture ball with a 1.5× catch modifier.',
            'ultraball':'A wild capture ball with a 2× catch modifier.',
            'masterball':'Always catches a wild Pokémon. Cannot capture another trainer’s Pokémon.',
            'netball':'3× catch modifier against Water- or Bug-type wild Pokémon; otherwise 1×.',
            'diveball':'3.5× catch modifier in underwater terrain; otherwise 1×. Surfing alone is not underwater.',
            'nestball':'More effective on lower-level wild Pokémon: max(1, (40 − level) / 10)×.',
            'repeatball':'3× if this species is already in your caught Pokédex; otherwise 1×. Merely seeing it does not count.',
            'timerball':'Starts at 1× and gains 0.1× per completed turn, up to 4× after 30 completed turns (GBA rule).',
            'luxuryball':'A 1× capture ball. Its caught Pokémon gains an extra friendship point when friendship increases.'
        }[key]
        put(key,'capture',desc,battle=True,ballRule=key,capture=value)
    heals = {'potion':20,'superpotion':50,'hyperpotion':200,'maxpotion':65535,
             'freshwater':50,'energypowder':50,'energyroot':200,'sitrusberry':30}
    for key, amount in heals.items():
        desc = ('Restores all HP' if amount==65535 else f'Restores {amount} HP')+' to one non-fainted Pokémon.'
        if key in ('energypowder','energyroot'):desc+=' Bitter medicine lowers friendship.'
        put(key,'medicine',desc,field=True,battle=True,target='pokemon',heal=amount,
            bitter=[-10,-15] if key=='energyroot' else [-5,-10] if key=='energypowder' else None)
    cures = {'antidote':['poison','toxic'],'paralyzheal':['paralysis'],'awakening':['sleep'],
             'burnheal':['burn'],'iceheal':['freeze'],'fullheal':['all'],'healpowder':['all'],
             'ragecookie':['all'],'lumberry':['all'],'blueflute':['sleep'],'yellowflute':['confusion']}
    for key, cure in cures.items():
        put(key,'medicine','Cures '+('major status conditions and confusion' if cure==['all'] else ' / '.join(cure))+' on one Pokémon.'+(' Reusable; not consumed.' if key.endswith('flute') else ''),
            field=key!='yellowflute',battle=True,target='pokemon',cure=cure,
            reusable=key.endswith('flute'),bitter=[-5,-10] if key=='healpowder' else None)
    put('fullrestore','medicine','Fully restores one living Pokémon’s HP and cures major status conditions and confusion.',field=True,battle=True,target='pokemon',heal=65535,cure=['all'])
    for key, fraction in [('revive',.5),('maxrevive',1),('revivalherb',1)]:
        put(key,'revive',('Revives one fainted Pokémon to half HP.' if fraction==.5 else 'Revives one fainted Pokémon to full HP.')+(' Bitter medicine lowers friendship.' if key=='revivalherb' else ''),field=True,battle=True,target='pokemon',fraction=fraction,bitter=[-15,-20] if key=='revivalherb' else None)
    put('sacredash','sacredash','Revives every fainted member of your current party to full HP. Field use only.',field=True,target='party')
    for key, amount, all_moves in [('ether',10,False),('maxether',65535,False),('elixir',10,True),('maxelixir',65535,True)]:
        put(key,'pp',('Restores all PP' if amount==65535 else f'Restores {amount} PP')+(' to every move of one Pokémon.' if all_moves else ' to one selected move.'),field=True,battle=True,target='pokemon' if all_moves else 'move',pp=amount,allMoves=all_moves)
    for key, index in [('hpup',0),('protein',1),('iron',2),('carbos',3),('calcium',4),('zinc',5)]:
        label=['HP','Attack','Defense','Speed','Special Attack','Special Defense'][index]
        put(key,'vitamin',f'Adds up to 10 {label} effort points, with the GBA vitamin cap of 100 per stat and total EV cap of 510. Increases friendship on successful use.',field=True,target='pokemon',stat=index)
    for key, count in [('ppup',1),('ppmax',3)]:
        put(key,'ppboost','Permanently increases a selected move’s maximum PP '+('by one 20% increment, up to three increments.' if count==1 else 'to all three 20% increments.')+' Does not affect Sketch or 1-PP moves.',field=True,target='move',increments=count)
    put('rarecandy','level','Raises a Pokémon below level 100 by one level, preserves EXP progression, and processes its native move-learning/evolution choices.',field=True,target='pokemon')
    put('skillcapsule','ability','Switches between a species’ two different regular abilities. It does not create an ability or grant a hidden ability. Unsupported destination ability IDs are blocked without consumption.',field=True,target='pokemon')
    for key, stat in [('xattack',1),('xdefend',2),('xspeed',3),('xspecial',4),('xaccuracy',0)]:
        put(key,'xstat','Raises the active Pokémon’s '+['accuracy','Attack','Defense','Speed','Special Attack'][stat]+' by one stage for this battle, until it switches out.',battle=True,target='active',stat=stat)
    put('direhit','direhit','Raises the active Pokémon’s critical-hit stage by two until it switches out. Does not stack with Focus Energy.',battle=True,target='active')
    put('guardspec','guardspec','Protects your side against opposing stat reductions for five turns.',battle=True,target='active')
    for key, steps in [('repel',100),('superrepel',200),('maxrepel',250)]:
        put(key,'repel',f'For {steps} successful walking steps, prevents wild encounters below your first party Pokémon’s level. Cannot replace an active Repel.',field=True,steps=steps)
    put('escaperope','escape','Returns to the recorded safe entrance where the source map permits Escape Rope. Cannot be used in battle; no item is spent without a safe destination.',field=True)
    put('pokeflute','pokeflute','Wakes sleeping Pokémon in your party. In battle, wakes both active Pokémon. Reusable.',field=True,battle=True,target='party',reusable=True)
    for key in ['pearl','bigpearl','stardust','cometshard','wishingstar','nugget','tinymushroom']:
        put(key,'valuable','A treasure for sale at a Poké Mart. Sell it for half its Sigma ROM shop value; it is not a battle consumable.')
    for key, machine in machines.items():
        put(key,'machine',f'Teaches {machine["moveName"]} to a compatible Pokémon using the supplied Sigma machine table.'+(' Reusable HM.' if key.startswith('hm') else ' One TM is consumed only after the move is successfully learned.'),
            field=True,target='machine',reusable=key.startswith('hm'),move=machine['move'],machineIndex=machine['index'])

    def held(key, desc, **effect):
        # A berry can be both used directly and given to a Pokémon.
        if key not in rules:put(key,'held',desc)
        else:rules[key]['description'] += ' When held: '+desc
        rules[key]['held']=effect
    held('choicescarf','Held: raises Speed by 50%, but locks the holder into its first selected move until it switches out.',stats={'3':[3,2]},choice=True)
    rules['choicescarf']['policy']='nxt-named-item-adapter'
    held('machobrace','Held: doubles earned EVs and halves battle Speed.',stats={'3':[1,2]},evMultiplier=2)
    for key,index in [('poweranklet',3),('powerband',5),('powerlens',4)]:
        held(key,'Held: adds 4 '+['HP','Attack','Defense','Speed','Special Attack','Special Defense'][index]+' EVs per defeated Pokémon and halves battle Speed.',stats={'3':[1,2]},evStat=index,evAdd=4)
        rules[key]['policy']='nxt-named-item-adapter'
    held('focusband','Held: 10% chance to survive an otherwise fatal hit at 1 HP.',legacyCode=196)
    held('luckyegg','Held: increases battle EXP earned by 50%.',exp=[3,2])
    held('smokeball','Held: guarantees escape from wild battles, including trapping effects.',alwaysRun=True)
    held('enigmastone','Sigma held effect: raises Latios or Latias Special Attack and Special Defense by 50%.',legacyCode=191)
    held('stickybarb','Sigma held effect: doubles Clamperl’s Special Defense (native Deep Sea Scale effect). It is not the later-generation contact-damage item.',legacyCode=193)
    held('widelens','Held: increases move accuracy by 10%.',accuracy=[11,10])
    rules['widelens']['policy']='nxt-description-adapter'
    for key in ('roseincense','oddincense'):
        held(key,'Sigma held effect: reduces the accuracy of attacks targeting the holder by 5%.',evasion=[95,100])
    for key,typ in [('nevermeltice',15),('blackglasses',17),('silverpowder',6),('twistedspoon',14),('dragonfang',16),('dragonbone',16),('flameball',10),('destinyknot',9)]:
        held(key,'Held: boosts '+TYPES[typ]+'-type move power by 10%.'+(' This is a held item, not a capture ball.' if key=='flameball' else ''),boostType=typ,boost=[11,10])
    rules['destinyknot']['policy']='nxt-description-adapter'
    rules['destinyknot']['description']='NXT Sigma-description adaptation: boosts source type 9 moves (including Moonblast and Dazlinggleam) by 10%. Sigma describes this role as Fairy; the published source type remains ???, not an invented type 18.'
    held('lumberry','Automatically cures major status and confusion, then is consumed.',legacyCode=141)
    held('sitrusberry','Restores 30 HP when at half HP or lower, then is consumed.',legacyCode=142)
    put('dragonshell','evolution','A Sigma Dragon Scale counterpart. Evolves Seadra into Kingdra through NXT’s confirmed item-evolution action.',field=True,target='pokemon',evolutionAlias='dragonscale',policy='nxt-evolution-adapter')
    put('whtapricorn','apricorn','Bring this White Apricorn to Kurt in his Azalea Town house to make a Fast Ball. The NXT Fast Ball has a 4× modifier against species with base Speed of at least 100.',field=True,policy='nxt-service-adapter')
    put('coincase','coincase','Reusable coin wallet. At an NXT Poké Mart coin exchange, buy coins or exchange them for displayed prizes. Coins and money are saved atomically.',field=True,reusable=True,policy='nxt-service-adapter')
    put('rotompad','journal','Opens your saved Pokédex and trainer/badge records. Reusable; nothing is consumed.',field=True,reusable=True)
    put('squirtbottle','story','Use at the Route 36 odd tree after earning Whitney’s badge to start the existing Sudowoodo story battle. Reusable.',field=True,reusable=True)
    put('pokeblockcas','pokeblocks','Reusable NXT berry-blending case. Blend an owned Lum or Sitrus Berry and feed the resulting block to increase friendship and the displayed contest condition. No contest minigame is simulated.',field=True,reusable=True,policy='nxt-service-adapter')
    put('teraorb','tera','NXT battle adaptation: once per battle, Terastallize your active Pokémon into its primary species type alongside an attack. Changes defensive typing and STAB until battle ends. The Orb is not consumed.',battle=True,reusable=True,policy='nxt-battle-adapter')
    missing=set(items)-set(rules)
    if missing:raise ValueError('Items without explicit behavior: '+', '.join(sorted(missing)))
    for key, rule in rules.items():
        n=native.get(key,{})
        rule['sellPrice']=0 if items[key].get('keyItem') or rule['reusable'] else max(0,int(n.get('price',items[key].get('sourcePrice',items[key].get('price',0))))//2)
        if items[key].get('buyable',True):rule['sellPrice']=min(rule['sellPrice'],max(0,int(items[key].get('price',0)))//2)
        if key in ('teraorb',):rule['sellPrice']=0
    return rules
