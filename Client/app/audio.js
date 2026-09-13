/* ROM-derived audio playback. This module never controls gameplay or trusts audio
 * events as game state. Audio failures remain isolated from the world client. */
export const AUDIO_DEFAULTS = Object.freeze({
  master: 0.8, music: 0.65, effects: 0.8, cries: 0.85,
  muted: false, muteUnfocused: true, lowHp: true, chat: true,
});

const CHANNELS = ['master', 'music', 'effects', 'cries'];
const CACHE_LIMIT = 256 * 1024 * 1024;
const VOICE_LIMIT = 24;
const EVENT_LIMIT = 2048;
const MAX_QUEUE = 64;
const EMPTY_CATALOG = {format: 1, clips: {}, mapMusic: {}, cries: {}, cues: {}};
const clamp = (value, fallback) => typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : fallback;
const releaseSeconds = coefficient => {
  const raw = Number(coefficient) || 0;
  const factor = Math.max(0, Math.min(255 / 256, raw <= 1 ? raw : raw / 256));
  return factor > 0 ? Math.max(0.01, Math.min(1.5, Math.log(0.001) / Math.log(factor) / 60)) : 0.01;
};

function cleanSettings(value = {}, base = AUDIO_DEFAULTS) {
  const result = {...base};
  if (!value || typeof value !== 'object') return result;
  for (const key of CHANNELS) if (value[key] !== undefined) result[key] = clamp(value[key], base[key]);
  for (const key of ['muted', 'muteUnfocused', 'lowHp', 'chat']) if (typeof value[key] === 'boolean') result[key] = value[key];
  return result;
}

function cleanCatalog(value) {
  if (!value || value.format !== 1 || typeof value.clips !== 'object') throw Error('Unsupported audio catalog.');
  const clips = Object.create(null);
  for (const [id, clip] of Object.entries(value.clips || {})) {
    if (!clip || typeof clip.path !== 'string' || !/^audio\/[A-Za-z0-9_./-]+$/.test(clip.path) || clip.path.split('/').includes('..')) continue;
    if (!['music', 'effect', 'cry'].includes(clip.kind)) continue;
    clips[id] = {...clip};
  }
  return {...EMPTY_CATALOG, ...value, clips};
}

export class GameAudio {
  constructor() {
    this._settings = {...AUDIO_DEFAULTS};
    this._catalog = EMPTY_CATALOG;
    this._context = null;
    this._gains = null;
    this._status = 'loading';
    this._scene = 'title';
    this._region = 'kanto';
    this._map = null;
    this._ambient = null;
    this._ambientKnown = false;
    this._surf = false;
    this._battle = null;
    this._battleID = null;
    this._music = null;
    this._musicRequest = null;
    this._musicSerial = 0;
    this._epoch = 0;
    this._cache = new Map();
    this._cacheBytes = 0;
    this._inflight = new Map();
    this._failed = new Map();
    this._voices = new Set();
    this._fanfareCount = 0;
    this._coalesced = new Map();
    this._seen = new Set();
    this._battleSeen = new Set();
    this._listeners = new Set();
    this._timers = new Set();
    this._eventQueue = [];
    this._draining = false;
    this._drainSerial = 0;
    this._lowHP = null;
    this._lowHPRequest = false;
    this._initialized = false;
    this._closed = false;
  }

  /** Initialize catalog/settings without creating or resuming an AudioContext. */
  async init(config = {}) {
    if (this._initialized) return this.snapshot();
    this._initialized = true;
    this._fetch = config.fetch || globalThis.fetch?.bind(globalThis);
    this._Context = config.AudioContext || globalThis.AudioContext || globalThis.webkitAudioContext;
    this._document = config.document === undefined ? globalThis.document : config.document;
    this._window = config.window === undefined ? globalThis.window : config.window;
    this._now = config.now || (() => globalThis.performance?.now() ?? Date.now());
    this._setTimeout = config.setTimeout || globalThis.setTimeout.bind(globalThis);
    this._clearTimeout = config.clearTimeout || globalThis.clearTimeout.bind(globalThis);
    this._persist = typeof config.onSettingsChange === 'function' ? config.onSettingsChange : null;
    this._assets = config.assetsBase || 'assets/';
    this._focused = this._document?.hasFocus ? this._document.hasFocus() : true;
    let initial = config.settings;
    if (!initial) {
      try { initial = JSON.parse(globalThis.localStorage?.getItem('pokemon-nxt-audio') || 'null'); } catch { /* optional fallback */ }
    }
    this._settings = cleanSettings(initial);
    this._focus = () => { this._focused = true; this._applyGains(); this._syncLowHP(); };
    this._blur = () => { this._focused = false; this._applyGains(); };
    this._visibility = () => this._applyGains();
    this._window?.addEventListener('focus', this._focus);
    this._window?.addEventListener('blur', this._blur);
    this._document?.addEventListener('visibilitychange', this._visibility);
    try {
      if (config.catalog) this._catalog = cleanCatalog(config.catalog);
      else {
        this._catalogAbort = new AbortController();
        const response = await this._fetch(config.catalogUrl || this._assets + 'audio/catalog.json', {signal: this._catalogAbort.signal});
        if (!response.ok) throw Error('Audio catalog unavailable.');
        this._catalog = cleanCatalog(await response.json());
      }
      if (this._closed) return this.snapshot();
      this._status = this._Context && Object.keys(this._catalog.clips).length ? (this._context?.state === 'running' ? 'ready' : 'locked') : 'unavailable';
      this._updateAmbient();
      this._notify();
      this._syncMusic();
    } catch {
      if (!this._closed) { this._status = 'unavailable'; this._notify(); }
    } finally { this._catalogAbort = null; }
    return this.snapshot();
  }

