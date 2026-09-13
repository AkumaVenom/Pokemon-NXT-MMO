#!/usr/bin/env python3
"""Reproduce both packaged sound catalogs from the two supplied local ROM versions.

Requires the optional bundled C++ renderer and local ffmpeg/ffprobe executables.
The normal game build uses packaged OGG assets and never runs this extraction.
"""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, shutil, struct, subprocess, tempfile, time

SOURCE_SPECS={
 'kanto':{'sha256':'729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059','table':0x4a332c,'slots':347},
 'johto':{'sha256':'62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64','table':0xe61608,'slots':516},
}

def recover_missing_base_sample(firered, sigma):
 """Recover the exact erased base instrument, with all ten descriptors verified.
 The data is appended and pointers changed only in a temporary extraction copy.
 """
 original=0x4a3da8;source=0x4a3e08
 if sigma[original:original+16]!=b'\xff'*16:raise ValueError('Unexpected Sigma sample header; refusing recovery')
 size=16+struct.unpack_from('<I',firered,source+12)[0]
 sample=firered[source:source+size]
 if hashlib.sha256(sample).hexdigest()!='ba5005d963318c61c4450e65c75980ff3828ce1923b1a5c0e5b91634a9c57f47':raise ValueError('Unexpected original instrument bytes')
 result=bytearray(sigma);patches=[];pattern=struct.pack('<I',0x8000000+original);pos=0
 while True:
  pos=sigma.find(pattern,pos)
  if pos<0:break
  voice=pos-4;other=voice+0x60
  if not(sigma[voice:voice+4]==firered[other:other+4] and sigma[voice+8:voice+12]==firered[other+8:other+12] and struct.unpack_from('<I',firered,other+4)[0]==0x8000000+source):raise ValueError('Base-instrument identity mismatch')
  patches.append(pos);pos+=4
 if len(patches)!=10:raise ValueError('Unexpected missing-instrument reference count')
 while len(result)%4:result.append(0)
 newpos=len(result);result.extend(sample)
 for pos in patches:struct.pack_into('<I',result,pos,0x8000000+newpos)
 return result,{'destination_region':'johto','damaged_sample_offset':original,'source_region':'kanto','source_offset':source,'bytes':size,'sample_sha256':hashlib.sha256(sample).hexdigest(),'matching_voice_offsets':[p-4 for p in patches],'evidence':'All ten descriptors match supplied FireRed at +0x60: identical type/key/ADSR, same relocated source sample. Original missing base instrument appended to temporary extraction copy; input ROMs untouched.'}


