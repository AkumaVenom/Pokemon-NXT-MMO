#!/usr/bin/env python3
"""ROM-free, fail-closed publication of reviewed item actions and source data."""
from __future__ import annotations
import copy,json
from pathlib import Path
SHA='62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64'
EFFECTS={'capture','medicine','revive','sacredash','pp','vitamin','ppboost','level','ability','xstat','direhit','guardspec','repel','escape','pokeflute','valuable','machine','held','evolution','apricorn','coincase','journal','story','pokeblocks','tera'}

def assemble(world,root):
    audit=json.loads((Path(root)/'Server/data/item_mechanics.json').read_text(encoding='utf-8'))
    if audit.get('format')!=1 or audit.get('sourceSha256')!=SHA:raise ValueError('Unreviewed item mechanics sidecar')
    rules=audit['rules']
    if set(rules)!=set(world['items'])-{'fastball'}:raise ValueError('Every source inventory item must have an explicit reviewed action')
    if set(audit['species'])!=set(world['species']):raise ValueError('Item species metadata is incomplete')
    for key,rule in rules.items():
        if rule.get('effect') not in EFFECTS or not rule.get('description'):raise ValueError('Incomplete item behavior: '+key)
        item=world['items'][key]
        if key in audit['nativeItems'] and audit['nativeItems'][key]['sourceId']!=item.get('sourceId'):raise ValueError('Item source ID changed: '+key)
        item['mechanics']=copy.deepcopy(rule)
        # Preserve the authored SquirtBottle story definition verbatim. Its
        # action description lives in mechanics; the adventure publisher owns it.
        if key!='squirtbottle':item['description']=rule['description']
        for field in ('capture','heal'):
            if field in rule:item[field]=rule[field]
        if rule['effect']=='machine':
            if str(rule['move']) not in world['moves']:raise ValueError('Unpublished machine move: '+key)
        if 'boostType' in rule.get('held',{}) and not any(m.get('type')==rule['held']['boostType'] and m.get('power',0)>0 for m in world['moves'].values()):raise ValueError('Held booster has no published damaging move type: '+key)
        if rule.get('held') and not item.get('sourceId'):raise ValueError('Held item has no source identity: '+key)
    for key,profile in audit['species'].items():
        if len(profile['evYield'])!=6 or any(type(v) is not int or not 0<=v<=3 for v in profile['evYield']):raise ValueError('Invalid EV yield: '+key)
        if any(k not in audit['machines'] for k in profile['machines']):raise ValueError('Unknown machine compatibility: '+key)
        world['species'][key]['machines']=list(profile['machines'])
        world['species'][key]['evYield']=list(profile['evYield'])
    for source,entries in audit.get('evolutions',{}).items():
        for entry in entries:
            if source not in world['species'] or entry['target'] not in world['species'] or entry.get('item') not in rules:raise ValueError('Invalid item evolution edge')
    for key,flags in audit.get('mapFlags',{}).items():
        if key not in world['maps']:raise ValueError('Unknown item map permission: '+key)
        world['maps'][key]['escapeAllowed']=bool(flags['escapeAllowed'])
    world['items']['fastball']={'name':'Fast Ball','price':0,'buyable':False,'tradable':True,'capture':1,
        'description':'Made from a White Apricorn at the Azalea crafting service. NXT rule: 4× catch modifier for species with base Speed of at least 100; otherwise 1×.',
        'mechanics':{'effect':'capture','battle':True,'field':False,'reusable':False,'target':'none','capture':1,'ballRule':'fastball','sellPrice':0,'policy':'nxt-service-adapter'}}
    world['items']['fastball']['mechanics']['description']=world['items']['fastball']['description']
    world['itemMechanics']={'format':1,'sourceSha256':SHA,'sourceItems':len(rules),'machines':len(audit['machines']),
        'evolutions':copy.deepcopy(audit.get('evolutions',{})),
        'adapters':[k for k,v in rules.items() if v['policy'].startswith('nxt-')],
        'policy':'Explicit native roles and labeled MMO adapters. Every source pickup has an action; no inert fallback catalogue entries.'}
    return audit