  get settings() { return {...this._settings}; }
  snapshot() { return {status: this._status, settings: this.settings, music: this._music?.id || null, failedClips: this._failed.size}; }
  subscribe(callback) {
    if (typeof callback !== 'function') return () => {};
    this._listeners.add(callback);
    try { callback(this.snapshot()); } catch { /* view callbacks cannot break audio */ }
    return () => this._listeners.delete(callback);
  }
  _notify() { for (const callback of this._listeners) try { callback(this.snapshot()); } catch { /* isolated observer */ } }

  /** Call synchronously from a trusted click/key/pointer handler. Never auto-resume. */
  async unlock() {
    if (this._closed || !this._initialized || !this._Context) return false;
    try {
      if (!this._context) {
        // Match the extracted PCM rate instead of needlessly expanding long
        // soundtracks to a high-rate desktop output device during decoding.
        try { this._context = new this._Context({sampleRate: 44100}); }
        catch { this._context = new this._Context(); }
        this._gains = {};
        for (const name of CHANNELS) this._gains[name] = this._context.createGain();
        if (this._context.createDynamicsCompressor) {
          this._limiter = this._context.createDynamicsCompressor();
          for (const [name, value] of Object.entries({threshold: -3, knee: 6, ratio: 12, attack: 0.002, release: 0.12})) this._limiter[name].setValueAtTime(value, this._context.currentTime);
          this._gains.master.connect(this._limiter);
          this._limiter.connect(this._context.destination);
        } else this._gains.master.connect(this._context.destination);
        for (const name of CHANNELS.slice(1)) this._gains[name].connect(this._gains.master);
        this._applyGains(true);
        this._context.onstatechange = () => {
          if (this._closed || this._status === 'unavailable' || this._status === 'loading') return;
          this._status = this._context.state === 'running' ? 'ready' : 'locked';
          this._notify();
        };
      }
      // The resume invocation stays before the first await to retain user activation.
      const resumed = this._context.state === 'running' ? undefined : this._context.resume();
      await resumed;
      if (this._closed || this._context.state !== 'running') return false;
      if (this._status !== 'loading' && this._status !== 'unavailable') this._status = 'ready';
      this._notify();
      this._syncMusic();
      this._syncLowHP();
      return true;
    } catch { this._status = 'locked'; this._notify(); return false; }
  }

  setSettings(patch) {
    this._settings = cleanSettings(patch, this._settings);
    this._applyGains();
    this._syncLowHP();
    try { globalThis.localStorage?.setItem('pokemon-nxt-audio', JSON.stringify(this._settings)); } catch { /* durable launcher persistence is preferred */ }
    if (this._persist) try { Promise.resolve(this._persist(this.settings)).catch(() => {}); } catch { /* settings save must not interrupt play */ }
    this._notify();
    return this.settings;
  }

  _applyGains(immediate = false) {
    if (!this._gains) return;
    const background = this._settings.muteUnfocused && (!this._focused || this._document?.hidden);
    for (const name of CHANNELS) {
      let value = name === 'master' && (this._settings.muted || background) ? 0 : this._settings[name];
      if (name === 'music' && this._fanfareCount) value *= 0.15;
      this._ramp(this._gains[name].gain, value, immediate ? 0 : 0.035);
    }
  }

