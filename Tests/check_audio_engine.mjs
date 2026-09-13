/* Browser-free lifecycle verification. No ROM files or audio device required.
 * Run: node Tests/check_audio_engine.mjs */
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
let code = await readFile(new URL('../Client/app/audio.js', import.meta.url), 'utf8');
const timingCode = await readFile(new URL('../Client/app/battle_timing.js', import.meta.url), 'utf8');
code = code.replace("'./battle_timing.js'", JSON.stringify('data:text/javascript;base64,' + Buffer.from(timingCode).toString('base64')));
const {GameAudio, AUDIO_DEFAULTS} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));

class Clock {
  now = 1000;
  next = 0;
  timers = new Map();
  set = (fn, ms) => { const id = ++this.next; this.timers.set(id, {fn, at: this.now + ms}); return id; };
  clear = id => this.timers.delete(id);
  tick(ms) {
    const target = this.now + ms;
    for (;;) {
      const next = [...this.timers].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      const [id, timer] = next;
      this.now = timer.at; this.timers.delete(id); timer.fn();
    }
    this.now = target;
  }
}
class Events {
  listeners = new Map();
  hidden = false;
  focused = true;
  hasFocus() { return this.focused; }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  removeEventListener(name, fn) { if (this.listeners.get(name) === fn) this.listeners.delete(name); }
  fire(name) { this.listeners.get(name)?.(); }
}
class Param {
  value = 1;
  ramps = [];
  cancelAndHoldAtTime() {}
  cancelScheduledValues() {}
  setValueAtTime(value) { this.value = value; }
  linearRampToValueAtTime(value, time) { this.value = value; this.ramps.push([value, time]); }
  exponentialRampToValueAtTime(value, time) { this.value = value; this.ramps.push([value, time]); }
}
class Gain {
  gain = new Param();
  connect(target) { this.target = target; }
  disconnect() { this.disconnected = true; }
}
class Source {
  constructor(context) { this.context = context; this.playbackRate = new Param(); }
  connect(gain) { this.gain = gain; }
  disconnect() { this.disconnected = true; }
  start(at) { this.started = at; this.context.starts.push(this); }
  stop(at) { this.stopped = at; }
  end() { this.onended?.(); }
}
class Context {
  static instances = [];
  state = 'suspended';
  currentTime = 5;
  sampleRate = 44100;
  destination = {};
  starts = [];
  resumes = 0;
  constructor() { Context.instances.push(this); }
  createGain() { return new Gain(); }
  createBufferSource() { return new Source(this); }
  createStereoPanner() { const node = new Gain(); node.pan = new Param(); return node; }
  async decodeAudioData(encoded) {
    const metadata = JSON.parse(new TextDecoder().decode(encoded));
    return {length: metadata.length || 44100, numberOfChannels: metadata.channels || 2, duration: metadata.duration || 1, id: metadata.id};
  }
  async resume() { this.resumes++; this.state = 'running'; this.onstatechange?.(); }
  async close() { this.state = 'closed'; }
}

const catalog = {
  format: 1,
  clips: {
    title: {kind: 'music', path: 'audio/kanto/title.ogg', duration: 12, loopStart: 2, loopEnd: 11},
    route: {kind: 'music', path: 'audio/kanto/route.ogg', duration: 14, loopStart: 3, loopEnd: 13},
    town: {kind: 'music', path: 'audio/kanto/town.ogg', duration: 15, loopStart: 4, loopEnd: 14},
    battle: {kind: 'music', path: 'audio/kanto/battle.ogg', duration: 12, loopStart: 1, loopEnd: 11},
    win: {kind: 'music', path: 'audio/kanto/win.ogg', duration: 5, loop: false, fanfare: true},
    select: {kind: 'effect', path: 'audio/kanto/select.ogg', duration: 0.1},
    hit: {kind: 'effect', path: 'audio/kanto/hit.ogg', duration: 0.2},
    low: {kind: 'effect', path: 'audio/kanto/low.ogg', duration: 1},
    cry: {kind: 'cry', path: 'audio/kanto/cry.ogg', duration: 0.9},
    cry2: {kind: 'cry', path: 'audio/johto/cry2.ogg', duration: 1.1},
  },
  mapMusic: {kanto_1_0: 'route', kanto_1_1: 'route', kanto_2_0: 'town'},
  cries: {fr_1: 'cry', fr_2: 'cry2'},
  cues: {kanto: {title: 'title', battle_wild: 'battle', battle_trainer: 'battle', victory_wild: 'win', victory_trainer: 'win', ui_select: 'select', ui_open: 'select', hit: 'hit', low_hp: 'low', sendout: 'select', chat: 'select'}},
};
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };
const response = (id, metadata = {}) => ({ok: true, arrayBuffer: async () => new TextEncoder().encode(JSON.stringify({id, duration: catalog.clips[id]?.duration || 1, ...metadata})).buffer});

