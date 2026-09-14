# Windows build correction · Build tools 1.3.4

Release date: **2026-09-14**. Based on the complete **0.3.5-alpha Pokémon Varieties**
source. Gameplay and content stay at 0.3.5-alpha; this is a build-only correction.

## What the supplied logs show

The bootstrap found Python 3.14.7 and Go 1.27.1. Isolated server dependencies
installed and passed their pinned-version checks. Content republishing completed
with pack `76fad1c40143e106528d0c53`. The Python suite ran 523 tests and then stopped
with **two errors and ten skips**.

Both errors came from `Tests/test_varieties.py`: the publisher idempotence test
and the unsafe-path/checksum test created a directory symlink to the entire
source asset tree. Their `Path.symlink_to(...)` calls raised **WinError 1314** on
the normal Windows user account. The ten skips were separate platform/privilege
checks, not these two errors. The earlier intentionally injected save failures
ended with `ok`; they were not real failures of the user's database.

This diagnosis does not attribute the failure to MySQL, Python/Go installation,
a missing sprite, the user's OneDrive directory, or a corrupted game account.

## The correction

`publisher_fixture` creates a disposable real directory and copies only the
**3,697 supplied variety-front PNGs**, plus the test's manifest. It does not copy
maps/audio, use symlinks/hard links/junctions, request elevation, or alter Windows
security settings. Copies also prevent corruption tests from writing through
to the shipped artwork. The real publisher and its path, checksum, PNG-header,
dimension and full-Kanto/Johto checks are not weakened or replaced with mocks.

Both original tests remain active. Additional regressions deny both link APIs
while running those checks, confirm byte isolation and cleanup, and reject a
missing copied sprite. Negative cases assert the specific expected error.
The build still stops for a genuine test or asset-validation failure.

The BAT, Python driver, bootstrap version marker and download user-agent report
**1.3.4**. The BAT's outdated gameplay label is corrected to **0.3.5-alpha**.
Tool/dependency pins and prerequisite selection behavior are unchanged.

## Apply the small repair to the existing source

Back up the source folder first and close any running build. Extract the repair
ZIP and follow its included `README_REPAIR.md`. The repair changes only its
listed build/test/documentation files and source checksum manifest. It does not
replace `Client/config.ini`, `Server/config.ini`, `.build/venv`, certificates,
accounts, saves, assets, or an existing `dist` deployment.

After applying it, run the existing **`BUILD_ALL.bat`** normally. The first banner
must report **1.3.4** and gameplay **0.3.5-alpha**. No administrator session,
Developer Mode, new database, dependency downgrade or test-skipping option is
needed. A build creates its own new staging/output directory and reuses a
compatible build environment and verified tool cache.

## Use the four complete source ZIPs instead

Extract **all four WindowsBuildFix parts** into the same new destination and
merge their identically named project folders. Run the `BUILD_ALL.bat` in that
completed folder. They are normal ZIP archives, not binary split volumes; do not
concatenate them. Do not mix partial files from different releases. The full
source already includes this repair, so the small repair is an alternative.

Build and deploy matching Client/Server outputs while preserving your working
configurations, database, certificates/private keys and connection settings.
No account reset or MySQL setup rerun is required for this correction.

## Gameplay and asset preservation

The world pack stays **`76fad1c40143e106528d0c53`**. This release changes no client
JavaScript/CSS, live server gameplay module, species/encounter/variety data,
regular or variety PNG, follower effect, mirrored battle sprite, audio clip,
regional Cut rule, personal tree flag, network protocol or dependency pin.

See `WINDOWS_BUILD_FIX_1.3.4_TEST_REPORT.md` for executed checks and platform limits.

## Platform reference

Python documents that Windows symlink creation without Developer Mode requires
appropriate privilege/elevation, and raises OSError otherwise. Microsoft
likewise documents the unprivileged-create flag's Developer Mode condition.
Those references explain the error; enabling those settings is **not** this fix.

- https://docs.python.org/3.14/library/os.html#os.symlink
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createsymboliclinkw