  _ramp(param, value, seconds) {
    const now = this._context.currentTime;
    if (param.cancelAndHoldAtTime) param.cancelAndHoldAtTime(now);
    else { param.cancelScheduledValues(now); param.setValueAtTime(param.value, now); }
    if (seconds) param.linearRampToValueAtTime(value, now + seconds);
    else param.setValueAtTime(value, now);
  }

  setRegion(region) {
    const normalized = String(region).toLowerCase();
    if (!['kanto', 'johto'].includes(normalized) || normalized === this._region) return;
    this._region = normalized;
    this._syncMusic();
  }

  setMap(mapID, surf = false) {
    const previousRegion = this._region;
    this._map = typeof mapID === 'string' ? mapID : null;
    this._surf = !!surf;
    if (this._map?.startsWith('johto_')) this._region = 'johto';
    else if (this._map?.startsWith('kanto_')) this._region = 'kanto';
    if (previousRegion !== this._region) { this._ambient = null; this._ambientKnown = false; }
    this._updateAmbient();
    this._syncMusic();
  }

  _updateAmbient() {
    if (!this._map || this._status === 'loading') return;
    const mode = this._catalog.mapModes?.[this._map];
    if (mode === 'inherit') {
      if (!this._ambientKnown) this._ambient = this._cue('region_default') || this._cue('world');
      this._ambientKnown = true;
    } else {
      this._ambient = mode === 'silence' ? null : (this._catalog.mapMusic?.[this._map] || null);
      this._ambientKnown = true;
    }
  }

  setScene(scene) {
    if (!['title', 'world', 'disconnected'].includes(scene) || this._closed) return;
    if (scene !== this._scene) {
      this.reset();
      this._scene = scene;
    }
    this._syncMusic();
  }

  setBattle(snapshot) {
    if (this._closed) return;
    const battleID = snapshot?.id ?? null;
    if (battleID !== this._battleID || (!snapshot && this._battle)) {
      this._cancelQueue();
      this._battleSeen.clear();
      for (const voice of [...this._voices]) if (voice.scope === 'battle') this._stopVoice(voice, 0.045);
      this._battleID = battleID;
      this._lowHP = null;
      this._lowHPRequest = false;
    }
    this._battle = snapshot || null;
    this._syncMusic();
    if (snapshot?.audio) this._enqueue(snapshot.audio, this._battleSeen, 'battle', String(battleID));
    this._syncLowHP();
  }

  handleEvents(packet) {
    if (!packet || this._scene !== 'world' || this._closed) return;
    this._enqueue(packet.audio || packet, this._seen, 'world', String(packet.source || 'world'));
  }

  _cue(cue, data = {}) {
    const region = ['kanto', 'johto'].includes(data.source) ? data.source : this._region;
    const cues = this._catalog.cues?.[region] || {};
    if (cue === 'cry' || cue === 'send_out' || cue === 'pokemon_cry') return this._catalog.cries?.[data.species] || this._catalog.cries?.[region]?.[data.species] || null;
    const candidates = [];
    if (cue === 'move') {
      if (data.move != null) candidates.push('move_' + data.move);
      if (data.moveType != null) candidates.push('move_type_' + String(data.moveType).toLowerCase());
    }
    if (cue === 'hit') {
      if (Number(data.effectiveness) === 0) candidates.push('hit_immune');
      else if (Number(data.effectiveness) > 1) candidates.push('hit_super');
      else if (Number(data.effectiveness) < 1) candidates.push('hit_weak');
    }
    candidates.push(cue);
    for (const name of candidates) if (typeof cues[name] === 'string' && this._catalog.clips[cues[name]]) return cues[name];
    return null;
  }

  _desiredMusic() {
    if (this._scene === 'disconnected') return null;
    if (this._scene === 'title') return this._cue('title');
    if (this._battle) {
      const b = this._battle;
      if (!b.ended) return this._cue(b.kind === 'wild' ? 'battle_wild' : 'battle_trainer', b);
      if (b.result === 'won') return this._cue(b.kind === 'wild' ? 'victory_wild' : 'victory_trainer', b) || this._cue('victory', b);
      if (b.result === 'caught') return this._cue('victory_caught', b) || this._cue('victory_wild', b) || this._cue('victory', b);
      if (b.result === 'lost') return this._cue('defeat', b);
    }
    return (this._surf && this._cue('surf')) || this._ambient;
  }

