"""Run the maintained two-account browser acceptance fixtures.

The early-alpha harness used piped spawnwild/shutdown input and outdated map/UI
assumptions. Local administration now deliberately rejects pipes. These current
fixtures instead own isolated in-process services and temporary SQLite databases;
there is no pipe bypass, remote admin endpoint or production fixture switch.
Trade/account/network coverage remains in the mandatory Python and Node suites.
Requires Playwright and an installed Chromium/Edge. NXT_QA_BRIDGE=1 selects the
explicit existing testing transport bridge; default transport is native browser.
"""
import asyncio
import os
from pathlib import Path
from check_varieties_browser import main as varieties
from check_cut_browser import main as cut

async def main():
    base=os.environ.get('NXT_QA_OUTPUT')
    try:
        for name,check in (('varieties',varieties),('cut',cut)):
            if base:os.environ['NXT_QA_OUTPUT']=str(Path(base)/name)
            async with asyncio.timeout(180):await check()
    finally:
        if base:os.environ['NXT_QA_OUTPUT']=base

if __name__=='__main__':asyncio.run(main())
