/** Shared presentation beats. These never determine server turns or outcomes. */
export const BATTLE_BEAT=Object.freeze({move:600,hit:360,sendout:300,cry:300,battle_start:0,battle_end:0,default:180});
export function battleBeat(event){return BATTLE_BEAT[event?.cue]??BATTLE_BEAT.default;}
export function planBattleEvents(events){let at=0;return (Array.isArray(events)?events:[]).slice(0,24).filter(e=>e&&typeof e.cue==='string').map(event=>{const duration=battleBeat(event),item={event,at,duration};at+=duration;return item;});}
