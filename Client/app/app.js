import {BattleFX} from './battle_fx.js';
import {WorldRenderer} from './renderer.js';
import {GameAudio} from './audio.js';
import {mountAudioControls} from './audio_controls.js';
const audio=new GameAudio();
let audioControls=null,audioSavePending=null,audioSaving=false;
const $=id=>document.getElementById(id);
const h=(tag,attributes={},...children)=>{const node=document.createElement(tag);for(const [key,value] of Object.entries(attributes)){if(value==null)continue;if(key==='class')node.className=value;else if(key.startsWith('on'))node.addEventListener(key.slice(2).toLowerCase(),value);else if(key==='text')node.textContent=value;else if(key==='disabled')node.disabled=!!value;else if(key==='checked')node.checked=!!value;else node.setAttribute(key,String(value));}for(const child of children.flat()){if(child!=null)node.append(child instanceof Node?child:document.createTextNode(String(child)));}return node;};
const button=(text,fn,classes='secondary',disabled=false)=>h('button',{type:'button',class:classes,onClick:fn,disabled},text);
const TYPES=['Normal','Fighting','Flying','Poison','Ground','Rock','Bug','Ghost','Steel','Mystery','Fire','Water','Grass','Electric','Psychic','Ice','Dragon','Dark','Fairy'];
let content,config,renderer,ws,connecting=null,hello=null,session=null,state=null,mode='login',starter='fr_1',loggingIn=false,deliberateLogout=false,authAttempt=0,authTimer=null;
let battleFX=null,battleSubmitting=false,battleSubmitTimer=null,battleEffectsDisabled=false;
let modalKind='',activeBattle=null,trade=null,invite=null,mapSerial=0,own=null,channel='general',sequence=0,pendingMove=0,nextStep=0;
const chats={general:[],trade:[]},mutedNames=new Set(),keys=new Map();
let inspectedUid=null,reminderView=null,collectionView='party',collectionSearch='',dexSearch='',dexFilter='all';
function toast(message,kind='info'){const node=h('div',{class:'toast '+kind},message);$('toasts').append(node);while($('toasts').children.length>5)$('toasts').firstChild.remove();setTimeout(()=>node.remove(),6500);}
function money(n){return '₽ '+Number(n||0).toLocaleString();}
function sprite(mon,back=false){const sp=content.species[mon.species];return 'assets/'+(back?(mon.shiny&&sp.backShiny?sp.backShiny:sp.back):mon.shiny?sp.shiny:sp.front);}
function send(op,data={}){if(!ws||ws.readyState!==WebSocket.OPEN||!session){toast('The world connection is not ready.','error');return false;}ws.send(JSON.stringify({op,...data}));return true;}
function connection(status,text){$('status-dot').className='status-dot '+status;$('connection-label').textContent=text;$('connection-address').textContent=config?config.host+':'+config.port+(config.tls?' · TLS':' · Private LAN / localhost'):'';}
async function connect(){
 if(connecting)return connecting;if(ws?.readyState===WebSocket.OPEN&&hello)return hello;
 connecting=new Promise((resolve,reject)=>{
  connection('','Connecting to world…');hello=null;const socket=new WebSocket(config.endpoint,'nxt.v1');ws=socket;
  const timer=setTimeout(()=>{socket.close();reject(Error('The world server did not respond. Start the server and check Client/config.ini.'));},12000);
  socket.addEventListener('message',event=>{if(ws!==socket||socket.readyState!==WebSocket.OPEN)return;let packet;try{packet=JSON.parse(event.data);}catch{toast('The server sent an unreadable packet.','error');return;}
   if(packet.type==='hello'){clearTimeout(timer);hello=packet;connection('online',packet.world+' · '+packet.online+' online');$('auth-submit').disabled=loggingIn;resolve(packet);}else handle(packet);
  });
  socket.addEventListener('open',()=>{});
  socket.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Cannot reach the world server. Check its address, firewall and TLS certificate.'));});
  socket.addEventListener('close',()=>{clearTimeout(timer);if(ws!==socket)return;hello=null;setAuthBusy(false);connection('offline','World connection closed');
   if(session&&!deliberateLogout){resetBattlePresentation();mapSerial++;audio.setScene('disconnected');keys.clear();renderer.resetSession?.();renderer.active=false;closeModal(true);$('battle-dialog').close();$('audio-dialog').close();$('disconnect-overlay').classList.remove('hidden');}
   else if(!session)$('auth-submit').textContent=mode==='register'?'Create account & enter':'Reconnect & enter world';
   reject(Error('The world connection was closed. Reconnect to try again.'));
  });
 });
 try{return await connecting;}finally{connecting=null;}
}
function setAuthBusy(busy){if(!busy){clearTimeout(authTimer);authTimer=null;}loggingIn=busy;for(const id of ['username','password','home','appearance','login-tab','register-tab','auth-submit'])$(id).disabled=busy;for(const choice of $('starters').children)choice.disabled=busy;}
async function authenticate(event){event.preventDefault();if(loggingIn)return;
 // Freeze exactly the visible choices before any network wait. Region and starter
 // are independent selections; reconnecting must never silently substitute either.
 const attempt=++authAttempt,request={op:'auth',mode,username:$('username').value.trim(),password:$('password').value,pack:content.pack,home:$('home').value,starter,appearance:Number($('appearance').value)};
 setAuthBusy(true);$('auth-error').textContent='';$('auth-submit').textContent=request.mode==='register'?'Creating your trainer…':'Entering world…';
 try{const greeting=await connect();if(attempt!==authAttempt)return;if(greeting.pack!==content.pack)throw Error('This client content pack does not match the server. Install the client supplied with this server build.');
  if(!ws||ws.readyState!==WebSocket.OPEN)throw Error('The world connection was closed. Reconnect to try again.');const socket=ws;socket.send(JSON.stringify(request));
  authTimer=setTimeout(()=>{if(attempt!==authAttempt||ws!==socket||!loggingIn)return;authAttempt++;setAuthBusy(false);hello=null;socket.close(1000,'Authentication response timed out');$('auth-error').textContent=request.mode==='register'?'No account creation result arrived. The account may already exist: choose Log in and use the same username and password.':'No login result arrived. Reconnect and try logging in again.';$('auth-submit').textContent=mode==='register'?'Create account & enter':'Reconnect & enter world';},45000);
 }catch(error){if(attempt!==authAttempt)return;setAuthBusy(false);$('auth-error').textContent=error.message;$('auth-submit').textContent=mode==='register'?'Create account & enter':'Enter world';}
}
function setMode(value){if(loggingIn)return;mode=value;for(const id of ['login','register']){$(id+'-tab').classList.toggle('selected',id===mode);$(id+'-tab').setAttribute('aria-selected',String(id===mode));}$('registration-options').classList.toggle('hidden',mode!=='register');$('login-title').textContent=mode==='register'?'Every trainer starts somewhere.':'Welcome back, trainer.';$('login-description').textContent=mode==='register'?'Choose a home region and your first partner. Any partner can start in either region.':'Your team is waiting. Connect to begin.';$('auth-submit').textContent=mode==='register'?'Create account & enter':'Enter world';$('password').autocomplete=mode==='register'?'new-password':'current-password';$('auth-error').textContent='';}
function registrationSummary(){$('registration-summary').textContent='Your first partner: '+content.species[starter].name+' · Starting region: '+$('home').value;}
function starterChoices(){const box=$('starters');box.replaceChildren();for(const key of content.starters){const sp=content.species[key];const b=button('',()=>{if(loggingIn)return;starter=key;starterChoices();audio.inspectPokemon(key);},'starter-choice'+(starter===key?' selected':''),loggingIn);b.title=sp.name;b.setAttribute('aria-pressed',String(starter===key));b.append(h('img',{src:'assets/'+sp.front,alt:sp.name}),h('span',{},sp.name));box.append(b);}registrationSummary();}
function handle(p){
 if(!session&&!['joined','error','notice'].includes(p.type))return;
 if(session&&p.ownerId!=null&&p.ownerId!==session.id)return;
 if(['map','move'].includes(p.type)&&p.entity?.id!==session?.id)return;
 switch(p.type){
  case 'joined':resetBattlePresentation();mapSerial++;keys.clear();renderer.resetSession?.();audio.setBattle(null);audio.setScene('world');session=p;state=null;inspectedUid=null;collectionView='party';collectionSearch='';dexSearch='';dexFilter='all';closeModal(true);$('party-list').replaceChildren();$('collection-count').textContent='Loading…';$('party-count').textContent='Loading…';$('money').textContent='Loading…';deliberateLogout=false;setAuthBusy(false);sequence=0;pendingMove=0;activeBattle=null;trade=null;invite=null;own=null;$('password').value='';$('login').classList.add('hidden');$('game').classList.remove('hidden');$('disconnect-overlay').classList.add('hidden');$('trainer-name').textContent=p.username;$('passport-name').textContent=p.username;$('world-title').textContent=p.world;$('population').textContent=p.online+' / '+p.cap;$('world-status').textContent='Authoritative world connected';renderer.selfId=p.id;renderer.active=true;renderer.players.clear();renderer.resize();$('surf-button').disabled=!p.alphaSurf;$('atlas-button').disabled=false;chats.general=[];chats.trade=[];toast(p.motd);break;
  case 'map':loadMap(p);break;
  case 'scene':renderer.scene(p);if(session)$('population').textContent=p.online+' / '+session.cap;break;
  case 'move':if(p.seq>=pendingMove)pendingMove=0;audio.movement(p,own);own=p.entity;renderer.entity(p.entity);if(state?.adventure&&typeof p.pcAvailable==='boolean'){state.adventure.pcAvailable=p.pcAvailable;if(!p.pcAvailable&&modalKind==='collection'&&collectionView==='storage')closeModal(true);}if(modalKind==='npc')closeModal(true);updateCoordinates();break;
  case 'state':if(state&&Number.isSafeInteger(p.revision)&&p.revision<state.revision)return;state=p;renderer.setCutTrees(p.adventure?.cutTrees);updateParty();refreshOwnerModal();break;
  case 'chat_history':chats[p.channel]=(p.messages||[]).slice(-150);if(channel===p.channel)renderChat();break;
  case 'audio':audio.handleEvents(p);break;
  case 'chat':if(!mutedNames.has(p.username)){if(audio.settings.chat&&p.username!==session?.username)audio.ui('chat');chats[p.channel].push(p);if(chats[p.channel].length>150)chats[p.channel].shift();if(channel===p.channel)renderChat();}break;
  case 'notice':toast(p.message);break;
  case 'error':if(activeBattle){battleSubmitting=false;clearTimeout(battleSubmitTimer);if(!battleFX?.busy)renderBattle();}audio.ui('error');if(p.login||!session){setAuthBusy(false);if(p.login&&!session){hello=null;ws?.close(1000,'Authentication rejected');}$('auth-error').textContent=p.message;$('auth-submit').textContent=mode==='register'?'Create account & enter':'Enter world';}else{toast(p.message,'error');if(modalKind==='npc')closeModal(true);else refreshOwnerModal();}break;
  case 'pong':$('latency').textContent=Math.max(0,Math.round(performance.now()-p.nonce))+' ms';break;
  case 'invite':audio.ui('invite');showInvite(p);break;
  case 'invite_expired':if(invite?.id===p.id){invite=null;if(modalKind==='invite')closeModal(true);toast('That invitation is no longer available.');}break;
  case 'dialog':audio.ui('dialog');showNpcDialog(p);break;
  case 'battle':{const b=p.battle;if(activeBattle?.id===b.id&&Number(b.audio?.revision)<Number(activeBattle.audio?.revision))break;const same=battleFX?.matches(b);if(b.waiting||b.ended||!same){battleSubmitting=false;clearTimeout(battleSubmitTimer);}audio.setBattle(b);activeBattle=b;if($('modal').open)closeModal(true);if(!(same&&battleFX?.busy))renderBattle();break;}
  case 'trade':trade=p.trade;renderTrade();break;
  case 'trade_done':if(trade?.id===p.id){trade=null;if(modalKind==='trade')closeModal(true);}toast(p.message,p.success?'info':'warn');break;
 }
}
async function loadMap(p){const serial=++mapSerial;keys.clear();pendingMove=0;if(['npc','collection','pokemon','reminder','atlas'].includes(modalKind))closeModal(true);if(state?.adventure)state.adventure.pcAvailable=false;$('map-loading').classList.remove('hidden');$('map-name').textContent=p.name;$('map-region').textContent=p.region;$('map-source').textContent=p.region+' · Adventure';own=p.entity;audio.setMap(p.id,!!p.entity.surf);
 try{const loaded=await renderer.loadMap(p.id,p.entity);if(!loaded||serial!==mapSerial||!session)return;renderer.resize();if(['warp','travel','home','rescue'].includes(p.transition))audio.ui('warp');updateCoordinates();}catch(error){if(serial===mapSerial&&session)toast(error.message,'error');}finally{if(serial===mapSerial)$('map-loading').classList.add('hidden');}
}
function updateCoordinates(){if(own)$('coords').textContent=own.x+', '+own.y+(own.surf?' · SURF':'');updateAdventureAccess();}
function updateAdventureAccess(){if(!session)return;const region=own?.map?.split('_')[0],unlocks=state?.adventure?.unlocks||[];$('atlas-button').disabled=false;$('surf-button').disabled=!(session.alphaSurf||own?.surf||unlocks.includes('surf_'+region));$('surf-button').title=unlocks.includes('surf_'+region)||session.alphaSurf?'Toggle Surf near water':'Earn this region’s Surf badge to travel on water.';}
function canTravelTo(map){if(!session||map.playable===false)return false;if(session.alphaAtlas)return true;const a=state?.adventure;return [1,2,3].includes(map.mapType)&&!!a?.unlocks?.includes('travel_pass')&&(a.visited.includes(map.id)||Object.values(content.homes||{}).includes(map.id));}
function hpBar(mon){const percent=Math.max(0,Math.min(100,100*mon.hp/mon.maxHp));const fill=h('div',{class:'hp-fill'+(percent<20?' critical':percent<50?' low':'')});fill.style.width=percent+'%';return h('div',{class:'hp-track',role:'meter','aria-label':mon.name+' HP','aria-valuemin':0,'aria-valuemax':mon.maxHp,'aria-valuenow':mon.hp},fill);}
function updateParty(){if(!state)return;updateAdventureAccess();$('money').textContent=money(state.money);$('collection-count').textContent=state.creatures.length+' owned';$('party-count').textContent=state.party.length+' / 6';const list=$('party-list');list.replaceChildren();
 for(let i=0;i<6;i++){const uid=state.party[i],mon=state.creatures.find(m=>m.uid===uid);if(!mon){list.append(h('div',{class:'party-empty'},'Empty party slot'));continue;}
  const ratio=Math.max(0,Math.min(100,100*(mon.exp-mon.levelExp)/Math.max(1,mon.nextExp-mon.levelExp)));const xp=h('div',{class:'xp-fill'});xp.style.width=ratio+'%';
  const card=h('div',{class:'party-card'+(i===0?' lead':''),title:'Click to inspect '+mon.name,role:'button',tabindex:0,onClick:()=>showPokemon(mon),onKeydown:e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showPokemon(mon);}}},h('img',{class:'party-icon',src:sprite(mon),alt:mon.name}),h('div',{class:'party-info'},h('div',{class:'party-name'},h('strong',{},(mon.shiny?'★ ':'')+mon.name),h('span',{},'Lv. '+mon.level)),h('div',{class:'party-meta'},h('span',{class:i===0?'lead-label':''},i===0?'FOLLOWING':mon.status||'READY'),h('span',{},mon.hp+' / '+mon.maxHp+' HP')),hpBar(mon),h('div',{class:'xp-track'},xp),(mon.pendingLearn?.length||(mon.evolutions||[]).some(e=>!e.deferred))?h('span',{class:'growth-tag'},'Growth choices ready'):null));list.append(card);
 }
}
function renderChat(){const box=$('chat-messages');const nearBottom=box.scrollTop+box.clientHeight>=box.scrollHeight-40;box.replaceChildren();const messages=chats[channel]||[];if(!messages.length)box.append(h('p',{class:'chat-line system'},channel==='general'?'Welcome to General. This channel reaches trainers throughout the world.':'Trade chat is global. Arrange a meeting, then click the trainer to open a secure exchange.'));
 for(const m of messages){if(mutedNames.has(m.username))continue;const time=new Date(m.time*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});box.append(h('div',{class:'chat-line '+channel},h('time',{},time),h('span',{class:'chat-name'},m.username),h('span',{},m.text)));}
 if(nearBottom||messages.length<10)box.scrollTop=box.scrollHeight;
}
function changeChannel(value){channel=value;$('chat-general').classList.toggle('selected',value==='general');$('chat-trade').classList.toggle('selected',value==='trade');$('chat-prefix').textContent=value.toUpperCase();renderChat();$('chat-input').focus();}
function openModal(title,kind,width=''){keys.clear();modalKind=kind;$('modal-title').textContent=title;$('modal').style.width=width;$('modal-eyebrow').textContent=kind==='trade'?'SECURE TRAINER EXCHANGE':'POKEMON NXT MMO';$('modal-body').replaceChildren();$('context-menu').classList.add('hidden');if(!$('modal').open)$('modal').showModal();return $('modal-body');}
function closeModal(force=false){if(!force&&modalKind==='trade'&&trade){send('trade',{id:trade.id,action:'cancel'});return;}if(!force&&modalKind==='invite'&&invite){send('invite.answer',{id:invite.id,accept:false});invite=null;}$('modal').close();modalKind='';}
function canOpen(){return !!session&&!!state&&!activeBattle&&!$('battle-dialog').open&&!trade&&!invite;}
function refreshOwnerModal(){
 const kind=modalKind,focus=document.activeElement,focusKey=focus?.getAttribute?.('data-focus'),selection=focus?.selectionStart,scroll=$('modal-body').scrollTop;
 if(kind==='collection')showCollection();else if(kind==='bag')showBag();else if(kind==='journal')showJournal();else if(kind==='dex')showDex();else if(kind==='pokemon'||kind==='reminder'){const mon=state?.creatures.find(m=>m.uid===inspectedUid);if(mon){if(kind==='reminder')showMoveReminder(mon);else showPokemon(mon,false);}else closeModal(true);}
 if(kind===modalKind){$('modal-body').scrollTop=scroll;if(focusKey){const next=$('modal-body').querySelector?.('[data-focus="'+focusKey+'"]');next?.focus();if(Number.isInteger(selection)&&next?.setSelectionRange)next.setSelectionRange(selection,selection);}}
}
// UI actions belong to the rendered owner and map. The server independently
// rechecks ownership, proximity and busy state before committing any mutation.
function commandButton(label,op,data,classes='secondary',disabled=false,mapBound=false){
 const owner=session?.id,map=own?.map,serial=mapSerial,kind=modalKind;
 const b=button(label,()=>{
  if(b.disabled||session?.id!==owner||modalKind!==kind||!canOpen()||(mapBound&&(own?.map!==map||mapSerial!==serial))){return;}
  if(data.uid&&!state.creatures.some(m=>m.uid===data.uid)){toast('That Pokémon is no longer in your collection.','error');return;}
  if(op==='pc'&&!state.adventure?.pcAvailable){toast('Use a PC inside a Pokémon Center to move Pokémon between your party and storage.');return;}
  if(send(op,data)){b.disabled=true;b.setAttribute('aria-busy','true');}
 },classes,disabled);
 return b;
}
function showPokemon(mon,playCry=true){
 if(!canOpen())return;mon=state.creatures.find(m=>m.uid===mon.uid);if(!mon)return;inspectedUid=mon.uid;if(playCry)audio.inspectPokemon(mon.species);
 const body=openModal(mon.name,'pokemon'),sp=content.species[mon.species];
 body.append(h('div',{class:'pokemon-summary'},h('img',{src:sprite(mon),alt:mon.name}),h('div',{},h('span',{class:'eyebrow'},state.party.includes(mon.uid)?'YOUR PARTY':'PC STORAGE'),h('h3',{},(mon.shiny?'★ Shiny · ':'')+'Level '+mon.level),h('p',{},[...new Set(sp.types)].map(t=>TYPES[t]).join(' / ')),h('p',{},mon.nature+' nature · Original trainer: '+mon.originalTrainer),h('p',{},'EXP '+mon.exp.toLocaleString()+' · Next level '+mon.nextExp.toLocaleString()))),hpBar(mon));
 const stats=h('div',{class:'help-grid'});stats.append(h('div',{},h('h3',{},'Stats'),h('p',{},['HP','Attack','Defense','Speed','Sp. Attack','Sp. Defense'].map((n,i)=>n+': '+mon.stats[i]).join(' · '))));
 const moves=h('div',{},h('h3',{},'Moves'));for(const m of mon.moves)moves.append(h('p',{},content.moves[m.id].name+' · '+m.pp+'/'+content.moves[m.id].pp+' PP'));stats.append(moves);body.append(stats);
 const pending=mon.pendingLearn?.[0];
 if(pending){
  const section=h('section',{class:'growth-panel'},h('span',{class:'eyebrow'},'A NEW MOVE · LV. '+pending.level),h('h3',{},mon.name+' wants to learn '+pending.name+'.'),h('p',{class:'modal-description'},mon.moves.length<4?'There is room for another move.':'Choose one move to forget, or keep the current moves.'));
  const actions=h('div',{class:'move-grid'});
  if(mon.moves.length<4)actions.append(commandButton('Learn '+pending.name,'pokemon.learn',{uid:mon.uid,move:pending.move,slot:mon.moves.length},'primary'));
  else for(let i=0;i<mon.moves.length;i++){const current=content.moves[mon.moves[i].id];actions.append(commandButton('Forget '+current.name,'pokemon.learn',{uid:mon.uid,move:pending.move,slot:i},'move-button'));}
  section.append(actions,h('div',{class:'modal-actions'},commandButton('Do not learn this move','pokemon.learn',{uid:mon.uid,move:pending.move,slot:null},'quiet')));
  if(mon.pendingLearn.length>1)section.append(h('p',{class:'mini-note'},(mon.pendingLearn.length-1)+' more move choices are waiting.'));body.append(section);
 }
 appendLearnset(body,mon);
 for(const option of mon.evolutions||[]){
  const target=content.species[option.target],item=option.item?content.items[option.item]:null;
  const section=h('section',{class:'growth-panel evolution-panel'},h('span',{class:'eyebrow'},option.deferred?'EVOLUTION PAUSED':'READY TO EVOLVE'),h('div',{class:'evolution-choice'},h('img',{src:'assets/'+(mon.shiny&&target.shiny?target.shiny:target.front),alt:option.name}),h('div',{},h('h3',{},mon.name+' → '+option.name),h('p',{class:'modal-description'},option.deferred?'You can resume this evolution whenever you are ready.':option.item?'Uses one '+(item?.name||option.item)+'.':'Your partner is ready for its next form.'))));
  const actions=h('div',{class:'modal-actions'});
  if(option.deferred)actions.append(commandButton('Resume evolution','pokemon.evolution.resume',{uid:mon.uid,target:option.target},'secondary'));
  else{actions.append(commandButton('Not now','pokemon.evolution.defer',{uid:mon.uid,target:option.target},'quiet'));actions.append(commandButton('Evolve into '+option.name,'pokemon.evolve',{uid:mon.uid,target:option.target},'primary',!!option.item&&!state.items[option.item]));}
  section.append(actions);body.append(section);
 }
 const actions=h('div',{class:'modal-actions'});if(state.party.includes(mon.uid)&&state.party[0]!==mon.uid)actions.append(commandButton('Make first partner','party',{party:[mon.uid,...state.party.filter(id=>id!==mon.uid)]},'primary'));
 actions.append(button('Back to party & storage',()=>showCollection()));body.append(actions);
}
function appendLearnset(body,mon){
 const entries=[...(mon.levelUpMoves||[])].sort((a,b)=>a.level-b.level),known=new Set(mon.moves.map(m=>m.id)),pending=new Set((mon.pendingLearn||[]).map(m=>m.move)),eligible=new Set((mon.relearnMoves||[]).map(m=>m.move));
 const section=h('section',{class:'learnset-panel'},h('span',{class:'eyebrow'},'LEVEL-UP MOVES'),h('h3',{},content.species[mon.species].name+'’s learnset'));
 if(!Array.isArray(mon.levelUpMoves)){section.append(h('p',{class:'modal-description'},'Move details are unavailable from this world server.'));body.append(section);return;}
 const next=entries.find(m=>m.level>mon.level&&!known.has(m.move)&&!pending.has(m.move));
 section.append(h('p',{class:'next-move'},next?'Next move: '+next.name+' at Lv. '+next.level:entries.some(m=>m.level>mon.level)?'All upcoming level-up moves are already known or awaiting a choice.':'No more level-up moves for this form.'),h('p',{class:'mini-note'},'Levels apply to this Pokémon’s current form. Evolving can change its learnset.'));
 const table=h('table',{class:'learnset-table'},h('thead',{},h('tr',{},h('th',{scope:'col'},'Level'),h('th',{scope:'col'},'Move'),h('th',{scope:'col'},'Status')))),rows=h('tbody');
 for(const entry of entries){const label=known.has(entry.move)?'Known':pending.has(entry.move)?'Pending choice':entry.level>mon.level?'Upcoming':eligible.has(entry.move)?'Move Reminder':'Reached';rows.append(h('tr',{},h('td',{},'Lv. '+entry.level),h('td',{},entry.name),h('td',{},h('span',{class:'learnset-status'+(label==='Known'?' known':label==='Pending choice'?' pending':'')},label))));}
 table.append(rows);if(entries.length)section.append(table);else section.append(h('p',{class:'modal-description'},'This form has no level-up moves.'));
 const owner=session,snapshot=state,uid=mon.uid,open=button('Open Move Reminder',()=>{if(open.disabled||session!==owner||state!==snapshot||!canOpen()||modalKind!=='pokemon'||inspectedUid!==uid)return;showMoveReminder(mon);},'secondary',pending.size>0||!eligible.size);
 section.append(h('div',{class:'modal-actions'},open),h('p',{class:'mini-note'},pending.size?'Finish the pending move choices above before using the Move Reminder.':eligible.size?'Recover a missed or forgotten level-up move. You choose the move and its slot.':'No forgotten level-up moves are available at this level.'));body.append(section);
}
function showMoveReminder(mon,moveId=null,slot=null){
 if(!canOpen())return;mon=state.creatures.find(m=>m.uid===mon.uid);if(!mon){closeModal(true);return;}inspectedUid=mon.uid;
 if(mon.pendingLearn?.length){showPokemon(mon,false);return;}
 const eligible=(mon.relearnMoves||[]).filter(m=>m.level<=mon.level&&!mon.moves.some(current=>current.id===m.move)),selected=eligible.find(m=>m.move===moveId);
 const body=openModal('Move Reminder · '+mon.name,'reminder'),owner=session,snapshot=state,view={};reminderView=view;let submitted=false;const controls=[];
 // Each step belongs to one rendered state and session. A state refresh returns
 // to move selection, so a stale confirmation can never replace a changed slot.
 const action=(label,fn,classes='secondary')=>{const b=button(label,()=>{if(b.disabled||submitted||session!==owner||state!==snapshot||reminderView!==view||modalKind!=='reminder'||inspectedUid!==mon.uid||!canOpen()||!state.creatures.some(m=>m.uid===mon.uid))return;fn();},classes);controls.push(b);return b;};
 const submit=chosenSlot=>{if(send('pokemon.remember',{uid:mon.uid,move:selected.move,slot:chosenSlot})){submitted=true;for(const b of controls)b.disabled=true;body.append(h('p',{class:'mini-note',role:'status'},'Waiting for the world to confirm the move…'));}};
 body.append(h('p',{class:'modal-description'},'Choose a missed or forgotten level-up move for '+mon.name+'’s current form. Your current moves stay in place until you confirm a choice.'));
 if(!selected){
  body.append(h('h3',{},'1. Choose a move'));const choices=h('div',{class:'move-grid reminder-choices'});
  for(const entry of eligible)choices.append(action(entry.name+' · Lv. '+entry.level,()=>showMoveReminder(mon,entry.move),'move-button'));
  body.append(choices);if(!eligible.length)body.append(h('p',{class:'empty-state'},'No forgotten level-up moves are available at this level.'));
 }else if(slot===null){
  body.append(h('h3',{},'2. Choose a slot for '+selected.name),h('p',{class:'mini-note'},'Available from Lv. '+selected.level+'. Select an empty slot or a move to replace.'));
  const choices=h('div',{class:'move-grid reminder-choices'});
  if(mon.moves.length<4)choices.append(action('Use empty slot '+(mon.moves.length+1),()=>submit(mon.moves.length),'primary'));
  for(let i=0;i<mon.moves.length;i++){const current=content.moves[mon.moves[i].id];choices.append(action('Replace '+(current?.name||'Move '+mon.moves[i].id)+' · Slot '+(i+1),()=>showMoveReminder(mon,selected.move,i),'move-button'));}body.append(choices);
  body.append(h('div',{class:'modal-actions'},action('Choose another move',()=>showMoveReminder(mon),'quiet')));
 }else if(Number.isInteger(slot)&&slot>=0&&slot<mon.moves.length){
  const current=content.moves[mon.moves[slot].id],name=current?.name||'Move '+mon.moves[slot].id;
  body.append(h('section',{class:'growth-panel reminder-confirmation'},h('span',{class:'eyebrow'},'CONFIRM MOVE REPLACEMENT'),h('h3',{},'Forget '+name+' and remember '+selected.name+'?'),h('p',{class:'modal-description'},mon.name+' will replace slot '+(slot+1)+'. Its other moves will stay the same.'),h('div',{class:'modal-actions'},action('Keep '+name,()=>showMoveReminder(mon,selected.move),'quiet'),action('Confirm: remember '+selected.name,()=>submit(slot),'primary'))));
 }
 body.append(h('div',{class:'modal-actions'},action('Back to Pokémon',()=>showPokemon(mon,false),'quiet')));
}
function showCollection(view){
 if(!canOpen())return;if(view==='party'||view==='storage')collectionView=view;
 const pc=state.adventure?.pcAvailable===true,body=openModal('Party & Pokémon storage','collection');
 body.append(h('p',{class:'modal-description'},pc?'PC connected. Deposit or withdraw Pokémon below. Keep at least one healthy partner in your party.':'Party order determines your follower. Visit a Pokémon Center and use its PC to deposit or withdraw Pokémon.'));
 const tabs=h('div',{class:'segmented',role:'tablist','aria-label':'Party or storage'});
 for(const [id,label] of [['party','Party · '+state.party.length+' / 6'],['storage','PC storage · '+(state.creatures.length-state.party.length)]]){const tab=button(label,()=>showCollection(id),id===collectionView?'selected':'');tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(id===collectionView));tabs.append(tab);}
 const search=h('input',{placeholder:'Find an owned Pokémon…','aria-label':'Search your Pokémon','data-focus':'collection-search'});search.value=collectionSearch;
 const grid=h('div',{class:'content-grid collection-grid'}),count=h('p',{class:'mini-note',role:'status'});body.append(tabs,search,count,grid);
 const refresh=()=>{
  collectionSearch=search.value;const term=collectionSearch.trim().toLowerCase();let mons=collectionView==='party'?state.party.map(uid=>state.creatures.find(m=>m.uid===uid)).filter(Boolean):state.creatures.filter(m=>!state.party.includes(m.uid));mons=mons.filter(m=>(m.name+' '+content.species[m.species].name).toLowerCase().includes(term));grid.replaceChildren();count.textContent=mons.length+' Pokémon'+(collectionView==='storage'&&!pc?' · Viewing storage; connect to a PC to transfer.':'');
  if(!mons.length){grid.append(h('p',{class:'empty-state'},term?'No owned Pokémon match your search.':collectionView==='storage'?'Your PC storage is empty. New captures go here when your party is full.':'No matching party members.'));return;}
  for(const mon of mons){
   const inParty=state.party.includes(mon.uid),lead=state.party[0]===mon.uid,actions=h('div',{class:'row'});
   actions.append(button('Inspect',()=>showPokemon(mon),'secondary'));
   if(inParty)actions.append(commandButton(lead?'Following':'Make lead','party',{party:[mon.uid,...state.party.filter(x=>x!==mon.uid)]},'secondary',lead));
   const transfer=inParty?commandButton('Deposit','pc',{action:'deposit',uid:mon.uid},'quiet',!pc||!state.party.some(id=>id!==mon.uid&&state.creatures.some(m=>m.uid===id&&m.hp>0)),true):commandButton('Withdraw','pc',{action:'withdraw',uid:mon.uid},'secondary',!pc||state.party.length>=6,true);
   const pending=(mon.pendingLearn?.length||0)+(mon.evolutions||[]).filter(e=>!e.deferred).length;
   grid.append(h('article',{class:'collection-card'},h('img',{src:sprite(mon),alt:mon.name}),h('strong',{},(mon.shiny?'★ ':'')+mon.name),h('span',{},'Lv. '+mon.level+' · '+mon.hp+'/'+mon.maxHp+' HP'),hpBar(mon),h('span',{},inParty?'Party slot '+(state.party.indexOf(mon.uid)+1):'Safely stored'),pending?h('span',{class:'growth-tag'},'New growth choices'):null,actions,h('div',{class:'row'},transfer)));
  }
 };search.addEventListener('input',refresh);refresh();
}
function showJournal(){
 if(!canOpen())return;const a=state.adventure,body=openModal('Adventure journal','journal','min(62rem,94vw)');if(!a){body.append(h('p',{class:'empty-state'},'Your adventure record is loading.'));return;}
 const badges=(a.regions||[]).flatMap(r=>r.badges||[]),earned=badges.filter(b=>b.earned).length;
 body.append(h('p',{class:'modal-description'},'Your journey through Kanto and Johto. Challenge trainers, earn badges and collect rewards as your adventure grows.'),h('div',{class:'journal-summary'},h('div',{},h('strong',{},earned+' / '+badges.length),h('span',{},'Gym badges')),h('div',{},h('strong',{},a.trainers?.count??0),h('span',{},'Trainers defeated')),h('div',{},h('strong',{},a.visited?.length||0),h('span',{},'Places visited'))));
 for(const region of a.regions||[]){
  const panel=h('section',{class:'journal-region'},h('div',{class:'section-heading'},h('h3',{},region.name),h('span',{class:'muted'},(region.badges||[]).filter(b=>b.earned).length+' / '+(region.badges||[]).length+' badges'))),grid=h('div',{class:'badge-grid'});
  for(const badge of region.badges||[])grid.append(h('article',{class:'badge-card'+(badge.earned?' earned':''),'aria-label':badge.name+(badge.earned?' earned':' not yet earned')},h('span',{class:'badge-symbol','aria-hidden':'true'},badge.earned?'★':String(badge.order)),h('strong',{},badge.name),h('span',{},badge.leader),h('small',{},badge.earned?'EARNED':'GYM CHALLENGE')));panel.append(grid);
  if(region.nextGym){const gym=region.nextGym;panel.append(h('p',{class:'next-gym'},'Next challenge: '+(typeof gym==='string'?gym:gym.name||gym.leader||'Visit the next gym')));}else panel.append(h('p',{class:'next-gym'},'All regional gym badges earned.'));body.append(panel);
 }
 if(a.fieldMoves?.length){
  const field=h('section',{class:'journal-region'},h('h3',{},'HM Cut — regional licences'));
  for(const move of a.fieldMoves)field.append(h('article',{class:'field-move-row'},h('strong',{},move.region==='kanto'?'Kanto':'Johto'),h('span',{class:'pill'+(move.unlocked?' mint':'')},move.unlocked?'CUT UNLOCKED':'CUT LOCKED'),h('p',{},move.unlocked?'Cut small HM trees in this region. Cleared paths persist for your character.':'Defeat '+move.leader+' in '+move.city+' and earn the '+move.badgeName+'.')));
  field.append(h('p',{class:'mini-note'},'Cut is learned automatically as a field ability. It does not replace a partner’s battle moves. Each region requires its own badge.'));body.append(field);
 }
 body.append(h('h3',{class:'journal-heading'},'Adventure goals'));
 for(const goal of a.goals||[]){
  const progress=Math.min(goal.target,Math.max(0,goal.current)),fill=h('div');fill.style.width=Math.min(100,100*progress/Math.max(1,goal.target))+'%';
  const reward=goal.reward||{},rewards=[reward.money?money(reward.money):'',...Object.entries(reward.items||{}).map(([id,n])=>(content.items[id]?.name||id)+' × '+n)].filter(Boolean).join(' · ');
  body.append(h('article',{class:'goal-card'+(goal.claimed?' claimed':'')},h('div',{class:'section-heading'},h('h3',{},goal.title),h('span',{class:'pill'+(goal.complete?' mint':'')},goal.claimed?'CLAIMED':progress+' / '+goal.target)),h('p',{},goal.description),h('div',{class:'goal-track',role:'progressbar','aria-label':goal.title,'aria-valuemin':0,'aria-valuemax':goal.target,'aria-valuenow':progress},fill),h('div',{class:'goal-reward'},h('span',{},rewards||'Adventure milestone'),commandButton(goal.claimed?'Reward collected':goal.complete?'Claim reward':'In progress','journal.claim',{id:goal.id},goal.complete&&!goal.claimed?'primary small':'quiet small',!goal.complete||goal.claimed))));
 }
 if(a.unlocks?.length)body.append(h('section',{class:'journal-region'},h('h3',{},'Exploration unlocks'),h('p',{class:'modal-description'},a.unlocks.map(id=>id.replace(/[_-]/g,' ')).join(' · '))));
}
function showDex(){
 if(!canOpen())return;const dex=state.adventure?.dex||{seen:[],caught:[]},seen=new Set([...dex.seen,...dex.caught]),caught=new Set(dex.caught),body=openModal('Pokédex','dex','min(60rem,94vw)');
 body.append(h('p',{class:'modal-description'},'Your field record grows when you meet and catch Pokémon. Species you have not encountered remain undiscovered.'),h('div',{class:'journal-summary dex-summary'},h('div',{},h('strong',{},seen.size),h('span',{},'Species seen')),h('div',{},h('strong',{},caught.size),h('span',{},'Species caught'))));
 const search=h('input',{placeholder:'Search discovered Pokémon…','aria-label':'Search discovered Pokémon','data-focus':'dex-search'});search.value=dexSearch;
 const filter=h('select',{'aria-label':'Pokédex record filter','data-focus':'dex-filter'},h('option',{value:'all'},'All discoveries'),h('option',{value:'caught'},'Caught'),h('option',{value:'seen'},'Seen, not caught'));filter.value=dexFilter;
 const grid=h('div',{class:'content-grid dex-grid'}),count=h('p',{class:'mini-note',role:'status'});body.append(h('div',{class:'atlas-controls'},search,filter),count,grid);
 const refresh=()=>{
  dexSearch=search.value;dexFilter=filter.value;const term=dexSearch.trim().toLowerCase();const entries=[...seen].filter(id=>content.species[id]).filter(id=>dexFilter==='caught'?caught.has(id):dexFilter==='seen'?!caught.has(id):true).filter(id=>(content.species[id].name+' '+id).toLowerCase().includes(term)).sort((a,b)=>content.species[a].name.localeCompare(content.species[b].name));
  grid.replaceChildren();count.textContent=entries.length+' matching discoveries';
  if(!entries.length)grid.append(h('p',{class:'empty-state'},'No discoveries match this view. Explore the world to add more entries.'));
  for(const id of entries){const sp=content.species[id],owned=caught.has(id),card=button('',()=>{audio.inspectPokemon(id);},'dex-card');card.setAttribute('aria-label',sp.name+' · '+(owned?'caught':'seen')+' · Play cry');card.append(h('img',{src:'assets/'+sp.front,alt:sp.name}),h('strong',{},sp.name),h('span',{class:owned?'caught-mark':'muted'},owned?'● CAUGHT':'SEEN'),h('small',{},[...new Set(sp.types)].map(t=>TYPES[t]).join(' / ')));grid.append(card);}
 };search.addEventListener('input',refresh);filter.addEventListener('change',refresh);refresh();
}
function showBag(){
 if(!canOpen())return;const body=openModal('Bag & supplies','bag');
 const nearMart=session.alphaAtlas||(renderer.map?.id===own?.map&&!renderer.pendingMap&&renderer.map.objects.some(n=>n.graphics===68&&Math.max(Math.abs(n.x-own.x),Math.abs(n.y-own.y))<=2));
 body.append(h('p',{class:'modal-description'},'Balance: '+money(state.money)+'. '+(nearMart?'Shop supplies are available here.':'Visit a Poké Mart to buy supplies. You can use owned healing items on your first partner in the field.')));
 for(const [key,item] of Object.entries(content.items)){
  const description=item.heal?'Restores '+item.heal+' HP':item.capture?'Wild capture ball':item.evolutionStone?'Evolution item · Inspect a compatible Pokémon to use it':'Supplies';
  const actions=h('div',{class:'item-actions'},commandButton('Buy 1','buy',{item:key,quantity:1},'secondary',!nearMart||state.money<item.price,true),commandButton('Buy 5','buy',{item:key,quantity:5},'secondary',!nearMart||state.money<item.price*5,true));
  if(item.heal)actions.append(commandButton('Use on lead','use',{item:key,uid:state.party[0]},'secondary',!state.items[key]));
  body.append(h('article',{class:'item-row'},h('div',{},h('h3',{},item.name+' × '+(state.items[key]||0)),h('p',{},money(item.price)+' each · '+description)),actions));
 }
}
function showAtlas(){if(!session||trade||$('battle-dialog').open)return;const body=openModal('World atlas','atlas','min(66rem,93vw)');body.append(h('p',{class:'modal-description'},session.alphaAtlas?'Exploration travel is enabled on this world. Choose a destination in Kanto or Johto / Sigma. Some original scripted exits are still in development.':state?.adventure?.unlocks.includes('travel_pass')?'Your Travel Pass is ready. Return to discovered outdoor waypoints or either starting town. Enter buildings and other interiors through their doors.':'Explore the atlas and discover routes on foot. Earn two gym badges to unlock travel between discovered outdoor waypoints and the starting towns. Enter interiors through their doors.'));const search=h('input',{placeholder:'Search a town, route, cave or map ID…','aria-label':'Search atlas'}),filter=h('select',{'aria-label':'Atlas region'},h('option',{value:'featured'},'Towns & routes'),h('option',{value:'kanto'},'Kanto · FireRed'),h('option',{value:'johto'},'Johto / Sigma'),h('option',{value:'all'},'All extracted maps'));const grid=h('div',{class:'content-grid'}),count=h('p',{class:'mini-note'});body.append(h('div',{class:'atlas-controls'},search,filter),count,grid);
 const refresh=()=>{const term=search.value.trim().toLowerCase();let maps=Object.values(content.maps).filter(m=>filter.value==='featured'?[1,2,3].includes(m.mapType):filter.value==='all'||m.id.startsWith(filter.value));maps=maps.filter(m=>(filter.value==='all'||m.playable!==false)&&(m.name+' '+m.id).toLowerCase().includes(term));maps.sort((a,b)=>((b.id==='kanto_3_0'||b.id==='johto_3_0')?1:0)-((a.id==='kanto_3_0'||a.id==='johto_3_0')?1:0)||a.name.localeCompare(b.name)||a.id.localeCompare(b.id));count.textContent=maps.length+' destinations · '+(maps.length>120?'Showing first 120; refine your search.':'Select a destination to travel.');grid.replaceChildren();for(const m of maps.slice(0,120)){const card=button('',()=>{send('travel',{map:m.id});closeModal(true);},'map-card'+(m.id==='kanto_3_0'||m.id==='johto_3_0'?' featured':''),!canTravelTo(m));card.append(h('span',{class:'eyebrow'},m.region),h('strong',{},m.name),h('small',{},m.playable===false?'Unavailable':canTravelTo(m)?'Travel to this waypoint':![1,2,3].includes(m.mapType)?'Enter through its door':state?.adventure?.visited.includes(m.id)?'Discovered · Travel Pass required':'Not yet visited'));grid.append(card);}};search.addEventListener('input',refresh);filter.addEventListener('change',refresh);refresh();}
