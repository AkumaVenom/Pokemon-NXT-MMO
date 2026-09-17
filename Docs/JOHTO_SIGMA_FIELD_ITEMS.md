# Johto / Sigma Field Item Ball Completion

Release: **0.6.9-alpha**  
Reviewed source: **Ultra Shiny Gold Sigma Completo 1.5.0**  
Accepted SHA-256: `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64`

## Scope and extraction contract

The Johto / Sigma maps contain many world objects that use graphics ID **92**, the visible Poké Ball field sprite. Graphics alone are not sufficient evidence that an object is collectible: starter displays, custom encounters, decorations and other scripted actors may use the same sprite.

`Tools/extract_adventure_data.py` therefore performs a bounded, static audit. It follows only the linear sequence of fixed-length event commands from the object's own script pointer. A pickup is accepted only when that path writes the source item ID to `VAR_8000`, writes the quantity to `VAR_8001`, and invokes standard script 1. Calls, gotos, branches, returns and unknown opcodes terminate the candidate path; ROM code is never executed and adjacent script bytes are never searched as a fallback.

The accepted ROM produces the following invariant counts:

- **386** visible Johto / Sigma objects use the Poké Ball field sprite.
- **361** are verified standard field-item pickups.
- **25** are deliberately excluded look-alike/custom objects.
- The verified placements contain **125 distinct pickup item identities** across **153 maps**.
- **38** placements award more than one item; the exact source quantity is preserved, with a maximum single pickup quantity of **16**.

The full placement list, source offsets, item IDs, quantities and 25 exclusions are in `JOHTO_SIGMA_FIELD_ITEM_AUDIT.json`.

## Runtime authority and persistence

Each verified placement is bound to its stable published `(map, NPC object ID)` identity and carries an `itemPickup` ID. When the player interacts with it, the server validates the current map, object identity and proximity before looking up the immutable award record. The client cannot choose the item or quantity.

The inventory increment and collected-marker append happen on a detached state snapshot and are persisted in one normal character commit. If the database save fails, the live character state does not change and the ball remains collectible. If the award would exceed the 999-item stack limit, collection is rejected without consuming the ball. Replays of an already collected ID are rejected server-side.

`adventure.itemPickups` is owner-private state. The client renderer receives only its own list and hides matching field objects locally. Another account on the same map keeps its own Poké Ball visible and may collect it independently. Legacy saves migrate additively by receiving an empty `itemPickups` list; no SQL schema migration or content reset is required.

## Item catalog policy

The extraction publishes the exact Sigma item identity needed by every verified placement. Existing NXT entries keep their established operational mechanics and balancing—for example Poké/Great/Ultra Ball capture multipliers, Potion/Super Potion healing and existing evolution-item prices. This prevents a content extraction from silently changing already accepted MMO behavior.

Newly recovered Sigma-only items are marked `buyable: false`; finding them on the map does not inject them into every Poké Mart. Ordinary non-important items remain tradable after acquisition. ROM-important/key items are non-tradable. TM/HM effects, held-item battle effects, status/PP consumables and other secondary behavior not already implemented by NXT are **not fabricated** merely because the item can now be collected; acquisition, identity, quantity, ownership and persistence are implemented independently of those future mechanics.

## Build and development-input boundary

The normal source pack ships the extracted `Server/data/adventure_rom.json`, rebuilt `Server/data/world.json` and matching client map/content JSON. A player or server operator does **not** need the ROM. Developers rerunning the extraction must provide the exact hash-approved Sigma ROM (and the separately approved FireRed ROM for the complete adventure extractor); a hash mismatch is rejected.
