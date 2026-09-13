#!/usr/bin/env python3
"""Build the optional offline audio renderer; no network or ROM is needed here."""
import argparse, concurrent.futures, os
from pathlib import Path
import shutil, subprocess

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--cxx', default='g++', help='GCC 13+ or compatible C++23 compiler')
 p.add_argument('--jobs',type=int,default=2)
 args=p.parse_args();root=Path(__file__).resolve().parent
 cxx=shutil.which(args.cxx)
 if not cxx:raise SystemExit('Optional renderer requires an existing GCC 13+ compiler. Normal BUILD_ALL uses the already extracted audio and does not need this tool.')
 out=root/'obj';out.mkdir(exist_ok=True)
 base=[cxx,'-std=c++23','-O2','-DNDEBUG','-DFMT_HEADER_ONLY','-I'+str(root/'core'),'-I'+str(root/'vendor')]
 def compile_one(src):
  obj=out/(src.stem+'.o');flags=['-mavx2'] if src.name.endswith('AVX2.cpp') else []
  subprocess.run(base+flags+['-c',str(src),'-o',str(obj)],check=True);return obj
 with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,args.jobs)) as pool:objects=list(pool.map(compile_one,sorted((root/'core').glob('*.cpp'))))
 exe=root/('nxt_audio_render.exe' if os.name=='nt' else 'nxt_audio_render')
 subprocess.run(base+[str(root/'render.cpp')]+[str(p) for p in objects]+['-o',str(exe)],check=True)
 print(exe)
if __name__=='__main__':main()