async function make(extra = {}) {
  const clock = new Clock(), document = new Events(), window = new Events(), requests = [];
  const audio = new GameAudio();
  const fetch = async (url, options) => {
    const id = Object.keys(catalog.clips).find(id => url.endsWith(catalog.clips[id].path));
    requests.push({url, options, id});
    return response(id);
  };
  await audio.init({catalog, fetch, AudioContext: Context, document, window, now: () => clock.now, setTimeout: clock.set, clearTimeout: clock.clear, ...extra});
  return {audio, clock, document, window, requests, get context() { return audio._context; }};
}

let count = 0;
async function test(name, fn) { await fn(); count++; process.stdout.write('PASS ' + name + '\n'); }

await test('Catalog initialization creates no context or autoplay; unlock is explicit', async () => {
  const before = Context.instances.length;
  const env = await make();
  assert.equal(Context.instances.length, before);
  assert.equal(env.audio.snapshot().status, 'locked');
  assert.equal(env.requests.length, 0);
  assert.equal(await env.audio.unlock(), true);
  await flush();
  assert.equal(env.context.resumes, 1);
  assert.equal(env.context.starts.length, 1);
  const title = env.context.starts[0];
  assert.equal(title.buffer.id, 'title');
  assert.equal(title.started, 0, 'intro starts at the beginning');
  assert.equal(title.loopStart, 2);
  assert.equal(title.loopEnd, 11);
  assert.equal(title.loop, true);
  await env.audio.shutdown();
});

await test('Adjacent maps sharing a track do not restart music; battle returns to map', async () => {
  const {audio} = await make();
  await audio.unlock(); await flush();
  audio.setScene('world'); audio.setMap('kanto_1_0'); await flush();
  const route = audio._music.source;
  audio.setMap('kanto_1_1'); await flush();
  assert.equal(audio._music.source, route);
  audio.setBattle({id: 'b1', kind: 'wild', you: {hp: 50, maxHp: 100}}); await flush();
  assert.equal(audio.snapshot().music, 'battle');
  audio.setBattle({id: 'b1', kind: 'wild', ended: true, result: 'won'}); await flush();
  assert.equal(audio.snapshot().music, 'win');
  assert.equal(audio._music.source.loop, false);
  audio.setBattle(null); await flush();
  assert.equal(audio.snapshot().music, 'route');
  await audio.shutdown();
});

await test('Latest map wins when earlier music fetch completes later', async () => {
  const pending = deferred();
  const {audio} = await make({fetch: async url => url.includes('/route.') ? pending.promise : response(url.includes('/town.') ? 'town' : 'title')});
  await audio.unlock(); await flush(); audio.setScene('world');
  audio.setMap('kanto_1_0'); await flush();
  audio.setMap('kanto_2_0'); await flush();
  assert.equal(audio.snapshot().music, 'town');
  pending.resolve(response('route')); await flush();
  assert.equal(audio.snapshot().music, 'town');
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'route').length, 0);
  await audio.shutdown();
});

await test('Disconnect aborts pending assets and prevents stale music or effects', async () => {
  const pending = deferred(), effect = deferred(), signals = [];
  const {audio} = await make({fetch: async (url, options) => {
    signals.push(options.signal);
    if (url.includes('/route.')) return pending.promise;
    if (url.includes('/hit.')) return effect.promise;
    return response('title');
  }});
  await audio.unlock(); await flush(); audio.setScene('world'); audio.setMap('kanto_1_0');
  audio.handleEvents({events: [{id: 1, cue: 'hit'}]}); await flush();
  audio.setScene('disconnected');
  const starts = audio._context.starts.length;
  pending.resolve(response('route')); effect.resolve(response('hit')); await flush();
  assert.equal(audio._context.starts.length, starts);
  assert.equal(audio._voices.size, 0);
  assert.equal(audio._eventQueue.length, 0);
  assert(signals.some(signal => signal.aborted));
  await audio.shutdown();
});

