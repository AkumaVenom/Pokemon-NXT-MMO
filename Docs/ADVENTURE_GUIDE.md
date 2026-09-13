# Pokémon NXT MMO — Adventure Guide

Version **0.3.0-alpha**, continuing the accepted 1.2.3 account, replication, connection and saving baseline.

The Adventure Update adds a persistent journey through both regions: real nearby trainer challenges, sixteen Gym Leaders, badges, journal rewards, Pokémon growth, a discovery-based Pokédex and Pokémon Center services. Kanto uses the extracted FireRed region assets. Johto uses the supplied Ultra Shiny Gold Sigma region assets, including its maps, character graphics and existing sound bank.

## Start your journey

Choose a home region and a starter independently. Choosing Johto does not replace a selected Charmander, and choosing Kanto does not replace a selected Chikorita. Each account keeps its own party, inventory and adventure record.

Explore nearby routes, catch partners, challenge local trainers and visit a Pokémon Center when your team needs care. Open the Adventure Journal to see your next regional Gym challenge and claim completed goals. Continue with the same username and password when logging back in.

| Control | Action |
| --- | --- |
| WASD or arrow keys | Move |
| E | Speak to a nearby character |
| Click a character | Interact, or open another player's challenge/trade menu |
| P | Party and Pokémon storage |
| J | Adventure Journal |
| G | Pokédex; D remains the move-right key |
| B | Bag and supplies |
| M | World atlas |
| Enter | Focus chat |
| Escape | Close an ordinary dialog or leave a text field |
| + / − | Adjust crisp integer world zoom |
| F11 | Toggle fullscreen |
| Sound | Music, effects, cries and accessibility preferences |

## Trainer battles and sixteen Gyms

Approach a trainer and press **E**, or click their character. A supported trainer offers **Challenge trainer**. The server checks your current map, distance and battle availability before starting their ROM-derived team. These are local NPC challenges; the game does not automatically trigger battles using the original games' trainer sight scripts.

Trainer battles cannot be fled or used to catch the opponent's Pokémon. Wild battles retain run and capture choices. Player-versus-player duels remain friendly matches with their existing item and persistent-health protections.

Defeating a trainer records that victory on your account. The first victory awards the trainer's money reward. Rematches become available one minute after a win; they do not repeat the first-victory money award. Gym victories also award the corresponding badge.

Each region has its own badge order. Earn that region's earlier badges before challenging its next Gym Leader. Kanto progress does not grant Johto badges, and Johto progress does not grant Kanto badges.

| Order | Kanto leader | Kanto badge | Johto / Sigma leader | Johto badge |
| --- | --- | --- | --- | --- |
| 1 | Brock | Boulder | Falkner | Zephyr |
| 2 | Misty | Cascade | Bugsy | Hive |
| 3 | Lt. Surge | Thunder | Whitney | Plain |
| 4 | Erika | Rainbow | Morty | Fog |
| 5 | Koga | Soul | Chuck | Storm |
| 6 | Sabrina | Marsh | Jasmine | Mineral |
| 7 | Blaine | Volcano | Pryce | Glacier |
| 8 | Giovanni | Earth | Clair | Rising |

The Journal shows earned badges, each region's next challenge, defeated-trainer count and visited places. Gym challenges use their actual extracted leader NPCs and teams; they are not a generic practice battle substituted for each leader.

## Journal goals and exploration unlocks

Press **J** to review goals for discoveries, catches, visits, trainer victories and regional badges. A completed goal displays **Claim reward**. Rewards are granted once, and the claimed state survives logout and server restart. If a Bag stack is full, make room before trying the claim again.

The default adventure world has these progression rules:

| Unlock | Requirement | Result |
| --- | --- | --- |
| Travel Pass | Two badges in total, from either region | Travel between visited outdoor waypoints and the two starting towns |
| Kanto Surf | Soul Badge from Koga | Enable Surf on Kanto water routes |
| Johto Surf | Fog Badge from Morty | Enable Surf on Johto / Sigma water routes |

The atlas remains readable before obtaining the Travel Pass. Locked destinations cannot be selected for travel. Discover outdoor destinations on foot, then return to them using the atlas after the pass is earned. Interiors remain visible in atlas browsing, but ordinary travel cannot jump directly inside: enter buildings, caves and other interiors through their doors so their return route is established. Surf permission follows the current region; a Kanto Surf license alone does not unlock Johto Surf. Return to land before turning Surf off.

These are authored MMO progression rules. They do not claim to execute the original ROMs' HM, story-item or event scripts.

## Pokémon Centers and Nurse Joy

Healing is a service inside the world. There is no remote **Restore party** menu button.

1. Enter a Pokémon Center and walk up to Nurse Joy's counter.
2. Press **E** or click Nurse Joy.
3. Choose **Yes, please heal my party**.
4. Nurse Joy restores the party's HP, move PP and status, and confirms the completed care.

Stay within interaction range—two tiles of the recognized service NPC. Moving to another map invalidates the previous dialog. Healing cannot run during a battle or trade, and a remote request cannot bypass the proximity check.

Healing also records your Center return point. If your party is defeated, the server restores you there with the correct building exit; before your first Center visit it returns you to your home hub.

Owned healing items remain usable from the Bag in the field. Buying supplies requires a nearby Poké Mart shopkeeper under the default adventure settings.