  _syncMusic() {
    if (!this._context || this._context.state !== 'running' || this._closed) return;
    const id = this._desiredMusic();
    if (this._musicRequest === id && (this._music?.id === id || this._musicPending)) return;
    const serial = ++this._musicSerial;
    const epoch = this._epoch;
    this._musicRequest = id;
    this._musicPending = false;
    if (!id || !this._catalog.clips[id]) {
      if (this._music) this._stopVoice(this._music, 0.3);
      this._music = null;
      this._notify();
      return;
    }
    if (this._music?.id === id) return;
    this._musicPending = true;
    this._loadMusic(id, serial, epoch).then(buffer => {
      if (this._closed || epoch !== this._epoch || serial !== this._musicSerial) return;
      this._musicPending = false;
      if (!buffer) {
        if (this._music) this._stopVoice(this._music, 0.3);
        this._music = null;
        this._notify();
        return;
      }
      const old = this._music;
      const voice = this._startVoice(id, buffer, {channel: 'music', priority: 100, fadeIn: old ? 0.5 : 0.18, loop: this._catalog.clips[id].loop !== false, scope: 'music'});
      if (!voice) return;
      this._music = voice;
      if (old) this._stopVoice(old, 0.5);
      this._notify();
    }).catch(() => {});
  }

  async _loadMusic(id, serial, epoch) {
    // Music must not be dropped just because a burst of short effects or map
    // transitions filled the loader. Only the newest desired track may retry.
    while (this._inflight.size >= 4 && !this._inflight.has(id) && !this._cache.has(id)) {
      await Promise.race([...this._inflight.values()].map(item => item.promise));
      if (this._closed || serial !== this._musicSerial || epoch !== this._epoch) return null;
    }
    if (this._closed || serial !== this._musicSerial || epoch !== this._epoch) return null;
    if (!this._cache.has(id)) {
      const estimatedBytes = Math.ceil((Number(this._catalog.clips[id]?.duration) || 0) * (this._context.sampleRate || 44100) * 2 * 4);
      const pinnedBytes = [...this._cache.values()].reduce((sum, entry) => sum + (entry.refs ? entry.bytes : 0), 0);
      if (estimatedBytes <= CACHE_LIMIT && pinnedBytes + estimatedBytes > CACHE_LIMIT) {
        // Large future soundtracks or high-rate fallback contexts may not fit
        // two songs at once. Use a brief fade-out/in instead of dropping the new
        // track or decoding indefinitely against a pinned old music buffer.
        const retiring = [...this._voices].filter(voice => voice.channel === 'music');
        for (const voice of retiring) this._stopVoice(voice, 0.18);
        if (retiring.includes(this._music)) { this._music = null; this._notify(); }
        if (retiring.length) {
          await new Promise(resolve => this._later(resolve, 210));
          for (const voice of retiring) voice.cleanup();
          if (this._closed || serial !== this._musicSerial || epoch !== this._epoch) return null;
        }
      }
      this._evict(estimatedBytes);
    }
    return this._load(id);
  }

  _readyForEffect() {
    return !this._closed && this._context?.state === 'running' && this._status === 'ready' && this._scene !== 'disconnected' && !this._settings.muted && (!this._settings.muteUnfocused || (this._focused && !this._document?.hidden));
  }

  ui(cue = 'select') {
    if (cue === 'chat' && !this._settings.chat) return Promise.resolve(null);
    const aliases = {select: 'ui_select', cancel: 'ui_cancel', error: 'ui_error', confirm: 'ui_confirm', open: 'ui_open', close: 'ui_close'};
    const id = this._cue(aliases[cue] || cue) || this._cue(cue);
    return this._effect(id, {priority: 20, coalesce: 'ui:' + cue, interval: 75, scope: 'ui', ttl: 350});
  }

  inspectPokemon(species) {
    const id = this._cue('cry', {species});
    // Inspecting rapidly should never produce a choir of stale cries.
    for (const voice of [...this._voices]) if (voice.scope === 'inspection') this._stopVoice(voice, 0.035);
    this._inspectionSerial = (this._inspectionSerial || 0) + 1;
    return this._effect(id, {channel: 'cries', priority: 65, scope: 'inspection', coalesce: 'inspection', interval: 180, ttl: 800, inspection: this._inspectionSerial});
  }

  /** Accepted movement only; ordinary GBA walking is intentionally quiet. */
  movement(move, previous = null) {
    if (this._battle || this._scene !== 'world') return;
    if (move?.entity && this._map) this.setMap(this._map, move.entity.surf);
    if (move?.seq != null) {
      if (move.seq <= (this._moveSequence ?? -1)) return;
      this._moveSequence = move.seq;
    }
    if (move?.accepted === false && move.reason === 'blocked') return this._effect(this._cue('bump'), {priority: 10, scope: 'world', coalesce: 'bump', interval: 240, ttl: 250});
    if (move?.accepted === true && move.movement === 'jump') return this._effect(this._cue('ledge'), {priority: 10, scope: 'world', coalesce: 'movement', interval: 100, ttl: 250});
  }

