# Pokémon NXT MMO · Learnsets and Move Reminder

Gameplay version **0.3.1-alpha**.

## Check the actual next move

Click a Pokémon in your party, or choose **Inspect** in **Party & Pokémon storage**. **Level-up moves** shows the learnset for that Pokémon's current form, each move's level, and whether it is known, awaiting a choice, available through the Move Reminder, or upcoming. The next new move appears above the table. Evolutions and native regional variants can have different learnsets.

Cyndaquil's bundled learnset is:

| Level | Move |
| --- | --- |
| 1 | Tackle |
| 1 | Leer |
| 6 | Smokescreen |
| 12 | Ember |
| 19 | Quick Attack |
| 27 | Flame Wheel |
| 36 | Swift |
| 46 | Flamethrower |

A level-10 Cyndaquil without Ember is therefore expected: it learns Ember at **level 12**, not level 10. Its inspect screen displays **Next move: Ember at Lv. 12** when Ember is not already known or awaiting a choice. These levels come from this game's included native content; guides for a different Pokémon release can list different levels.

## Learn a new move

Level-up choices remain at the top of the inspect screen. If a slot is empty, choose **Learn**. With four moves, choose the move to forget, or **Do not learn this move** to keep the existing set. Additional queued choices follow in order. Resolve these choices before opening the Move Reminder.

## Recover a missed or forgotten move

1. Inspect your Pokémon and choose **Open Move Reminder** under its level-up table. No visit to a special NPC is required.
2. Choose one of the available moves. Only level-up moves eligible for its current form and current level appear, and moves it already knows are excluded.
3. Choose the empty slot, or choose an existing move to replace.
4. For a replacement, review the named old and new moves and choose **Confirm: remember**. **Keep** or **Back to Pokémon** leaves the existing move set unchanged.

The server confirms the change and refreshes the Pokémon. No move set is reset automatically during the upgrade or when opening the reminder. This feature can recover an eligible move missed in an earlier build. It does not teach a future move early: a level-10 Cyndaquil cannot use it to learn Ember. It also does not promise access to every move from a previous evolution or another native variant.

Move changes are unavailable during battles, trades, invitations, or a disconnected session. A changed Pokémon state returns the reminder to move selection, so review the current choices again before replacing a move.

## Upgrade without losing your trainer

Build the supplied source with **BUILD_ALL.bat** and use its matching Client and Server output together. Before changing the deployed server, stop it cleanly and back up the existing database and deployment configuration. Keep your existing server `config.ini`, database, certificates and other private files, and your client's working connection settings. Do not overwrite these with the clean release templates or rerun MySQL setup simply to upgrade.

Point the upgraded server at the same database and log in with the same account credentials. Existing Pokémon identities, levels, chosen moves and account progress are preserved. Inspect the Pokémon and use the Move Reminder deliberately if an eligible move was missed. Do not create a replacement account or reset your save to obtain this fix.

## Existing Sigma move identities

The upgrade also corrects seven native Sigma moves whose numeric IDs previously displayed a different FireRed move name. A one-time server migration changes an old ID only when the Pokémon's own already-earned native Sigma list proves the identity. Its slot and spent PP are preserved, with PP capped only if the corrected move has a lower maximum. Queued choices use their recorded source species. Shared FireRed Pokémon are unchanged, and ambiguous inherited or off-profile moves are left intact. The migration is saved before login completes and is not reapplied on later logins.