await test('Duplicate waiting snapshots do not replay turn sounds', async () => {
  const {audio, clock} = await make();
  await audio.unlock(); await flush(); audio.setScene('world');
  const battle = {id: 'battle-1', kind: 'wild', you: {hp: 50, maxHp: 100}, audio: {revision: 2, events: [{id: 'b1:2:0', cue: 'hit'}, {id: 'b1:2:1', cue: 'cry', species: 'fr_1'}]}};
  audio.setBattle(battle); await flush(); clock.tick(500); await flush();
  audio.setBattle({...battle, waiting: true}); clock.tick(1000); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 1);
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry').length, 1);
  audio.setBattle({...battle, audio: {revision: 3, events: [{id: 'b1:3:0', cue: 'hit'}]}}); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 2);
  await audio.shutdown();
});

await test('Muted or locked history is consumed without delayed replay on unlock', async () => {
  const {audio} = await make(); audio.setScene('world');
  const packet = {events: [{id: 'world:1', cue: 'hit'}]};
  audio.handleEvents(packet);
  await audio.unlock(); await flush(); audio.handleEvents(packet); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 0);
  audio.setSettings({muted: true}); audio.handleEvents({events: [{id: 'world:2', cue: 'hit'}]});
  audio.setSettings({muted: false}); audio.handleEvents({events: [{id: 'world:2', cue: 'hit'}]}); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 0);
  await audio.shutdown();
});

await test('Settings clamp volumes, isolate callback failures, and ramp focus mute', async () => {
  let saved;
  const {audio, window, document} = await make({onSettingsChange: settings => { saved = settings; throw Error('disk full'); }});
  await audio.unlock(); await flush();
  audio.setSettings({master: 9, music: -2, effects: NaN, cries: 0.4, muted: 'false', lowHp: false, unknown: true});
  assert.deepEqual(saved, {...AUDIO_DEFAULTS, master: 1, music: 0, cries: 0.4, lowHp: false});
  const master = audio._gains.master.gain;
  window.fire('blur'); assert.equal(master.value, 0);
  window.fire('focus'); assert.equal(master.value, 1);
  document.hidden = true; document.fire('visibilitychange'); assert.equal(master.value, 0);
  audio.setSettings({muteUnfocused: false}); assert.equal(master.value, 1);
  audio.setSettings({muted: true}); assert.equal(master.value, 0);
  assert(master.ramps.length >= 4);
  await audio.shutdown();
  assert.equal(window.listeners.size, 0); assert.equal(document.listeners.size, 0);
});

await test('Asset requests deduplicate; rapid menu selection coalesces', async () => {
  const wait = deferred(); let calls = 0;
  const {audio} = await make({fetch: async url => {
    if (url.includes('/select.')) { calls++; return wait.promise; }
    return response('title');
  }});
  await audio.unlock(); await flush();
  const one = audio.ui('select'), two = audio.ui('select'), three = audio.ui('open');
  wait.resolve(response('select')); await Promise.all([one, two, three]);
  assert.equal(calls, 1);
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'select').length, 2);
  await audio.shutdown();
});

await test('Stale UI fetch cannot beep several seconds after an interaction', async () => {
  const wait = deferred();
  const {audio, clock} = await make({fetch: async url => url.includes('/select.') ? wait.promise : response('title')});
  await audio.unlock(); await flush(); const play = audio.ui();
  clock.tick(2000); wait.resolve(response('select')); await play;
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'select').length, 0);
  await audio.shutdown();
});

await test('Unavailable clips fail silently and are not fetched every click', async () => {
  let failures = 0;
  const {audio, clock} = await make({fetch: async url => {
    if (url.includes('/select.')) { failures++; throw Error('missing file'); }
    return response('title');
  }});
  await audio.unlock(); await flush();
  for (let i = 0; i < 4; i++) { await audio.ui(); clock.tick(1000); }
  assert.equal(failures, 1); assert.equal(audio.snapshot().failedClips, 1);
  assert.equal(audio.snapshot().status, 'ready');
  await audio.shutdown();
});