## Party and PC storage

Press **P** to inspect your party or view the Pokémon stored in your account. Changing the first party member changes your visible follower. Pokémon not in the party remain in PC storage; a full party sends additional captures into storage.

To transfer Pokémon, approach a recognized Pokémon Center PC service or Nurse Joy and select **Open Pokémon storage**. Transfers become available only while you are close enough to the service.

- **Deposit** moves a party member to storage. Keep at least one healthy Pokémon in the party.
- **Withdraw** moves a stored Pokémon into an available party slot. The party limit is six.
- **Inspect** opens stats, moves and available growth choices.
- **Make lead** changes party order without depositing or withdrawing a Pokémon.

The storage tabs and search only show Pokémon owned by the signed-in account. Moving out of PC range disables transfers. Battle and trade activity blocks conflicting party, storage and growth changes.

## Move learning and evolution

Battle experience belongs to the account's actual Pokémon. Inspect a partner when its party card shows **Growth choices ready**.

### New moves

A newly earned level-up move can fill a free move slot. Once all four slots are occupied, the game keeps a saved choice instead of silently replacing a move.

Open the Pokémon's inspection panel and choose the move to forget, or select **Do not learn this move**. Multiple choices are presented in order. Logging out does not discard the remaining choices. A choice applies to that Pokémon's own UID and earned learnset.

### Evolution

An eligible Pokémon displays its available next form in the inspection panel. Choose **Evolve into…** to proceed, or **Not now** to pause that option. A paused evolution has a **Resume evolution** action; resuming makes the explicit evolution choice available again.

Supported runtime rules cover verified level requirements, compatible evolution items and supported trade-triggered evolution offers. The UI displays only eligible options supplied by the server.

**Evolution items** is a general category. It includes the familiar stones and compatible Sigma items such as **Link Cable** and **Fairy Dust**. Their actual extracted names appear in the Bag and evolution panel. A compatible option states which item it consumes; the evolution action is disabled when that item is missing. Buy supplies at a Poké Mart, then inspect the compatible Pokémon to use an evolution item. Evolution items are not battle healing items or capture balls.

The runtime preserves a Pokémon's ownership identity, original trainer, accumulated experience and individual attributes through evolution. A fainted Pokémon remains fainted. Unsupported evolution conditions are not guessed or replaced with arbitrary level requirements; not every condition used by either ROM is implemented.

## Pokédex

Press **G** for the field record. It distinguishes **seen** and **caught** species, with search and filters for all discoveries, catches or sightings still awaiting a catch.

Unseen species are not revealed by name or artwork in this view. Discoveries stay in your account record even if a Pokémon is later traded away. Existing owned Pokémon are added to the record when an older account is first loaded by this release. Your Pokédex is private account progress, separate from another player's record.

## Saving and continuing

Important gameplay changes are committed on the server before their successful completion is reported. This includes rewards, party/storage transfers, healing and growth choices. The existing progressive-saving system also saves movement periodically, on logout and during a normal shutdown.

Fresh server configurations use a **five-second movement save interval**. An existing server keeps its configured interval. **Save now** requests an additional save; it is not required after every action.

Reconnect using the same account to continue. A live battle or trade dialog is not a resumable save file; account progress is the committed server state. An abrupt machine failure can return recent movement to its last completed save.

## Operator upgrade and settings

Build and distribute the updated **Client and Server together**. Their content-pack identities must match. This source update does not require deleting existing accounts or running character-specific repairs.

Before replacing a deployed server, stop it normally and keep a backup of its database, working configuration and TLS files. Reuse the existing database settings and working online-hosting configuration in the newly built server. Keep the certificate private key on the server; players receive the client files and any public trust files required by the already configured hosting setup.

The new adventure fields are added when existing saved accounts load. Current creatures, account ownership and prior progress remain intact. Do not edit player JSON or database rows to grant ordinary progress; use the game services and account flow.

For normal progression, the server's `[world]` configuration uses:

```ini
allow_alpha_atlas = false
allow_alpha_surf = false
save_interval_seconds = 5
```

Restart the server after changing its configuration. Existing deployments may still have the two alpha flags set to `true`. Those explicit exploration settings allow unrestricted atlas travel, field purchasing and/or Surf as before; they override the corresponding progression restrictions. They do not restore remote menu healing or remove Pokémon Center PC checks.

The server owns badge requirements, NPC range, PC range, reward eligibility, item costs, evolution eligibility and save commits. Client buttons communicate availability, but cannot authorize an action on their own.

## Scope of this update

This is a FireRed-style multiplayer adventure layer using the supplied regions and ROM-derived content. It includes sixteen mapped Gym Leader challenges, persistent badges and goals, trainer teams, Pokémon Center care, PC storage, discoveries and supported Pokémon growth.

It is **not a complete interpreter for FireRed or Ultra Shiny Gold Sigma**. Original story cutscenes, every scripted door or puzzle, full NPC event execution, original trainer sight AI, complete abilities and move effects, every evolution condition, breeding and a full Pokémon League campaign are not all implemented. Authored MMO rewards and unlocks are separate from the original story scripts. Region art, sound and extracted identity data do not imply those missing scripts are executing.

Use this release's validation report for the exact automated checks and platform limits. A configured maximum population is not a measured production concurrency guarantee.
