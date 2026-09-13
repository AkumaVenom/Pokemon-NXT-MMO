/** Accessible mixer controls; the audio engine owns playback and focus behavior. */
export function mountAudioControls(audio){
 const byId=id=>document.getElementById(id),dialog=byId('audio-dialog');
 const sliders=['master','music','effects','cries'];
 const toggles={muted:'audio-muted',muteUnfocused:'audio-focus',lowHp:'audio-lowhp',chat:'audio-chat'};
 let current={status:'locked',settings:audio.settings};
 function paint(value){
  current=value||current;
  const settings=current.settings||audio.settings;
  for(const name of sliders){
   const input=byId('audio-'+name),percent=Math.round((settings[name]??0)*100);
   if(document.activeElement!==input)input.value=String(percent);
   byId('audio-'+name+'-value').value=percent+'%';
   input.setAttribute('aria-valuetext',percent+' percent');
  }
  for(const [name,id] of Object.entries(toggles))byId(id).checked=!!settings[name];
  const messages={locked:'Sound starts with your first click or key press.',ready:settings.muted?'All sound is muted.':'Your sound mix is active.',loading:'Preparing the sound bank…',unavailable:'Audio is unavailable in this browser.'};
  const message=messages[current.status]||messages.ready;
  byId('audio-status').textContent=message;
  byId('audio-enable').classList.toggle('hidden',current.status!=='locked');
  const stateLabel=document.querySelector('.sound-state');
  if(stateLabel)stateLabel.textContent=current.status==='locked'?'Ready after first interaction':current.status==='unavailable'?'Unavailable':settings.muted?'Muted':'Music · effects · cries';
  byId('game-sound').setAttribute('aria-label','Sound settings'+(settings.muted?', currently muted':''));
 }
 function open(){audio.unlock();paint();if(!dialog.open)dialog.showModal();}
 for(const id of ['login-sound','game-sound'])byId(id).addEventListener('click',open);
 byId('audio-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('cancel',event=>{event.preventDefault();event.stopPropagation();dialog.close();});
 byId('audio-enable').addEventListener('click',()=>audio.unlock());
 for(const name of sliders)byId('audio-'+name).addEventListener('input',event=>audio.setSettings({[name]:Number(event.currentTarget.value)/100}));
 for(const [name,id] of Object.entries(toggles))byId(id).addEventListener('change',event=>audio.setSettings({[name]:event.currentTarget.checked}));
 // Pointer/keyboard activation supplies the browser's required user gesture;
 // music never depends on silently changing autoplay settings.
 document.addEventListener('pointerdown',()=>audio.unlock(),{passive:true});
 document.addEventListener('keydown',event=>{if(!event.repeat&&!['Control','Shift','Alt','Meta'].includes(event.key))audio.unlock();});
 document.addEventListener('click',event=>{
  const button=event.target.closest?.('button');
  if(button&&!button.disabled&&!button.closest('#audio-dialog'))audio.ui('select');
 });
 document.addEventListener('change',event=>{if(event.target.matches?.('select')&&!event.target.closest('#audio-dialog'))audio.ui('select');});
 audio.subscribe(paint);paint();
 return {open,setPersistence(saved){byId('audio-persistence').textContent=saved?'Sound preferences are saved on this PC.':'This mix is active for this session. Preferences could not be saved on this PC.';}};
}