await test('Inspection chooses latest Pokemon, even with out-of-order cries', async () => {
  const wait = deferred();
  const {audio, clock} = await make({fetch: async url => url.includes('/cry.') ? wait.promise : response(url.includes('/cry2.') ? 'cry2' : 'title')});
  await audio.unlock(); await flush(); const older = audio.inspectPokemon('fr_1');
  clock.tick(200); await audio.inspectPokemon('fr_2');
  wait.resolve(response('cry')); await older;
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry').length, 0);
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry2').length, 1);
  await audio.shutdown();
});

await test('Low HP loop is singular, optional, and stops on healing or leaving battle', async () => {
  const {audio} = await make(); await audio.unlock(); await flush(); audio.setScene('world');
  const b = {id: 'hp-battle', kind: 'wild', you: {hp: 10, maxHp: 100}};
  audio.setBattle(b); await flush(); audio.setBattle({...b, waiting: true}); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'low').length, 1);
  assert.equal(audio._lowHP.source.loop, true);
  const low = audio._lowHP;
  audio.setSettings({lowHp: false}); assert.equal(low.stopped, true); assert.equal(audio._lowHP, null);
  audio.setSettings({lowHp: true}); await flush(); assert(audio._lowHP);
  const after = audio._lowHP;
  audio.setBattle({...b, you: {hp: 70, maxHp: 100}}); assert(after.stopped); assert.equal(audio._lowHP, null);
  audio.setBattle(null); await flush(); assert.equal(audio._lowHP, null);
  await audio.shutdown();
});

await test('Voice priority limit bounds overlapping clips without evicting music', async () => {
  const {audio} = await make(); await audio.unlock(); await flush();
  const track = audio._music;
  for (let i = 0; i < 60; i++) await audio._effect('hit', {priority: 50, ttl: 1000});
  assert.equal(audio._voices.size, 24);
  assert(audio._voices.has(track)); assert.equal(track.stopped, false);
  await audio.shutdown(); assert.equal(audio._voices.size, 0); assert.equal(audio._cacheBytes, 0);
});

await test('Decoded cache respects 256 MiB while protecting active track buffers', async () => {
  const large = 24 * 1024 * 1024; // frames * 2 channels * 4 = 192 MiB per fake clip
  const {audio} = await make({fetch: async url => response(url.includes('/route.') ? 'route' : 'title', {length: large})});
  await audio.unlock(); await flush(); assert.equal(audio._cacheBytes, 192 * 1024 * 1024);
  await audio._load('route');
  assert(audio._cacheBytes <= 256 * 1024 * 1024);
  assert(audio._cache.has('title')); assert.equal(audio._cache.has('route'), false);
  audio.reset(); await audio._load('route');
  assert.equal(audio._cache.has('title'), false); assert.equal(audio._cache.has('route'), true);
  await audio.shutdown();
});

await test('Untrusted catalog paths never fetch outside the asset folder', async () => {
  const {audio} = await make({catalog: {...catalog, clips: {...catalog.clips, evil: {kind: 'effect', path: 'audio/../../config.ini'}, remote: {kind: 'effect', path: 'https://other.invalid/a.ogg'}}}});
  assert.equal(audio._catalog.clips.evil, undefined); assert.equal(audio._catalog.clips.remote, undefined);
  await audio.shutdown();
});

await test('Late catalog completion remains usable after a scene transition', async () => {
  const wait = deferred(), clock = new Clock(), audio = new GameAudio();
  const init = audio.init({fetch: async url => url.endsWith('catalog.json') ? wait.promise : response('route'), AudioContext: Context, document: null, window: null, now: () => clock.now, setTimeout: clock.set, clearTimeout: clock.clear});
  audio.setScene('world'); audio.setMap('kanto_1_0'); await audio.unlock();
  wait.resolve({ok: true, json: async () => catalog}); await init; await flush();
  assert.equal(audio.snapshot().status, 'ready'); assert.equal(audio.snapshot().music, 'route');
  await audio.shutdown();
});