  _enqueue(packet, seen, scope, source) {
    const events = Array.isArray(packet.events) ? packet.events.slice(0, MAX_QUEUE) : [];
    for (let index = 0; index < events.length; index++) {
      const event = events[index];
      if (!event || typeof event.cue !== 'string') continue;
      const id = event.id != null ? source + ':' + String(event.id) : packet.revision != null ? source + ':' + packet.revision + ':' + index : null;
      // Network cues must have stable identity. Never replay waiting snapshots.
      if (id === null || seen.has(id)) continue;
      seen.add(id);
      if (seen.size > EVENT_LIMIT) seen.delete(seen.values().next().value);
      if (event.cue === 'surf') {
        if (typeof event.enabled === 'boolean') { this._surf = event.enabled; this._syncMusic(); }
        continue;
      }
      if (!this._readyForEffect() || this._eventQueue.length >= MAX_QUEUE) continue;
      if (event.cue === 'chat' && !this._settings.chat) continue;
      if (!['battle_start', 'battle_end'].includes(event.cue)) this._eventQueue.push({event, scope, epoch: this._epoch, battleID: this._battleID});
      if (event.cue === 'sendout' && event.species && this._eventQueue.length < MAX_QUEUE) this._eventQueue.push({event: {...event, cue: 'cry'}, scope, epoch: this._epoch, battleID: this._battleID});
      if (event.cue === 'party_changed' && event.leadChanged && event.species && this._eventQueue.length < MAX_QUEUE) this._eventQueue.push({event: {...event, cue: 'cry'}, scope, epoch: this._epoch, battleID: this._battleID});
    }
    this._drainQueue();
  }

  _drainQueue() {
    if (this._draining || !this._eventQueue.length || !this._readyForEffect()) return;
    this._draining = true;
    const serial = this._drainSerial;
    const next = () => {
      if (serial !== this._drainSerial) return;
      const item = this._eventQueue.shift();
      if (!item || !this._readyForEffect()) { this._draining = false; this._eventQueue.length = 0; return; }
      if (item.epoch !== this._epoch || (item.scope === 'battle' && item.battleID !== this._battleID)) { next(); return; }
      const source = ['kanto', 'johto'].includes(item.event.source) ? item.event.source : this._region;
      const move = item.event.cue === 'move' ? this._catalog.moveSounds?.[source]?.[item.event.move] : null;
      if (move && typeof move === 'object') {
        const duration = this._scheduleMove(move, item, serial);
        this._later(next, Math.max(100, duration));
        return;
      }
      const id = this._cue(item.event.cue, item.event);
      const channel = this._catalog.clips[id]?.kind === 'cry' ? 'cries' : 'effects';
      const duration = Number(this._catalog.clips[id]?.duration) || 0.2;
      // Preserve event order without making combat wait for sound loading. Bound
      // backlog latency; a long cry cannot stall an entire turn's audio queue.
      const interval = Math.max(85, Math.min(channel === 'cries' ? 850 : 360, duration * 850));
      let advanced = false;
      const advance = (played) => {
        if (advanced || serial !== this._drainSerial) return;
        advanced = true;
        this._clearTimeout(deadline);
        this._timers.delete(deadline);
        this._later(next, played ? interval : 0);
      };
      const deadline = this._later(() => advance(false), 850);
      this._effect(id, {channel, scope: item.scope, priority: channel === 'cries' ? 70 : 50, ttl: 800}).then(voice => advance(!!voice)).catch(() => advance(false));
    };
    next();
  }

