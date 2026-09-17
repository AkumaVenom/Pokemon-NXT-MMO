# Pokemon NXT MMO · Player client

Extract this whole Client folder, then edit `config.ini` under `[server]` with the administrator's IP/hostname, port and TLS setting. For a world on this PC use `127.0.0.1:7777`; for a LAN world use that PC's private address. Never put MySQL credentials here.

Run `Pokemon NXT MMO.exe`. Windows x64 and installed Microsoft Edge are required. This is a dedicated Edge app-mode window, not an emulator; Python, Node.js and a ROM are not needed on the client. The world service must be running. Create an account with unique test credentials, choose a home/starter, and enter.

WASD/arrows move, E interacts, Enter focuses world chat, P opens party/collection, B opens bag, M opens the atlas, +/− change crisp world zoom, F11 toggles fullscreen. Click another trainer/nameplate to challenge or trade. A separate account is required for each simultaneous player. General and Trade channels are global. First-party Pokemon follow using extracted two-frame icon animation.

Keep display pixel_scale and ui_scale at zero for automatic 4K-aware presentation. Defaults start maximized. An optional absolute Edge executable path can be set in the launcher section. Restart the client after changing configuration.

This is a private networking/exploration alpha, not the complete original FireRed/Sigma story. Original campaign scripting, complete abilities/moves and every original trainer script are not implemented; the persistent autonomous trainer population is an MMO-specific server system. The application can use only the matching server content pack. It has no offline mode, auto-updater or password recovery.

The Windows executable is an unsigned, cross-built development binary; native Windows execution still requires acceptance testing. Follow your normal security review policy. The alpha's LAN plaintext mode is not encrypted; use isolated testing and unique passwords, or the administrator's correctly configured direct TLS server. The extracted art remains third-party material; this package does not grant public redistribution rights.


## Route 36 odd tree and SquirtBottle (0.6.5)

The odd tree on Johto Route 36 is now a personal story obstacle. Until you clear it, its exact tile is solid for your character even if another trainer has already cleared theirs. Defeat Whitney in Goldenrod City to earn the Plain Badge; NXT then saves the SquirtBottle in your Key Items. Approach the odd tree, click it (or press E), and choose **Use SquirtBottle**. This starts a Lv. 20 Sudowoodo battle.

Defeat or capture Sudowoodo to save the Route 36 path as permanently clear for that character. Running away or losing does not clear it. The SquirtBottle is not consumed, cannot be bought or traded, and existing characters who already have the Plain Badge receive it automatically after their save is validated. The Adventure Journal shows whether this event is locked, ready or cleared.


## Regional wild Pokémon and Cut (0.3.4)

Wild Pokémon follow the current map's FireRed/Crystal ordinary encounter table, not a universal starter-area list. Crystal locations change with the server's morning/day/night period. Surf encounters are separate from grass/caves; an encounter-free location does not invent a fallback.

Earn the Cascade Badge from Misty to unlock Kanto Cut, or the Hive Badge from Bugsy to unlock Johto Cut. These are independent field licenses, visible in the journal. No selected battle move is automatically replaced. Approach and click a small HM tree: locked Cut is disabled; enabled Cut removes the tree and its collision for your character after saving. Other players still have their own tree. Your cleared paths remain cleared after relogging.


## Using collected items (0.6.10)

Open **Bag** and search for the item. Medicine, training and evolution actions ask for a compatible owned Pokémon; Ether/PP upgrades and TMs also ask for a move slot. A zero-effect target is disabled or rejected without consuming an item. Use **Give to Pokémon…** for held items, and **Take held item** on the Pokémon detail page to return equipment.

For a **Timer Ball**, enter a wild battle, choose **Battle item → Timer Ball**, then **Throw Timer Ball**. The option shows the current turn-based multiplier. Capture balls are not field-use items and cannot capture trainers’ Pokémon. **Flame Ball is different:** in this Sigma source it is a held Fire-type booster, so equip it rather than throw it.

Sell valuables at a Poké Mart clerk. White Apricorn crafting requires Kurt’s Azalea house. Coin Case and Pokéblock Case have dedicated panels. Their services and the Tera Orb battle action are labeled NXT adaptations, not exact replicas of all cartridge minigames. Unsupported Skill Capsule destination abilities are blocked without consumption. See the source documentation for all item-specific behavior.