await test('Event history is bounded and source IDs deduplicate world cues', async () => {
  const {audio} = await make(); audio.setScene('world');
  for (let i = 0; i < 2300; i++) audio.handleEvents({events: [{id: 'seq:' + i, cue: 'hit'}]});
  assert.equal(audio._seen.size, 2048); assert.equal(audio._eventQueue.length, 0);
  await audio.unlock(); await flush();
  const packet = {events: [{id: 'seq:2299', cue: 'hit'}]}; audio.handleEvents(packet); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 0);
  await audio.shutdown();
});

await test('Map inherit/silence flags preserve the native ambient rules', async () => {
  const custom = {...catalog, mapModes: {kanto_9_0: 'inherit', kanto_9_1: 'silence'}, cues: {kanto: {...catalog.cues.kanto, region_default: 'town'}}};
  const {audio} = await make({catalog: custom});
  await audio.unlock(); await flush(); audio.setScene('world'); audio.setMap('kanto_9_0'); await flush();
  assert.equal(audio.snapshot().music, 'town', 'inherit uses region start when there is no earlier map');
  audio.setMap('kanto_1_0'); await flush(); const route = audio._music.source;
  audio.setMap('kanto_9_0'); await flush(); assert.equal(audio._music.source, route);
  audio.setMap('kanto_9_1'); await flush(); assert.equal(audio.snapshot().music, null);
  audio.setMap('kanto_9_0'); await flush(); assert.equal(audio.snapshot().music, null, 'inherit also preserves silence');
  await audio.shutdown();
});

await test('Battle source remains authoritative during cross-region rescue relocation', async () => {
  const custom = {...catalog, cues: {kanto: catalog.cues.kanto, johto: {battle_wild: 'town'}}};
  const {audio} = await make({catalog: custom});
  await audio.unlock(); await flush(); audio.setScene('world'); audio.setMap('kanto_1_0');
  audio.setBattle({id: 'b1', source: 'kanto', kind: 'wild', you: {hp: 10, maxHp: 100}}); await flush();
  audio.setMap('johto_1_0'); await flush(); assert.equal(audio.snapshot().music, 'battle');
  assert.equal(audio._cue('battle_wild', {source: 'johto'}), 'town');
  assert.equal(audio._cue('battle_wild', {source: 'evil'}), 'town', 'invalid source falls back to current region');
  await audio.shutdown();
});

await test('Movement audio only follows accepted ledges and genuine blocked moves', async () => {
  const {audio, clock} = await make({catalog: {...catalog, cues: {kanto: {...catalog.cues.kanto, bump: 'select', ledge: 'hit'}}}});
  await audio.unlock(); await flush(); audio.setScene('world');
  await audio.movement({seq: 1, accepted: false, reason: 'rate'});
  await audio.movement({seq: 2, accepted: false, reason: 'busy'});
  await audio.movement({seq: 3, accepted: false, reason: 'blocked'});
  await audio.movement({seq: 3, accepted: false, reason: 'blocked'});
  clock.tick(300);
  await audio.movement({seq: 4, accepted: true, movement: 'step'});
  await audio.movement({seq: 5, accepted: true, movement: 'jump'});
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'select').length, 1);
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 1);
  await audio.shutdown();
});

await test('Late battle decode cannot delay or play over the following visual beat', async () => {
  const wait = deferred();
  const {audio, clock} = await make({fetch: async url => url.includes('/hit.') ? wait.promise : response(url.includes('/cry.') ? 'cry' : 'battle')});
  await audio.unlock(); await flush(); audio.setScene('world');
  audio.setBattle({id: 'order', kind: 'wild', audio: {revision: 1, events: [{id: '1', cue: 'hit'}, {id: '2', cue: 'cry', species: 'fr_1'}]}});
  clock.tick(400); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry').length, 1);
  wait.resolve(response('hit')); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 0, 'expired hit skipped rather than played out of order');
  await audio.shutdown();
});

await test('Authoritative Surf toggles replace field music without an overlapping effect', async () => {
  const {audio} = await make({catalog: {...catalog, cues: {kanto: {...catalog.cues.kanto, surf: 'town'}}}});
  await audio.unlock(); await flush(); audio.setScene('world'); audio.setMap('kanto_1_0'); await flush();
  audio.handleEvents({events: [{id: 'surf-1', cue: 'surf', enabled: true}]}); await flush();
  assert.equal(audio.snapshot().music, 'town');
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'town').length, 1);
  assert.equal([...audio._voices].filter(v => v.id === 'town')[0].channel, 'music');
  audio.handleEvents({events: [{id: 'surf-2', cue: 'surf', enabled: false}]}); await flush();
  assert.equal(audio.snapshot().music, 'route');
  await audio.shutdown();
});