  _scheduleMove(move, item, serial) {
    const scheduled = [];
    const direction = item.event.side === 'opponent' ? -1 : 1;
    for (const event of (Array.isArray(move.events) ? move.events : []).slice(0, 48)) {
      if (!event || typeof event.clip !== 'string' || !this._catalog.clips[event.clip]) continue;
      const delay = Number(event.delaySeconds), interval = Number(event.intervalSeconds);
      if (!Number.isFinite(delay) || delay < 0 || delay > 8) continue;
      const count = Math.max(1, Math.min(16, Math.trunc(Number(event.repeat) || 1)));
      for (let repeat = 0; repeat < count && scheduled.length < 48; repeat++) {
        const at = delay + repeat * (Number.isFinite(interval) ? Math.max(1 / 60, Math.min(2, interval)) : 1 / 60);
        if (at > 8) break;
        scheduled.push({id: event.clip, at, channel: 'effects', pan: Number.isFinite(Number(event.pan)) ? Math.max(-1, Math.min(1, Number(event.pan) / 64)) * direction : 0});
      }
    }
    let previousCryEnd = 0;
    for (const cry of (Array.isArray(move.cries) ? move.cries : []).slice(0, 8)) {
      const delay = Number(cry.delaySeconds);
      if (!Number.isFinite(delay) || delay < 0 || delay > 8) continue;
      const defender = item.event.side === 'opponent' ? this._battle?.you : this._battle?.opponent;
      const species = cry.side === 'defender' ? defender?.species : item.event.species;
      const id = cry.reverse ? this._catalog.reverseCries?.[species] : this._cue('cry', {species, source: item.event.source});
      if (!id || !this._catalog.clips[id]) continue;
      const rate = Math.max(0.5, Math.min(2, Number(cry.playbackRate ?? cry.rate) || 1));
      const noteOff = typeof cry.noteOffSeconds === 'number' && Number.isFinite(cry.noteOffSeconds) ? Math.max(0, Math.min(4, cry.noteOffSeconds)) : null;
      const envelopeDuration = noteOff === null ? Infinity : noteOff + releaseSeconds(cry.releaseCoefficient ?? 200);
      const cryDuration = Math.min((Number(this._catalog.clips[id].duration) || 1) / rate, envelopeDuration);
      const phaseGap = Math.max(2 / 60, Math.min(1, Number(cry.minimumStartDelaySeconds) || 0));
      const base = cry.afterPreviousCry ? Math.max(delay, previousCryEnd + phaseGap) : delay;
      const rawGain = cry.gain ?? cry.volume;
      const count = Math.max(1, Math.min(4, Math.trunc(Number(cry.repeat) || 1)));
      for (let repeat = 0; repeat < count && scheduled.length < 48; repeat++) {
        const at = base + repeat * Math.max(0.06, Math.min(1, Number(cry.intervalSeconds) || 0.2));
        if (at > 8) break;
        previousCryEnd = at + cryDuration;
        scheduled.push({id, at, duration: cryDuration, channel: 'cries', pan: (cry.side === 'defender' ? 0.6 : -0.6) * direction, rate, noteOff, release: releaseSeconds(cry.releaseCoefficient ?? 200), volume: Math.max(0, Math.min(1.5, Number.isFinite(rawGain) ? rawGain : 1))});
      }
    }
    let duration = 0;
    for (const sound of scheduled) {
      const tail = Math.min(sound.channel === 'cries' ? 1.5 : 0.36, sound.duration || Number(this._catalog.clips[sound.id]?.duration) || 0.1);
      duration = Math.max(duration, (sound.at + tail) * 1000);
      this._later(() => {
        if (serial !== this._drainSerial || item.epoch !== this._epoch || item.battleID !== this._battleID) return;
        void this._effect(sound.id, {channel: sound.channel, scope: item.scope, priority: sound.channel === 'cries' ? 70 : 50, ttl: 350, pan: sound.pan, rate: sound.rate, volume: sound.volume, noteOff: sound.noteOff, release: sound.release});
      }, sound.at * 1000);
    }
    return duration;
  }

  async _effect(id, options = {}) {
    if (!id || !this._catalog.clips[id] || !this._readyForEffect()) return null;
    const channel = options.channel || (this._catalog.clips[id].kind === 'cry' ? 'cries' : 'effects');
    if (!this._settings[channel] || !this._settings.master) return null;
    const now = this._now();
    if (options.coalesce) {
      if (now - (this._coalesced.get(options.coalesce) ?? -Infinity) < (options.interval || 80)) return null;
      this._coalesced.set(options.coalesce, now);
      if (this._coalesced.size > 256) this._coalesced.delete(this._coalesced.keys().next().value);
    }
    const epoch = this._epoch;
    const battleID = this._battleID;
    const buffer = await this._load(id);
    if (!buffer || epoch !== this._epoch || !this._readyForEffect() || this._now() - now > (options.ttl || 1000)) return null;
    if (options.scope === 'battle' && battleID !== this._battleID) return null;
    if (options.inspection && options.inspection !== this._inspectionSerial) return null;
    const clip = this._catalog.clips[id];
    try { return this._startVoice(id, buffer, {...options, channel, loop: false, fanfare: clip.fanfare === true}); } catch { return null; }
  }

