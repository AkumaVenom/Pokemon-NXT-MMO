# Autonomous Trainer Party Identity Fix — 0.5.1-alpha

## Defect

0.5.0 correctly rendered the overworld follower from `state.party[0]`, but a human ranked challenge rebuilt the bot roster by scanning `state.creatures`. After automatic party optimisation those orders can differ, so the first battle Pokémon could be a different owned Pokémon than the follower. Older 0.4.0 seeding also appended `bot_id % 3` synthetic Pokémon that were never captured.

## Correction

`AutonomousTrainers._party_members()` is now the only party materialisation path. It resolves the exact ordered UIDs in `state.party`, verifies every UID is uniquely owned, and is used for overworld follower identity, team strength, development, autonomous wild battles and human ranked challenges. Ranked duels clone those exact owned records and only heal the temporary duel copies.

Fresh bots receive only the same single starter produced by `World.initial()`. Existing bots receive a one-time `partyIdentityVersion` migration. The old deterministic bootstrap extras are identifiable because 0.4.0/0.5.0 inserted them directly after the starter using a fixed species formula, while all genuine captures were appended later. The migration removes only recognized legacy bootstrap entries and preserves genuine captured Pokémon and remaining party order.

## Required runtime acceptance

On an upgraded persistent database, select a visible bot whose follower can be identified, challenge that exact bot, and confirm the first opponent Pokémon is the same species/level. Allow the bot to capture and optimise its party, then repeat. Restart the server and repeat again. Also verify newly created/fresh-database bots begin with one starter and acquire later team members only through recorded wild activity.