await test('Native fanfares duck ambient music and restore the chosen music volume', async () => {
  const {audio} = await make(); await audio.unlock(); await flush();
  const fanfare = await audio._effect('win');
  assert.equal(audio._gains.music.gain.value, AUDIO_DEFAULTS.music * 0.15);
  audio.setSettings({music: 0.4}); assert.equal(audio._gains.music.gain.value, 0.4 * 0.15);
  fanfare.source.end(); assert.equal(audio._gains.music.gain.value, 0.4);
  assert.equal(audio._fanfareCount, 0);
  await audio.shutdown();
});

await test('Native move profile uses ROM timing, repeat counts, and perspective pan', async () => {
  const custom = {...catalog, moveSounds: {kanto: {52: {events: [
    {clip: 'select', delaySeconds: 0, repeat: 2, intervalSeconds: 5 / 60, pan: -64},
    {clip: 'hit', delaySeconds: 0.4, pan: 63},
  ], cries: []}}}};
  const {audio, clock} = await make({catalog: custom}); await audio.unlock(); await flush(); audio.setScene('world');
  audio.setBattle({id: 'move', kind: 'wild', audio: {revision: 1, events: [{id: 'move:1:0', cue: 'move', move: 52, source: 'kanto', side: 'opponent', species: 'fr_1'}]}});
  clock.tick(0); await flush();
  let clips = audio._context.starts.filter(s => s.buffer.id === 'select');
  assert.equal(clips.length, 1); assert.equal(clips[0].gain.pan.value, 1);
  clock.tick(90); await flush(); assert.equal(audio._context.starts.filter(s => s.buffer.id === 'select').length, 2);
  clock.tick(320); await flush(); assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 1);
  audio.setBattle(null); await audio.shutdown();
});

await test('Pending native move cues are cancelled when leaving the battle', async () => {
  const custom = {...catalog, moveSounds: {kanto: {22: {events: [{clip: 'hit', delaySeconds: 2, pan: 63}], cries: []}}}};
  const {audio, clock} = await make({catalog: custom}); await audio.unlock(); await flush(); audio.setScene('world');
  audio.setBattle({id: 'cancel-move', kind: 'wild', audio: {revision: 1, events: [{id: 'move1', cue: 'move', move: 22, source: 'kanto'}]}});
  audio.setBattle(null); clock.tick(3000); await flush();
  assert.equal(audio._context.starts.filter(s => s.buffer.id === 'hit').length, 0);
  await audio.shutdown();
});

await test('Reverse cry tasks never substitute the normal cry when reverse data is absent', async () => {
  const custom = {...catalog, moveSounds: {kanto: {45: {events: [], cries: [{side: 'attacker', reverse: true, delaySeconds: 0}]}}}};
  const {audio, clock} = await make({catalog: custom}); await audio.unlock(); await flush(); audio.setScene('world');
  audio.setBattle({id: 'reverse', kind: 'wild', audio: {revision: 1, events: [{id: 'cry-task', cue: 'move', move: 45, source: 'kanto', species: 'fr_1'}]}});
  clock.tick(1000); await flush(); assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry').length, 0);
  await audio.shutdown();
});

