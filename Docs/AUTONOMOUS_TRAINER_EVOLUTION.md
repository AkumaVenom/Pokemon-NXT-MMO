# Autonomous Trainer Level Evolution

Version: **0.6.3-alpha**

## Purpose

The persistent 2,000-trainer population already owns real Pokémon, gains real EXP, captures from published encounter tables and uses one authoritative party UID list for followers and battles. Version 0.6.3 completes that progression loop by allowing autonomous trainers to accept supported **level-based evolutions** when their real Pokémon reach the authored threshold.

## Authoritative rule source

The AI does not contain a second species/evolution table. It asks the existing `Growth.options()` service for the Pokémon's available authored evolution choices and applies eligible level transitions through `Growth.evolve()`.

That preserves the normal server contracts for:

- species and target validation;
- experience-growth compatibility;
- exact owned Pokémon UID;
- EXP, level, IVs, nature and original trainer;
- HP damage/fainted state across the species stat change;
- existing move slots and PP state;
- pending native move learning;
- evolution history;
- cosmetic variety identity;
- persistent party order and therefore follower identity.

The party is never rebuilt from species names. When the lead Pokémon evolves, the same `party[0]` UID remains the lead, so nearby players see the evolved species automatically and ranked/wild battles use that same individual.

## When bots evolve

A level-evolution check runs after a real autonomous Pokémon gains one or more levels from:

1. genuine autonomous wild battles, including off-screen/zero-player field simulation; or
2. autonomous ranked development, including bot-vs-bot and saved human-vs-bot ranked results.

If the saved level already satisfies a supported level evolution, the authored transition is accepted. Chained overdue level transitions are bounded and cycle-checked.

## Upgrade repair

Older autonomous populations could already contain Pokémon above their evolution level because v0.6.2 gained levels but did not invoke evolution. On first 0.6.3 startup, every existing bot is scanned once. The persistent starter is repaired when eligible. Later captured Pokémon are repaired only when their saved EXP proves they have earned post-capture progress; a legitimately caught lower-stage Pokémon that happens to be above its normal evolution level is not auto-evolved merely by upgrading the server.

This migration does **not** reset trainers, parties, ratings, wins/losses, captures, travel state, rivalries or human accounts. It uses existing state/personality JSON and requires no SQL schema bump.

## Conditions deliberately not faked

This release automates **level** evolutions only. It does not pretend that another condition occurred:

- a stone evolution is not performed merely because the Pokémon is high level;
- a trade evolution is not performed without the durable server trade trigger;
- unsupported ROM evolution methods are not approximated as level evolutions.

Those constraints are intentional. Autonomous trainers should progress through the same authoritative rules as real players, not through bot-only shortcuts.