  _syncLowHP() {
    const mon = this._battle?.you;
    const shouldPlay = !!(this._settings.lowHp && this._battle && !this._battle.ended && mon && mon.hp > 0 && mon.maxHp > 0 && mon.hp / mon.maxHp <= 0.2);
    this._lowHPWanted = shouldPlay;
    if (!shouldPlay) {
      if (this._lowHP) this._stopVoice(this._lowHP, 0.08);
      this._lowHP = null;
      return;
    }
    if (this._lowHP || this._lowHPRequest || !this._readyForEffect()) return;
    const id = this._cue('low_hp', this._battle);
    if (!id) return;
    const epoch = this._epoch, battleID = this._battleID;
    this._lowHPRequest = true;
    this._load(id).then(buffer => {
      this._lowHPRequest = false;
      if (!buffer || epoch !== this._epoch || battleID !== this._battleID || !this._lowHPWanted || !this._readyForEffect()) return;
      this._lowHP = this._startVoice(id, buffer, {channel: 'effects', priority: 35, volume: 0.3, scope: 'battle', loop: true, fadeIn: 0.05});
    }).catch(() => { this._lowHPRequest = false; });
  }

  async _load(id) {
    if (this._cache.has(id)) {
      const entry = this._cache.get(id);
      entry.used = this._now();
      return entry.buffer;
    }
    if (this._inflight.has(id)) return this._inflight.get(id).promise;
    if (!this._context || !this._fetch || (this._failed.has(id) && this._now() - this._failed.get(id) < 30000)) return null;
    // Bound simultaneous downloads/decodes as well as resident decoded memory.
    if (this._inflight.size >= 4) return null;
    const clip = this._catalog.clips[id];
    if (!clip) return null;
    const controller = new AbortController(), epoch = this._epoch;
    const promise = (async () => {
      try {
        const response = await this._fetch(this._assets + clip.path, {signal: controller.signal});
        if (!response.ok) throw Error('Audio clip unavailable.');
        const encoded = await response.arrayBuffer();
        if (controller.signal.aborted || epoch !== this._epoch || this._closed) return null;
        const buffer = await this._context.decodeAudioData(encoded);
        if (controller.signal.aborted || epoch !== this._epoch || this._closed) return null;
        const bytes = buffer.length * buffer.numberOfChannels * 4;
        if (!Number.isFinite(bytes) || bytes <= 0 || bytes > CACHE_LIMIT) throw Error('Audio clip exceeds memory budget.');
        this._evict(bytes);
        // Active music is pinned; decline additional clips rather than grow
        // resident memory beyond the budget on a constrained client.
        if (this._cacheBytes + bytes > CACHE_LIMIT) return null;
        this._cache.set(id, {buffer, bytes, refs: 0, used: this._now()});
        this._cacheBytes += bytes;
        this._failed.delete(id);
        return buffer;
      } catch {
        if (!controller.signal.aborted && !this._closed) { this._failed.set(id, this._now()); this._notify(); }
        return null;
      } finally { if (this._inflight.get(id)?.controller === controller) this._inflight.delete(id); }
    })();
    this._inflight.set(id, {promise, controller});
    return promise;
  }

  _evict(required = 0) {
    const entries = [...this._cache.entries()].filter(([, entry]) => !entry.refs).sort((a, b) => a[1].used - b[1].used);
    for (const [id, entry] of entries) {
      if (this._cacheBytes + required <= CACHE_LIMIT) break;
      this._cache.delete(id);
      this._cacheBytes -= entry.bytes;
    }
  }