function showHelp(){if(!canOpen())return;const body=openModal('Controls & adventure guide','help');const entries=[['HM Cut','Defeat Misty in Kanto or Bugsy in Johto to learn Cut automatically for that region. Click a nearby small HM tree (or press E), then choose Cut tree. A locked button explains the badge requirement. Only your character’s tree and collision are removed, including after relogging.'],['Explore','WASD or arrow keys move. E interacts with a nearby character. Walk into tall grass for encounters, or use Search for wild on an encounter tile.'],['Meet trainers','Click another trainer or their nameplate. Challenge starts a friendly duel; Trade opens a two-sided exchange after they accept.'],['Build your team','P opens your party and PC storage. Inspect a Pokémon for move-learning and evolution choices. Party order controls your follower. Deposit and withdraw at a Pokémon Center PC.'],['Battle','Choose a move, switch partners or use an item. Throw balls in wild battles to catch Pokémon. Trainer battles cannot be fled. Friendly duels do not spend items or persist HP loss.'],['Visit a Pokémon Center','Enter a Pokémon Center, approach Nurse Joy and press E. Ask her to heal your party and restore their HP and PP. You can access Pokémon storage there, too.'],['Your adventure','J opens badges and adventure goals. Claim completed goal rewards from your journal. G opens the Pokédex, where your encounters and catches are recorded. M opens the world atlas; B opens supplies.'],['Saving','Your progress saves automatically on the server. Save now requests an extra save. Log back in with the same account to continue your adventure.'],['Display & chat','Enter focuses chat; Escape leaves a text field. + and − adjust crisp integer world zoom. F11 toggles fullscreen. Sound controls are in the top bar and battles.']];body.append(h('div',{class:'help-grid'},entries.map(([title,text])=>h('div',{},h('h3',{},title),h('p',{},text)))));body.append(h('p',{class:'mini-note'},'Adventure alpha: original story scripts, all abilities and every advanced move effect are not yet recreated. Exploration helpers depend on the world configuration.'));}
function showNpcDialog(p){
 if(!canOpen()||(p.map&&p.map!==own?.map)||renderer.pendingMap)return;const body=openModal(p.title,'npc');body.append(h('p',{class:'modal-description'},p.message));
 const actions=h('div',{class:'modal-actions'});
 for(const action of p.actions||[]){
  if(action==='shop')actions.append(button('Open supplies',showBag,'primary'));
  else if(action==='cut'){
   const locked=(p.disabledActions||[]).includes('cut')||!p.fieldMove?.unlocked||p.fieldMove?.cleared;
   const label=p.fieldMove?.cleared?'Tree already cleared':locked?'Cut tree — locked':'Cut tree';
   const cut=commandButton(label,'npc',{npc:p.npc,map:p.map,action:'cut'},'primary cut-tree-button',!!locked,true);
   cut.setAttribute('aria-disabled',String(!!locked));
   if(locked)cut.setAttribute('title',p.fieldMove?.cleared?'Already cleared for your character.':'Requires '+(p.fieldMove?.badgeName||'the regional badge')+'.');
   actions.append(cut);
   body.append(h('p',{class:'field-move-note'},'Personal path: cutting is saved for your character only. Other trainers still see and must cut their own tree.'));
  }
  else if(action==='battle')actions.append(commandButton('Challenge trainer','npc',{npc:p.npc,action:'battle'},'primary',false,true));
  else if(action==='heal'){
   body.append(h('div',{class:'nurse-care'},h('span',{class:'care-symbol','aria-hidden':'true'},'♥'),h('div',{},h('h3',{},'A little rest for your partners'),h('p',{},'Nurse Joy will restore your party’s HP, PP and status. Would you like her to take care of them?'))));
   actions.append(commandButton('Yes, please heal my party','npc',{npc:p.npc,action:'heal'},'primary',false,true));
  }else if(action==='pc')actions.append(button('Open Pokémon storage',()=>showCollection('storage'),'secondary',!state.adventure?.pcAvailable));
 }
 actions.append(button('Close',()=>closeModal(true),'quiet'));body.append(actions);
}
function interact(){if(!renderer.map||!own||renderer.pendingMap||renderer.map.id!==own.map)return;const near=renderer.map.objects.filter(n=>renderer.objectVisible(n)&&Math.max(Math.abs(n.x-own.x),Math.abs(n.y-own.y))<=2).sort((a,b)=>(Math.abs(a.x-own.x)+Math.abs(a.y-own.y))-(Math.abs(b.x-own.x)+Math.abs(b.y-own.y)));if(near.length)send('npc',{npc:near[0].id,map:own.map});else toast('Move closer to a character, then press E.');}
function picked(hit,x,y){if(!session||$('modal').open||$('battle-dialog').open)return;if(hit.kind==='npc'){if(renderer.pendingMap||renderer.map?.id!==own?.map||hit.map!==own.map||!renderer.objectVisible(renderer.map.objects.find(n=>n.id===hit.id)))return;send('npc',{npc:hit.id,map:own.map});return;}const player=renderer.players.get(hit.id);if(!player||hit.id===session.id)return;const menu=$('context-menu');menu.replaceChildren(h('div',{class:'menu-title'},player.username));menu.append(button('Challenge to a duel',()=>{send('invite',{kind:'challenge',target:player.id});menu.classList.add('hidden');}),button('Trade Pokemon & items',()=>{send('invite',{kind:'trade',target:player.id});menu.classList.add('hidden');}),button('View first partner',()=>{menu.classList.add('hidden');const sp=content.species[player.follower];const body=openModal(player.username+'’s first partner','inspect');if(sp)body.append(h('article',{class:'collection-card'},h('img',{src:'assets/'+sp.front,alt:sp.name}),h('strong',{},sp.name),h('span',{},'Follower of '+player.username)));}),button(mutedNames.has(player.username)?'Unmute chat locally':'Mute chat locally',()=>{if(mutedNames.has(player.username))mutedNames.delete(player.username);else mutedNames.add(player.username);renderChat();menu.classList.add('hidden');},'quiet'));menu.classList.remove('hidden');menu.style.left=Math.min(x,innerWidth-menu.offsetWidth-12)+'px';menu.style.top=Math.min(y,innerHeight-menu.offsetHeight-12)+'px';}
function showInvite(p){if(trade||$('battle-dialog').open){send('invite.answer',{id:p.id,accept:false});return;}invite=p;const body=openModal(p.kind==='trade'?'Trade invitation':'Trainer challenge','invite');body.append(h('p',{class:'modal-description'},p.trainer+(p.kind==='trade'?' would like to trade with you.':' challenged you to a friendly duel.')));body.append(h('p',{class:'mini-note'},'Invitation expires after '+p.seconds+' seconds. You must stay nearby.'),h('div',{class:'modal-actions'},button('Decline',()=>{send('invite.answer',{id:p.id,accept:false});invite=null;closeModal(true);},'quiet'),button('Accept invitation',()=>{send('invite.answer',{id:p.id,accept:true});invite=null;closeModal(true);},'primary')));}
function renderTrade(){if(!trade||!state)return;const t=trade,body=openModal('Trade with '+t.otherName,'trade','min(62rem,94vw)');const both=t.ready.length===2;body.append(h('p',{class:'trade-warning'},both?'Both offers are locked. Check the Pokemon, items and money on BOTH sides before final confirmation. Any offer edit resets both confirmations.':'Nothing moves until both trainers lock their offers and confirm the exact same exchange. You can cancel before the final commit.'));
 const sides=h('div',{class:'trade-grid'});for(const id of [t.you,t.other]){const offer=t.offers[id],box=h('section',{class:'trade-side'},h('h3',{},id===t.you?'Your offer':t.otherName+'’s offer')),detail=h('div',{class:'trade-offer'});for(const mon of offer.pokemon)detail.append(h('div',{class:'offer-mon'},h('img',{src:sprite(mon),alt:mon.name}),h('span',{},(mon.shiny?'★ ':'')+mon.name+' · Lv. '+mon.level)));for(const [key,n] of Object.entries(offer.items))if(n)detail.append(h('p',{class:'offer-item'},content.items[key].name+' × '+n));if(offer.money)detail.append(h('p',{class:'offer-item'},money(offer.money)));if(!offer.pokemon.length&&!Object.values(offer.items).some(Boolean)&&!offer.money)detail.append(h('p',{class:'mini-note'},'No assets offered.'));box.append(detail,h('div',{class:'trade-status'},t.confirmed.includes(id)?'✓ FINAL CONFIRMATION RECEIVED':t.ready.includes(id)?'✓ OFFER LOCKED':'EDITING OFFER'));sides.append(box);}body.append(sides);
 const ownOffer=t.offers[t.you],editor=h('section',{class:'trade-editor'},h('h3',{},'Edit your offer')),picker=h('div',{class:'trade-picker'}),selected=new Set(ownOffer.pokemon.map(m=>m.uid));for(const mon of state.creatures){const check=h('input',{type:'checkbox',checked:selected.has(mon.uid),'data-mon':mon.uid});picker.append(h('label',{},check,mon.name+' · Lv. '+mon.level));}editor.append(h('p',{class:'mini-note'},'Select up to six Pokemon. A trade may not leave either trainer without a Pokemon.'),picker);
 const numbers=h('div',{class:'trade-numbers'});const cash=h('input',{type:'number',min:0,max:state.money,step:1,value:ownOffer.money||0,'aria-label':'Money offered'});numbers.append(h('div',{},h('label',{},'Money · own '+money(state.money)),cash));const itemInputs={};for(const [key,item] of Object.entries(content.items)){const input=h('input',{type:'number',min:0,max:state.items[key]||0,step:1,value:ownOffer.items[key]||0,'aria-label':item.name+' offered'});itemInputs[key]=input;numbers.append(h('div',{},h('label',{},item.name+' · own '+(state.items[key]||0)),input));}editor.append(numbers);
 function apply(){const pokemon=[...picker.querySelectorAll('input:checked')].map(i=>i.dataset.mon);if(pokemon.length>6){toast('You can offer at most six Pokemon.','error');return;}const items={};for(const [key,input] of Object.entries(itemInputs)){const n=Number(input.value);if(!Number.isSafeInteger(n)||n<0){toast('Item quantities must be whole, non-negative numbers.','error');return;}if(n)items[key]=n;}const amount=Number(cash.value);if(!Number.isSafeInteger(amount)||amount<0){toast('Money must be a whole, non-negative number.','error');return;}send('trade',{id:t.id,action:'offer',revision:t.revision,offer:{pokemon,items,money:amount}});}
 editor.append(h('div',{class:'modal-actions'},button('Apply edited offer',apply,'secondary')));body.append(editor,h('p',{class:'digest-note'},'Offer revision '+t.revision+' · Verification '+t.digest.slice(0,24)+'… · '+t.seconds+' seconds remaining'));
 const lockButton=button(t.ready.includes(t.you)?'Your offer is locked':'Lock current offer',()=>send('trade',{id:t.id,action:'lock',revision:t.revision}),'secondary',t.ready.includes(t.you));
 const confirmButton=button(t.confirmed.includes(t.you)?'Waiting for final confirmation':'Confirm this exact exchange',()=>send('trade',{id:t.id,action:'confirm',revision:t.revision,digest:t.digest}),'primary',!both||t.confirmed.includes(t.you));
 const draftNote=h('p',{class:'mini-note hidden'},'Unsubmitted changes: apply your edited offer before locking or confirming. The offer panels above show the last server-accepted exchange.');
 editor.append(draftNote);editor.addEventListener('input',()=>{lockButton.disabled=true;confirmButton.disabled=true;draftNote.classList.remove('hidden');});
 body.append(h('div',{class:'modal-actions'},button('Cancel exchange',()=>send('trade',{id:t.id,action:'cancel'}),'quiet danger'),lockButton,confirmButton));
}
function combatCard(mon,side){return h('div',{class:'combat-card '+side},h('div',{class:'party-name'},h('strong',{},(mon.shiny?'★ ':'')+mon.name),h('span',{},'Lv. '+mon.level)),h('div',{class:'party-meta'},h('span',{},mon.status?mon.status.toUpperCase():'HP'),h('span',{},mon.hp+' / '+mon.maxHp)),hpBar(mon));}
function resetBattlePresentation(){battleFX?.reset();battleEffectsDisabled=false;battleSubmitting=false;clearTimeout(battleSubmitTimer);battleSubmitTimer=null;}
function disableBattleEffects(error){battleEffectsDisabled=true;battleFX?.reset();console.warn('Battle animations disabled; authoritative battle controls remain available.',error);}
function battleAction(action,extra={}){
 if(!activeBattle||activeBattle.ended||activeBattle.waiting||battleSubmitting||battleFX?.busy)return;
 try{if(!send('battle',{id:activeBattle.id,action,...extra}))return;battleSubmitting=true;const id=activeBattle.id;battleSubmitTimer=setTimeout(()=>{if(activeBattle?.id!==id)return;battleSubmitting=false;if(!battleFX?.busy)renderBattle();toast('Still waiting for the world server. Check your connection if the turn does not resolve.','warn');},12000);renderBattle();}catch(error){battleSubmitting=false;toast('The action could not be sent. Reconnect and try again.','error');renderBattle();}
}
function renderBattle(){if(!activeBattle||battleFX?.busy&&battleFX.matches(activeBattle))return;battleFX??=new BattleFX();keys.clear();const b=activeBattle,root=$('battle-content');root.replaceChildren();root.append(h('header',{class:'battle-head'},h('div',{},h('span',{class:'eyebrow'},b.kind==='duel'?'FRIENDLY TRAINER DUEL':b.kind==='trainer'?'TRAINER BATTLE':'WILD ENCOUNTER'),h('h2',{},session.username+' vs '+b.opponentName)),h('div',{class:'toolbar-actions'},button('Sound',()=>audioControls?.open(),'quiet small'),h('span',{class:'pill'},b.ended?'BATTLE COMPLETE':'TURN '+b.turn+' · '+b.seconds+'s'))));const stage=h('div',{class:'battle-stage'},h('img',{class:'battle-sprite enemy',src:sprite(b.opponent),alt:b.opponent.name}),h('img',{class:'battle-sprite you',src:sprite(b.you,true),alt:b.you.name}),combatCard(b.opponent,'enemy'),combatCard(b.you,'you'));root.append(stage);const log=h('div',{class:'battle-log',role:'log'});for(const text of b.log)log.append(h('p',{},text));const choices=h('fieldset',{class:'battle-choice-panel','aria-label':'Battle actions'});
 if(b.ended){const result={caught:'A new partner joins your journey!',won:'Victory!',lost:'Your team fought bravely.',escaped:'You returned to the world.'}[b.result]||'Battle complete.';choices.append(h('h3',{class:'battle-result'},result),h('p',{class:'modal-description'},b.kind==='duel'?'Friendly duel finished. Your persistent party health and supplies were not spent.':'The world server has saved the completed actions.'),button('Return to adventure',()=>{resetBattlePresentation();$('battle-dialog').close();activeBattle=null;audio.setBattle(null);},'primary wide'));
 }else{
  if(b.waiting)choices.append(h('div',{class:'battle-wait'},'Action submitted. Waiting for the other trainer…'));
  const moves=h('div',{class:'move-grid'});for(let i=0;i<b.you.moves.length;i++){const slot=b.you.moves[i],move=content.moves[slot.id];const enabled=b.usable.includes(i);const btn=button('',()=>battleAction('attack',{slot:i}),'move-button',b.waiting||!enabled);btn.title=enabled?'Use '+move.name:slot.pp<=0?'No PP remaining':'This move’s advanced effect is not implemented in this alpha.';btn.append(h('strong',{},move.name),h('small',{},h('span',{},TYPES[move.type]),h('span',{},slot.pp+' / '+move.pp+' PP')));moves.append(btn);}if(!b.usable.length)moves.append(button('Struggle',()=>battleAction('attack',{slot:-1}),'move-button',b.waiting));choices.append(moves);
  const switcher=h('select',{'aria-label':'Switch active Pokemon'},h('option',{value:''},'Switch partner…'));for(const m of b.party)if(m.uid!==b.you.uid&&m.hp>0)switcher.append(h('option',{value:m.uid},m.name+' · Lv. '+m.level));switcher.disabled=b.waiting;switcher.addEventListener('change',()=>{if(switcher.value)battleAction('switch',{uid:switcher.value});});const options=h('div',{class:'battle-options'},switcher);
  if(b.kind!=='duel'){const items=h('select',{'aria-label':'Battle item'},h('option',{value:''},'Use an item…'));for(const [key,item] of Object.entries(content.items)){if(!state.items[key]||(!item.capture&&!item.heal)||(item.capture&&b.kind!=='wild'))continue;items.append(h('option',{value:key},item.name+' × '+state.items[key]));}items.disabled=b.waiting;items.addEventListener('change',()=>{if(items.value)battleAction(content.items[items.value].capture?'capture':'item',{item:items.value});});options.append(items);}
  options.append(button(b.kind==='duel'?'Forfeit':b.kind==='trainer'?'Cannot flee trainer battles':'Run',()=>battleAction('run'),'quiet danger',b.waiting||b.canRun===false||b.kind==='trainer'));choices.append(options,h('p',{class:'mini-note'},b.kind==='duel'?'A friendly match. No money or items are wagered.':'Weaken a wild Pokemon before throwing a ball. Unsupported advanced moves are disabled.'));
 }
 root.append(h('div',{class:'battle-controls'},log,choices));
 // Open the usable battle before starting optional presentation effects.
 if(!$('battle-dialog').open)$('battle-dialog').showModal();
 let started=false;try{if(!battleEffectsDisabled)started=battleFX.play(b,stage,{moveName:id=>content.moves[id]?.name||'Move',showSpecies:(image,event,side)=>{if(!image||!content.species[event.species])return;const current=side==='you'?b.you:b.opponent;image.src=sprite({...current,species:event.species,shiny:current.species===event.species&&current.shiny},side==='you');image.alt=content.species[event.species].name;const card=stage.querySelector('.combat-card.'+side);if(card)card.style.visibility=current.species===event.species?'':'hidden';},done:()=>{if(activeBattle?.id===b.id&&session)renderBattle();},failed:error=>{disableBattleEffects(error);if(activeBattle?.id===b.id&&session)renderBattle();}});else battleFX.skip(b);}catch(error){disableBattleEffects(error);renderBattle();return;}
 choices.disabled=!!(started||battleFX.busy||battleSubmitting);if(started||battleFX.busy||battleSubmitting)choices.prepend(h('p',{class:'battle-presentation-status',role:'status'},battleSubmitting?'Sending your action…':'Resolving the turn…'));
 log.scrollTop=log.scrollHeight;
}
function logout(){resetBattlePresentation();mapSerial++;authAttempt++;setAuthBusy(false);audio.setScene('title');audio.setBattle(null);setMode('login');deliberateLogout=true;keys.clear();renderer.resetSession?.();renderer.active=false;if(ws)ws.close(1000,'User logout');session=null;state=null;own=null;trade=null;invite=null;activeBattle=null;renderer.players.clear();closeModal(true);$('battle-dialog').close();$('audio-dialog').close();$('disconnect-overlay').classList.add('hidden');$('game').classList.add('hidden');$('login').classList.remove('hidden');$('auth-submit').disabled=false;$('auth-submit').textContent='Enter world';connection('offline','Reconnect to continue your journey');}
function setupInput(){
 $('auth-form').addEventListener('submit',authenticate);$('login-tab').addEventListener('click',()=>setMode('login'));$('register-tab').addEventListener('click',()=>setMode('register'));$('reconnect').addEventListener('click',()=>{if(!loggingIn)connect().catch(e=>{$('auth-error').textContent=e.message;connection('offline','World server is unavailable');});});
 $('home').addEventListener('change',()=>{if(loggingIn)return;registrationSummary();audio.setRegion($('home').value);});
 $('logout').addEventListener('click',logout);$('disconnect-login').addEventListener('click',logout);$('modal-close').addEventListener('click',()=>closeModal());$('modal').addEventListener('cancel',e=>{e.preventDefault();closeModal();});$('battle-dialog').addEventListener('cancel',e=>{e.preventDefault();if(activeBattle?.ended){resetBattlePresentation();activeBattle=null;$('battle-dialog').close();audio.setBattle(null);}});
 $('chat-general').addEventListener('click',()=>changeChannel('general'));$('chat-trade').addEventListener('click',()=>changeChannel('trade'));$('chat-form').addEventListener('submit',e=>{e.preventDefault();const text=$('chat-input').value.trim();if(text&&send('chat',{channel,text}))$('chat-input').value='';});
 for(const [id,fn] of [['atlas-button',showAtlas],['collection-button',showCollection],['bag-button',showBag],['help-button',showHelp],['journal-button',showJournal],['dex-button',showDex],['surf-button',()=>send('surf')],['search-button',()=>send('encounter')],['save-button',()=>send('save')],['unstuck-button',()=>send('unstuck')]])$(id).addEventListener('click',fn);
 $('zoom-out').addEventListener('click',()=>renderer.setScale(renderer.scale-1));$('zoom-in').addEventListener('click',()=>renderer.setScale(renderer.scale+1));
 document.addEventListener('click',e=>{if(!e.target.closest('#context-menu')&&e.target!==$('world-canvas'))$('context-menu').classList.add('hidden');});
 const directions={w:'up',arrowup:'up',s:'down',arrowdown:'down',a:'left',arrowleft:'left',d:'right',arrowright:'right'};
 document.addEventListener('keydown',e=>{
  const key=e.key.toLowerCase(),typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);if(e.key==='F11'){e.preventDefault();if(document.fullscreenElement)document.exitFullscreen();else document.documentElement.requestFullscreen().catch(()=>{});return;}
  if(typing){if(key==='escape'){document.activeElement.blur();keys.clear();}return;}if(!session)return;if($('modal').open||$('battle-dialog').open||$('audio-dialog').open)return;
  if(directions[key]){e.preventDefault();if(!e.repeat){keys.set(key,directions[key]);stepNow();}return;}if(e.repeat)return;
  if(key==='enter'){e.preventDefault();$('chat-input').focus();keys.clear();}else if(key==='e')interact();else if(key==='m')showAtlas();else if(key==='p')showCollection();else if(key==='b')showBag();else if(key==='j')showJournal();else if(key==='g')showDex();else if(key==='?'||key==='h')showHelp();else if(key==='+'||key==='=')renderer.setScale(renderer.scale+1);else if(key==='-')renderer.setScale(renderer.scale-1);
 });document.addEventListener('keyup',e=>keys.delete(e.key.toLowerCase()));window.addEventListener('blur',()=>keys.clear());
 function stepNow(){if(!session||!own||!keys.size||!renderer.map||renderer.pendingMap||renderer.map.id!==own.map||$('modal').open||$('battle-dialog').open||$('audio-dialog').open||!$('disconnect-overlay').classList.contains('hidden'))return;if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;const now=performance.now();if(pendingMove&&now-nextStep>1500)pendingMove=0;if(pendingMove||now<nextStep)return;const direction=[...keys.values()].at(-1);sequence++;pendingMove=sequence;nextStep=now+(session.stepMs||160)+5;send('move',{direction,seq:sequence});}
 setInterval(stepNow,16);
 setInterval(()=>{if(session){send('ping',{nonce:performance.now()});$('zoom-value').textContent=renderer.scale+'×';$('render-status').textContent=renderer.fps+' FPS · '+(window.devicePixelRatio||1)+'× DPI';}},2500);
}

