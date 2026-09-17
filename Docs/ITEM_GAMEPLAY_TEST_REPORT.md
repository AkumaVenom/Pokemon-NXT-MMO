# Item Gameplay Repair — executed validation

Release: **0.6.10-alpha**  
Date: **2026-09-18**  
Matched content pack: **`7acc655cf1328ed72b75b06f`**

## Final results

| Suite | Executed result |
|---|---|
| Complete Python discovery | 722 tests run; 721 passed; 1 platform-only skip; zero failures/errors |
| New item-focused suite | 41 tests passed, including loops over every pickup contract, capture ball, medicine, machine, evolution token and held-item roundtrip; included in the full discovery total |
| Build source-selection suite | 28 tests passed; includes mandatory runtime/item sidecar/publication files |
| Dependency-free client checks | 151 checks passed: 117 registered Node tests plus 34 explicit audio-engine assertions. Node's aggregate also counts the successful audio script wrapper, hence its 118 top-level results |
| Client JavaScript parsing | `node --check` passed for app.js and renderer.js |
| Client launcher Go tests | 12 top-level Go tests passed on Linux; native Windows execution not claimed |
| Chromium DOM acceptance | 15 two-account scenarios passed through the documented local DOM/asset bridge, real aiohttp WebSocket service, and disposable SQLite; no page JavaScript errors |
| Reproduction | Two consecutive ROM-free republishes produced the identical matched server/client pack above |

The full run includes existing battle, autonomous trainer, save/replication, dialogue, account, trade, console, movement, portal, field-pickup and Windows-bootstrap contract tests. Logged injected storage/audit exceptions are expected failure-path tests, not silently ignored production errors. All failing intermediate fixtures/version checks were repaired and the complete final run was re-executed. Counts are test cases, not a claim to have run every possible battle state.

## Item behavior exercised

The new suite verifies Timer Ball's completed-turn formula/cap, every supported capture ball and capture identity, special-ball conditions, trainer rejection, exactly-one consumption, bench/UID medicine targets, no-effect rejection, all PP restoratives/upgrades, all vitamin caps and stat changes, Rare Candy growth, valid Skill Capsule switching plus non-consuming unsupported-destination rejection, all nine ROM-backed machines, all twenty-five evolution token actions, source-safe held item Give/Take/swap/reserve, every type booster against a real published damaging move, species-specific held modifiers, accuracy/evasion, EV/EXP rewards, berry triggering, Focus Band at 1 HP, Smoke Ball, X items/Guard Spec./Dire Hit, Tera adaptation, party-only Ash/Flute, Repels, sales and case/crafting services.

Durable tests use real temporary Store/World instances. They cover ownership, repeated request receipts across relog, mismatched reused request IDs, invalid targets, atomic database failure rollback, retained held/machine state, service proximity, safe Escape Rope use and Repel accepted/blocked steps. Existing movement and portal suites remain active.

## Actual browser fixture actions

- Field Potion uses the selected owner target and commits HP/item together.
- Revive targets a fainted bench partner instead of the lead.
- PP Up changes max PP and Max Ether restores the upgraded cap.
- Flame Ball can be equipped with its source namespace preserved.
- TM48 uses the real Sigma Thunderbolt move, compatibility and explicit replacement.
- Rare Candy commits a level and exposes native evolution choices.
- Timer Ball is visibly a battle capture item, not an inert field-use button.
- Real Timer Ball UI shows 2.1x on turn 12, throws, catches and persists the ball identity.
- Kurt crafting requires the real house and makes an owned usable Fast Ball.
- Pokéblock blending and selected-target feeding persist condition and consume the berry/block, not the case.
- Repel activates from the Bag and publishes its remaining step budget.
- Selling two Nuggets at a real clerk commits exactly two units and the server price.
- Coin Case purchase and prize exchange use the real mart controls and durable wallet.
- Second connected account retains its inventory, Pokémon and progress throughout.
- 1024-pixel layout has no document overflow; both pages have no JavaScript errors.


The fixture runs Chromium 144.0.7559.96. Browser navigation to the native localhost URL was rejected by the environment's managed browser policy (`ERR_BLOCKED_BY_ADMINISTRATOR`). No policy or browser security setting was changed to defeat that restriction. The subsequent documented `NXT_QA_BRIDGE=1` run loads the same source DOM/assets in the existing test fixture and uses a Python aiohttp WebSocket adapter to the real server. This establishes DOM/action/server/database integration, **not native browser WebSocket or Windows Edge launcher transport acceptance**. The read-only observer reads state; actions are performed through visible controls. Initial account inventory/locations and deterministic capture RNG are explicitly seeded test fixtures, not production features.

The screenshots in `ITEM_GAMEPLAY_BAG_QA.png`, `ITEM_GAMEPLAY_BATTLE_QA.png`, and `ITEM_GAMEPLAY_1024_QA.png` were visually inspected. The 1024-pixel check confirms no document-width overflow. This is not a certification of every DPI setting or screen size.

## Boundaries not hidden by test passes

The registry includes clearly labeled NXT crafting/case/Tera and named-item adaptations. Source evidence does not certify full cartridge execution, full later-generation abilities or original minigames. Unsupported Skill Capsule destination ability IDs and transformed-move PP restoration are rejected without item loss. Consult `ITEM_GAMEPLAY.md` and `ITEM_GAMEPLAY_COVERAGE.json` for exact behavior and policies.

Native Windows/Edge gameplay, a packaged Windows launch, live MySQL, Internet/TLS deployment, and production load testing were **not executed for this repair**. The successful temporary SQLite and Linux/bridged-DOM checks are not substituted for those claims. The existing platform-only skip remains a skip, not a pass.

## Deployment acceptance

Stop the live world; back up the configured database and configuration. Merge all four complete source archives, run `BUILD_ALL.bat`, and deploy matching rebuilt server and client while retaining production settings/database/TLS material. Already-collected inventory and pickup flags keep their identities; no reset or recollection is required.

On the target deployment, check an already-owned Timer Ball in a wild battle, one medicine/PP target, a held Give/Take, a compatible TM and an evolution item. Relog and restart the world, then verify the other account's inventory/collection flags remain independent. These are remaining deployment checks, not additional claimed passes.

## Reproduction commands

```text
python Tools/repack_content.py
python -m unittest discover -s Tests
python -m unittest discover -s Tests -p test_item_mechanics.py -v
node --test Tests/check_adventure_ui.mjs Tests/check_audio_app_integration.mjs Tests/check_audio_engine.mjs Tests/check_battle_fx.mjs Tests/check_learnsets.mjs Tests/check_registration.mjs Tests/check_renderer_replication.mjs Tests/check_varieties.mjs
node --check Client/app/app.js
node --check Client/app/renderer.js
```

Client launcher: `go test -v ./...` from `Client/launcher`.
Browser fixture: `NXT_QA_BRIDGE=1 python Tests/check_items_browser.py` in a compatible shell, or set that environment variable before invoking Python on Windows. Playwright and a permitted installed Chromium are optional test dependencies, not required client/runtime dependencies.
