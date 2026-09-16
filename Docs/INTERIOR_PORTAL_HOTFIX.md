# v0.6.6-alpha Interior Portal Hotfix

## Runtime defects corrected

Two independent portal-state defects were found during native runtime acceptance.

1. **Pokémon Center upstairs loop.** Entering a shared Center correctly created an owner return to the exterior doorway. Returning from an internal upstairs room to that same lower Center created a second return entry, incorrectly treating the upstairs room as a new exterior. The lower exit then consumed the newer entry and sent the character back upstairs.
2. **Goldenrod Department Store elevator placeholder.** The Sigma elevator exit at `johto_34_27`, warp 0, stores raw destination bank/map `0/0`. In the ROM this destination is selected by script. NXT does not execute that script, so treating the raw bytes as a real map incorrectly sent the player to `johto_0_0` (Battle Frontier).

## Corrected contracts

`Server/nxt/portals.py` now keeps at most one valid return context for a shared interior. Internal stairs or side rooms can re-enter the shared room without replacing its exterior return. Saved duplicate contexts from the earlier defect are normalized by retaining the first valid owner return.

`Tools/repair_interiors.py` contains a narrowly reviewed `SCRIPT_DYNAMIC_RETURNS` entry for Goldenrod Department Store's elevator only. The checked-in `Server/data/interior_repairs.json` publishes that exit as `dynamic: true`, `kind: elevator-return`. Entering the lift from 1F–6F or the basement pushes the character's exact source floor and adjacent doorway; leaving the lift consumes that owner context and returns there. No general rule turns other `0/0` records into dynamic returns.

The transition and its return stack are still committed atomically before a map packet is published. No collision arrays, NPC objects, player progression, bot simulation or schema are changed by this hotfix.

## Acceptance coverage

The focused regression suite verifies:

- real Cherrygrove Center exterior entry -> downstairs -> upstairs -> downstairs -> exterior, with the same owner return preserved throughout;
- legacy duplicate shared-room return records collapse to the original valid exterior;
- all seven Goldenrod Department Store elevator source maps (`johto_34_21`–`johto_34_26`, `johto_34_28`) enter `johto_34_27` and return to the exact source tile;
- the elevator path never resolves to `johto_0_0`;
- all original native door, Center, gym, collision, relog and save-failure regressions remain intact.

No database wipe, account reset or save migration command is required.