async function persistAudioSettings(settings){
 audioSavePending={...settings};
 if(audioSaving)return;
 audioSaving=true;
 try{
  while(audioSavePending){
   const current=audioSavePending;audioSavePending=null;
   try{
    const response=await fetch('/audio-settings?token='+encodeURIComponent(config.nonce),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(current),keepalive:true});
    if(!response.ok)throw Error('Audio preferences could not be saved.');
    const saved=await response.json();audioControls?.setPersistence(saved.persisted===true);
   }catch{audioControls?.setPersistence(false);}
  }
 }finally{audioSaving=false;}
}

async function boot(){
 try{const [bootResponse,contentResponse]=await Promise.all([fetch('/bootstrap'),fetch('assets/world/client.json')]);if(!bootResponse.ok||!contentResponse.ok)throw Error('Start the game using Pokemon NXT MMO.exe. Do not open index.html directly.');[config,content]=await Promise.all([bootResponse.json(),contentResponse.json()]);if(config.uiScale)document.documentElement.style.fontSize=(14*config.uiScale)+'px';renderer=new WorldRenderer($('world-canvas'),content,picked);if(config.pixelScale)renderer.manualScale=config.pixelScale;starterChoices();setupInput();audioControls=mountAudioControls(audio);if(config.audioPersistenceMessage)audioControls.setPersistence(false);audio.init({settings:config.audio,onSettingsChange:persistAudioSettings}).catch(()=>{});audio.setScene('title');$('boot').classList.add('hidden');$('login').classList.remove('hidden');setMode('login');
  const heartbeat=()=>fetch('/heartbeat?token='+encodeURIComponent(config.nonce),{method:'POST',keepalive:true}).catch(()=>{});heartbeat();setInterval(heartbeat,15000);connect().catch(error=>{connection('offline','World server is unavailable');$('auth-error').textContent=error.message;$('auth-submit').disabled=false;});
 }catch(error){$('boot-message').textContent=error.message;console.error(error);}
}
boot();