def recover_sequence_prefix(sigma):
 """Restore overwritten 408 setup from the surviving 320 version of its composition.
 Native 408 note data and patterns remain unchanged; relocation preserves 407.
 This is a documented structural reconstruction, not a bit-exact original ROM claim.
 """
 start=0x10249b0;end=0x1024b17;header=0x102552c;reference=0xc8fea0
 expected=bytes.fromhex('bc00bb42bd3cbe50bf58a0b0b0b0b08c')
 if sigma[reference:reference+16]!=expected:raise ValueError('Unexpected same-ROM sequence prefix')
 if sigma[start:start+16]!=bytes.fromhex('4043020972450209f94602094a480209'):raise ValueError('Unexpected corrupt sequence prefix')
 # All five accompanying tracks identify the same native composition uniquely.
 for new,old in [(0x1024b17,0xc90008),(0x1024e65,0xc90349),(0x1024f24,0xc903fe),(0x102515a,0xc905b4),(0x10252a7,0xc906ce)]:
  if sigma[new:new+16]!=sigma[old:old+16]:raise ValueError('Companion-track identity mismatch')
 if struct.unpack_from('<I',sigma,header+8)[0]!=0x8000000+start:raise ValueError('Unexpected target song header')
 result=bytearray(sigma)
 while len(result)%4:result.append(0)
 destination=len(result);track=bytearray(sigma[start:end]);track[:16]=expected;fixes=[]
 for i in range(16,len(track)-3):
  target=struct.unpack_from('<I',track,i)[0]-0x8000000
  if start<=target<end:
   if track[i-1] not in (0xb2,0xb3):raise ValueError('Unexpected internal pointer command')
   fixes.append((i,target-start))
 if len(fixes)!=13 or fixes[-1][1]!=11:raise ValueError('Unexpected pattern/loop topology')
 for i,target in fixes:struct.pack_into('<I',track,i,0x8000000+destination+target)
 result.extend(track);struct.pack_into('<I',result,header+8,0x8000000+destination)
 info={'source_region':'johto','affected_song_ids':[408],'reference_song_id':320,'damaged_track':0,'damaged_prefix_offset':start,'reference_prefix_offset':reference,'prefix_bytes':16,'prefix_sha256':hashlib.sha256(expected).hexdigest(),'tempo_bpm':132,'classification':'structurally validated same-ROM reconstruction','evidence':'Previous song 407 header overwrote exactly 16 setup bytes of song 408 track 0. All five accompanying track prefixes match native song 320; its 16-byte setup fits the gap and both loop targets return to prefix offset 11. Restore that existing setup, relocate track 0 and its 13 internal pointers, preserving all 408 note data and song 407. Input ROM untouched.'}
 return result,info

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--kanto-rom',type=Path,required=True);ap.add_argument('--johto-rom',type=Path,required=True)
 ap.add_argument('--output',type=Path,required=True);ap.add_argument('--jobs',type=int,default=4)
 root=Path(__file__).resolve().parent
 ap.add_argument('--renderer',type=Path,default=root/('nxt_audio_render.exe' if os.name=='nt' else 'nxt_audio_render'))
 ap.add_argument('--ffmpeg',default='ffmpeg');ap.add_argument('--ffprobe',default='ffprobe')
 args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
 for name in ['ffmpeg','ffprobe']:
  value=shutil.which(getattr(args,name))
  if not value:raise SystemExit('Optional extraction requires local '+name)
  setattr(args,name,value)
 if not args.renderer.is_file():raise SystemExit('Build the optional renderer first with python build_renderer.py')
 paths={'kanto':args.kanto_rom.resolve(),'johto':args.johto_rom.resolve()};raw={};sources={};jobs=[]
 for region,path in paths.items():
  data=path.read_bytes();digest=hashlib.sha256(data).hexdigest();spec=SOURCE_SPECS[region]
  if digest!=spec['sha256']:raise SystemExit(f'{region}: unsupported ROM hash; refusing wrong-version extraction')
  raw[region]=data;sources[region]={'rom_sha256':digest,'rom_bytes':len(data),'song_table_offset':spec['table'],'song_table_slots':spec['slots'],'null_ids':[],'silence_ids':[]}
  (out/'songs'/region).mkdir(parents=True,exist_ok=True)
  for i in range(spec['slots']):
   ptr=struct.unpack_from('<I',data,spec['table']+i*8)[0]
   if ptr==0:sources[region]['null_ids'].append(i)
   elif data[ptr-0x8000000]==0:sources[region]['silence_ids'].append(i)
   else:jobs.append((region,i))
 repaired,recovery=recover_missing_base_sample(raw['kanto'],raw['johto'])
 repaired,sequence_recovery=recover_sequence_prefix(repaired)
 with tempfile.TemporaryDirectory(prefix='nxt-audio-extract-') as tmp:
  temp=Path(tmp);paths['johto']=temp/'johto-recovered.gba';paths['johto'].write_bytes(repaired)
  def render(job):
   region,i=job;spec=SOURCE_SPECS[region];key=f'{region}:{i}'
   ogg=out/'songs'/region/f'{i:04d}.ogg';wav=temp/f'{region}-{i:04d}.wav'
   staging=ogg.with_name(ogg.stem+'.partial.ogg')
   start=time.monotonic()
   r=subprocess.run([str(args.renderer),str(paths[region]),hex(spec['table']),str(spec['slots']),str(i),str(wav),'480','44100'],capture_output=True,text=True,timeout=240)
   if r.returncode:raise RuntimeError(f'{key}: renderer failed ({r.returncode}): {r.stderr}')
   m=json.loads(r.stdout.strip().splitlines()[-1]);rate=m['sample_rate']
   if m['capped'] or not m['nonzero_frames']:raise RuntimeError(f'{key}: capped or silent export')
   subprocess.run([args.ffmpeg,'-v','error','-nostdin','-y','-i',str(wav),'-map_metadata','-1','-c:a','libvorbis','-q:a','5',str(staging)],check=True,capture_output=True,timeout=120)
   with staging.open('rb+') as f: f.flush(); os.fsync(f.fileno())
   p=subprocess.run([args.ffprobe,'-v','error','-show_entries','stream=sample_rate,channels:format=duration','-of','json',str(staging)],check=True,capture_output=True,text=True)
   info=json.loads(p.stdout)
   if int(info['streams'][0]['sample_rate'])!=rate or info['streams'][0]['channels']!=2 or abs(float(info['format']['duration'])-m['frames']/rate)>.002:raise RuntimeError(f'{key}: encoded format mismatch')
   os.replace(staging,ogg)
   m.update({'ok':True,'source':region,'file':ogg.relative_to(out).as_posix(),'ogg_bytes':ogg.stat().st_size,'sha256':hashlib.sha256(ogg.read_bytes()).hexdigest(),'duration':m['frames']/rate,'loop':bool(m['loop_end']),'loop_start_frame':m['loop_start'],'loop_end_frame':m['loop_end'],'loop_start':m['loop_start']/rate,'loop_end':m['loop_end']/rate,'render_wall_seconds':round(time.monotonic()-start,3),'renderer_warnings':r.stderr.strip().splitlines()})
   wav.unlink();return key,m
  entries={};start=time.monotonic()
  with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,args.jobs)) as pool:
   futures=[pool.submit(render,job) for job in jobs]
   for n,future in enumerate(concurrent.futures.as_completed(futures),1):
    key,m=future.result();entries[key]=m
    if n%20==0:print(f'{n}/{len(jobs)} rendered, {time.monotonic()-start:.1f}s',flush=True)
  manifest={'format_version':1,'renderer':'bundled agbplay snapshot + NXT adapter','sample_rate':44100,'encoding':'Ogg Vorbis quality5 stereo','sources':sources,'sample_recoveries':[recovery],'sequence_recoveries':[sequence_recovery],'songs':dict(sorted(entries.items()))}
  for key,entry in entries.items():
   asset=out/entry['file'];data=asset.read_bytes()
   if len(data)!=entry['ogg_bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise RuntimeError(f'{key}: final publication integrity failure')
  final=out/'render_manifest.json';staged=out/'render_manifest.partial.json'
  staged.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
  with staged.open('rb+') as f: f.flush(); os.fsync(f.fileno())
  os.replace(staged,final);print(final)
if __name__=='__main__':main()