  _startVoice(id, buffer, options) {
    const entry = this._cache.get(id);
    if (!entry || entry.buffer !== buffer) return null;
    if (this._voices.size >= VOICE_LIMIT) {
      const victim = [...this._voices].filter(v => v.channel !== 'music' && v.priority <= options.priority).sort((a, b) => a.priority - b.priority || a.started - b.started)[0];
      if (!victim) return null;
      this._stopVoice(victim, 0);
    }
    const source = this._context.createBufferSource(), gain = this._context.createGain();
    const clip = this._catalog.clips[id];
    const voice = {id, source, gain, channel: options.channel, scope: options.scope, priority: options.priority || 0, started: this._now(), entry, stopped: false, fanfare: !!options.fanfare};
    source.buffer = buffer;
    source.loop = !!options.loop;
    if (options.rate && source.playbackRate) source.playbackRate.setValueAtTime(options.rate, this._context.currentTime);
    if (source.loop) {
      const start = Number(clip.loopStart), end = Number(clip.loopEnd);
      // Starting at zero plays the intro once, then Web Audio loops sample-
      // accurately between the extracted driver loop boundaries.
      source.loopStart = Number.isFinite(start) && start >= 0 && start < buffer.duration ? start : 0;
      source.loopEnd = Number.isFinite(end) && end > source.loopStart && end <= buffer.duration + 0.02 ? Math.min(end, buffer.duration) : buffer.duration;
    }
    let panner = null;
    if (Number.isFinite(options.pan) && this._context.createStereoPanner) {
      panner = this._context.createStereoPanner();
      panner.pan.setValueAtTime(Math.max(-1, Math.min(1, options.pan)), this._context.currentTime);
      source.connect(panner); panner.connect(gain);
    } else source.connect(gain);
    gain.connect(this._gains[options.channel]);
    gain.gain.setValueAtTime(options.fadeIn ? 0 : (options.volume ?? 1), this._context.currentTime);
    if (options.fadeIn) gain.gain.linearRampToValueAtTime(options.volume ?? 1, this._context.currentTime + options.fadeIn);
    const cleanup = () => {
      if (voice.cleaned) return;
      voice.cleaned = true;
      this._voices.delete(voice);
      if (entry) entry.refs = Math.max(0, entry.refs - 1);
      if (voice.fanfare) { this._fanfareCount = Math.max(0, this._fanfareCount - 1); this._applyGains(); }
      if (this._lowHP === voice) this._lowHP = null;
      try { source.disconnect(); panner?.disconnect(); gain.disconnect(); } catch { /* already disconnected */ }
      this._evict();
    };
    voice.cleanup = cleanup;
    source.onended = cleanup;
    this._voices.add(voice);
    if (voice.fanfare) { this._fanfareCount++; this._applyGains(); }
    if (entry) entry.refs++;
    try { source.start(0); } catch { cleanup(); return null; }
    if (typeof options.noteOff === 'number' && options.noteOff >= 0) {
      const end = Math.min(buffer.duration / (options.rate || 1), options.noteOff + (options.release || 0.01));
      const beginRelease = Math.min(options.noteOff, end);
      const volume = Math.max(0.00001, options.volume ?? 1);
      gain.gain.setValueAtTime(volume, this._context.currentTime + beginRelease);
      if (gain.gain.exponentialRampToValueAtTime) gain.gain.exponentialRampToValueAtTime(Math.max(0.00001, volume * 0.001), this._context.currentTime + end);
      else gain.gain.linearRampToValueAtTime(0, this._context.currentTime + end);
      source.stop(this._context.currentTime + end);
      this._later(cleanup, end * 1000 + 100);
    }
    return voice;
  }

  _stopVoice(voice, fade = 0) {
    if (!voice || voice.stopped) return;
    voice.stopped = true;
    try {
      if (fade) this._ramp(voice.gain.gain, 0, fade);
      voice.source.stop(this._context.currentTime + fade);
    } catch { /* source may already have ended */ }
    // Browsers suspend on backgrounding; immediate reset must still release
    // resources even when the audio clock cannot dispatch onended.
    if (!fade) voice.cleanup();
    else this._later(voice.cleanup, fade * 1000 + 100);
  }

  _later(callback, ms) {
    const timer = this._setTimeout(() => { this._timers.delete(timer); callback(); }, ms);
    this._timers.add(timer);
    return timer;
  }

  _cancelQueue() {
    this._drainSerial++;
    this._eventQueue.length = 0;
    this._draining = false;
  }

  /** Clear transient session audio, retaining decoded assets and preferences. */
  reset() {
    this._epoch++;
    this._musicSerial++;
    this._musicRequest = null;
    this._musicPending = false;
    this._cancelQueue();
    for (const item of this._inflight.values()) item.controller.abort();
    this._inflight.clear();
    for (const timer of this._timers) this._clearTimeout(timer);
    this._timers.clear();
    for (const voice of [...this._voices]) this._stopVoice(voice, 0);
    this._music = null;
    this._lowHP = null;
    this._lowHPRequest = false;
    this._lowHPWanted = false;
    this._battle = null;
    this._battleID = null;
    this._map = null;
    this._ambient = null;
    this._ambientKnown = false;
    this._surf = false;
    this._moveSequence = -1;
    this._seen.clear();
    this._battleSeen.clear();
    this._coalesced.clear();
    this._notify();
  }

  async shutdown() {
    if (this._closed) return;
    this._closed = true;
    this._catalogAbort?.abort();
    this.reset();
    this._window?.removeEventListener('focus', this._focus);
    this._window?.removeEventListener('blur', this._blur);
    this._document?.removeEventListener('visibilitychange', this._visibility);
    this._listeners.clear();
    this._cache.clear();
    this._cacheBytes = 0;
    if (this._context) { this._context.onstatechange = null; try { await this._context.close(); } catch { /* browser shutting down */ } }
  }
}
