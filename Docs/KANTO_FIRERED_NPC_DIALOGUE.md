# Kanto / FireRed NPC Dialogue Restoration

Release: **0.6.7-alpha · Kanto FireRed NPC Dialogue Restoration**

## Scope

Pokemon NXT MMO now publishes regular Kanto NPC talk text from the project's reviewed **Pokemon FireRed Rev 1** ROM. The source ROM is accepted only when it matches SHA-256 `729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059` and exact size **16,777,216 bytes**.

`Tools/extract_firered_dialogue.py` performs bounded static script traversal. It never executes ARM/Thumb ROM code, native `special` handlers, or arbitrary event state. It follows only the validated FireRed-family event opcodes already used by the Johto/Sigma extractor, decodes safe literal text, records source script/text/object offsets, and rejects unsupported control bytes rather than guessing.

## Regular-NPC policy

The reviewed FireRed object-event graphics table uses IDs **0–91** for the ordinary person-NPC actor set. The extractor intentionally excludes graphics IDs 92 and above so item balls, Pokémon actors, rocks/trees and other field/special objects cannot surface pickup/result strings as if they were conversational NPC text. Trainer bindings and trainer-type objects are separately excluded so NXT's trainer/Gym preview remains authoritative. Authored story objects are also excluded.

The completed audit covers **1,620 visible FireRed object events**:

- **669** ordinary nontrainer NPC objects are eligible for dialogue extraction.
- **642** have a validated static literal and are published.
- **25** have no readable object-script pointer.
- **2** have a readable script but no validated talk literal.
- **498** non-regular object actors are excluded.
- **413** resolved trainer bindings are excluded.
- **40** additional trainer-type objects are excluded.

Objects without a validated literal keep NXT's existing controlled fallback. No dialogue is invented.

## Runtime behavior

The Kanto sidecar is merged with the preserved Johto/Sigma sidecar into `npcDialogue` format 2. Every published entry retains its region and exact source-object provenance. Runtime rendering substitutes supported owner/party placeholders without executing source scripts.

Trainer and Gym Leader clicks remain unchanged and still show the trainer's Pokémon species and levels before battle. Kanto Pokémon Center nurses and Poké Mart clerks keep their server-authoritative heal/storage/shop actions; the FireRed literal changes presentation only.

This update adds no database schema field, save migration, player reset or bot reset. The accepted v0.6.6 Interior Portal Hotfix and Johto/Sigma dialogue behavior remain intact.

## Reproduction

With the reviewed ROM available outside the release tree:

```text
python Tools/extract_firered_dialogue.py "Pokemon - FireRed Version (USA, Europe) (Rev 1).gba"
python Tools/repack_content.py
python -m unittest Tests.test_kanto_dialogue Tests.test_johto_dialogue -v
```

The normal end-user build does not require either ROM because the validated sidecars are bundled.