await test('Native reverse/forward cry modes honor pitch, note-off, and phase ordering', async () => {
  const rate = 2 ** ((15200 - 15360) / (256 * 12));
  const custom = {...catalog, reverseCries: {fr_1: 'cry2'}, moveSounds: {kanto: {45: {events: [], cries: [
    {side: 'attacker', reverse: true, delaySeconds: 0, playbackRate: rate, noteOffSeconds: 15 / 60, releaseCoefficient: 125 / 256, gain: 0.75},
    {side: 'attacker', reverse: false, delaySeconds: 0, playbackRate: rate, noteOffSeconds: 100 / 60, releaseCoefficient: 225 / 256, afterPreviousCry: true},
  ]}}}};
  const {audio, clock} = await make({catalog: custom}); await audio.unlock(); await flush(); audio.setScene('world');
  audio.setBattle({id: 'growl', kind: 'wild', audio: {revision: 1, events: [{id: 'growl1', cue: 'move', move: 45, source: 'kanto', species: 'fr_1'}]}});
  clock.tick(0); await flush();
  const first = audio._context.starts.find(s => s.buffer.id === 'cry2');
  assert(first); assert.equal(first.playbackRate.value, rate);
  assert(first.stopped > audio._context.currentTime + 0.25 && first.stopped < audio._context.currentTime + 0.5);
  clock.tick(300); await flush(); assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry').length, 0);
  clock.tick(200); await flush(); assert.equal(audio._context.starts.filter(s => s.buffer.id === 'cry').length, 1);
  await audio.shutdown();
});

await test('Oversized two-track transition fades out before replacing its pinned buffer', async () => {
  const frames = 24 * 1024 * 1024, duration = frames / 44100;
  const custom = {...catalog, clips: {...catalog.clips, title: {...catalog.clips.title, duration}, route: {...catalog.clips.route, duration}}};
  const {audio, clock} = await make({catalog: custom, fetch: async url => response(url.includes('/route.') ? 'route' : 'title', {length: frames, duration})});
  await audio.unlock(); await flush(); assert.equal(audio.snapshot().music, 'title');
  // Change only the desired music while preserving a playing old track, as an
  // ordinary map-to-battle transition does; scene reset would free it already.
  audio._scene = 'world'; audio.setMap('kanto_1_0'); await flush();
  assert.equal(audio.snapshot().music, null, 'old track fades out to make room');
  clock.tick(220); await flush();
  assert.equal(audio.snapshot().music, 'route');
  assert(audio._cacheBytes <= 256 * 1024 * 1024);
  assert.equal(audio._cache.has('title'), false);
  await audio.shutdown();
});

await test('Shipped ROM catalog fits native scheduling bounds without dropping primary effects', async () => {
  const shipped = JSON.parse(await readFile(new URL('../Client/app/assets/audio/catalog.json', import.meta.url), 'utf8'));
  const {audio, clock} = await make({catalog: shipped});
  assert.equal(Object.keys(audio._catalog.clips).length, Object.keys(shipped.clips).length, 'all packaged paths are accepted');
  let checked = 0;
  for (const [source, profiles] of Object.entries(shipped.moveSounds)) for (const [move, profile] of Object.entries(profiles)) {
    const before = clock.timers.size;
    const item = {event: {source, move, side: 'you', species: 'fr_1'}, scope: 'battle', epoch: audio._epoch, battleID: null};
    const duration = audio._scheduleMove(profile, item, audio._drainSerial);
    const expectedEffects = profile.events.reduce((sum, event) => sum + (event.repeat || 1), 0);
    assert(clock.timers.size - before >= expectedEffects, `${source} move ${move}: no primary SFX clipped by bounds`);
    assert(duration <= 9500, `${source} move ${move}: bounded sequence`);
    for (const timer of audio._timers) clock.clear(timer);
    audio._timers.clear();
    checked++;
  }
  assert(checked >= 708);
  await audio.shutdown();
});

await test('New battle revision retires tails and pending cues while preserving music and low HP', async () => {
  const custom = {...catalog, moveSounds: {kanto: {52: {events: [{clip:'hit',delaySeconds:0},{clip:'select',delaySeconds:4}],cries:[]}}}};
  const {audio,clock}=await make({catalog:custom}); await audio.unlock();await flush();audio.setScene('world');
  const base={id:'fast',kind:'wild',you:{hp:10,maxHp:100}};
  audio.setBattle({...base,audio:{revision:1,events:[{id:'a',cue:'move',move:52}]}});clock.tick(0);await flush();
  const old=audio._context.starts.find(s=>s.buffer.id==='hit'), music=audio._music, low=audio._lowHP;
  assert(old&&music&&low);
  audio.setBattle({...base,audio:{revision:2,events:[{id:'b',cue:'cry',species:'fr_1'}]}});await flush();
  assert.notEqual(old.stopped,undefined);assert.equal(audio._music,music);assert.equal(audio._lowHP,low);
  clock.tick(500);await flush();assert.equal(audio._context.starts.filter(s=>s.buffer.id==='select').length,0);
  const starts=audio._context.starts.length;
  audio.setBattle({...base,waiting:true,audio:{revision:2,events:[{id:'unexpected-new-id',cue:'hit'}]}});
  audio.setBattle({...base,audio:{revision:1,events:[{id:'stale-new-id',cue:'hit'}]}});await flush();
  assert.equal(audio._context.starts.length,starts);assert.equal(low.stopped,false);
  await audio.shutdown();
});

await test('A decode completing after a newer revision cannot resurrect its old attack', async () => {
  const wait=deferred();
  class SlowDecode extends Context { async decodeAudioData(encoded) { const buffer=await super.decodeAudioData(encoded);if(buffer.id==='hit')await wait.promise;return buffer; } }
  const {audio,clock}=await make({AudioContext:SlowDecode});await audio.unlock();await flush();audio.setScene('world');
  const base={id:'decode',kind:'wild'};
  audio.setBattle({...base,audio:{revision:1,events:[{id:'a',cue:'hit'}]}});await flush();clock.tick(100);
  audio.setBattle({...base,audio:{revision:2,events:[{id:'b',cue:'cry',species:'fr_1'}]}});await flush();
  wait.resolve();await flush();assert.equal(audio._context.starts.filter(s=>s.buffer.id==='hit').length,0);
  assert.equal(audio._context.starts.filter(s=>s.buffer.id==='cry').length,1);await audio.shutdown();
});

await test('Opposing move fades the preceding attack and its hit tail within the same revision', async () => {
  const custom={...catalog,moveSounds:{kanto:{52:{events:[{clip:'select',delaySeconds:0}],cries:[]},33:{events:[{clip:'cry2',delaySeconds:0}],cries:[]}}}};
  const {audio,clock}=await make({catalog:custom});await audio.unlock();await flush();audio.setScene('world');
  audio.setBattle({id:'opposing',kind:'wild',audio:{revision:1,events:[{id:1,cue:'move',move:52,side:'you'},{id:2,cue:'hit'},{id:3,cue:'move',move:33,side:'opponent'}]}});
  clock.tick(0);await flush();const first=audio._context.starts.find(s=>s.buffer.id==='select');assert(first);
  clock.tick(600);await flush();const hit=audio._context.starts.find(s=>s.buffer.id==='hit');assert(hit);
  clock.tick(360);await flush();assert.notEqual(first.stopped,undefined);assert.notEqual(hit.stopped,undefined);
  assert.equal(audio._context.starts.filter(s=>s.buffer.id==='cry2').length,1);await audio.shutdown();
});

await test('A new battle revision preserves queued world reward cues', async () => {
  const {audio,clock}=await make();await audio.unlock();await flush();audio.setScene('world');
  audio.setBattle({id:'reward',kind:'wild',audio:{revision:1,events:[{id:1,cue:'hit'}]}});await flush();
  audio.handleEvents({events:[{id:'reward-world',cue:'ui_select'}]});
  audio.setBattle({id:'reward',kind:'wild',audio:{revision:2,events:[]}});await flush();clock.tick(100);await flush();
  assert.equal(audio._context.starts.filter(s=>s.buffer.id==='select').length,1);await audio.shutdown();
});

await test('Long native scripts retain their sample order inside the compact move beat', async () => {
  const custom={...catalog,moveSounds:{kanto:{52:{events:[{clip:'select',delaySeconds:0},{clip:'hit',delaySeconds:4}],cries:[]}}}};
  const {audio,clock}=await make({catalog:custom});await audio.unlock();await flush();audio.setScene('world');
  audio.setBattle({id:'compact',kind:'wild',audio:{revision:1,events:[{id:1,cue:'move',move:52}]}});
  clock.tick(0);await flush();clock.tick(399);await flush();assert.equal(audio._context.starts.filter(s=>s.buffer.id==='hit').length,0);
  clock.tick(1);await flush();assert.equal(audio._context.starts.filter(s=>s.buffer.id==='hit').length,1);
  assert.deepEqual(audio._context.starts.filter(s=>['select','hit'].includes(s.buffer.id)).map(s=>s.buffer.id),['select','hit']);
  await audio.shutdown();
});

process.stdout.write(`\n${count} audio engine checks passed.\n`);
