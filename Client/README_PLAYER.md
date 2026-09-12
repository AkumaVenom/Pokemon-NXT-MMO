# Pokemon NXT MMO · Player client

Extract this whole Client folder, then edit `config.ini` under `[server]` with the administrator's IP/hostname, port and TLS setting. For a world on this PC use `127.0.0.1:7777`; for a LAN world use that PC's private address. Never put MySQL credentials here.

Run `Pokemon NXT MMO.exe`. Windows x64 and installed Microsoft Edge are required. This is a dedicated Edge app-mode window, not an emulator; Python, Node.js and a ROM are not needed on the client. The world service must be running. Create an account with unique test credentials, choose a home/starter, and enter.

WASD/arrows move, E interacts, Enter focuses world chat, P opens party/collection, B opens bag, M opens the atlas, +/− change crisp world zoom, F11 toggles fullscreen. Click another trainer/nameplate to challenge or trade. A separate account is required for each simultaneous player. General and Trade channels are global. First-party Pokemon follow using extracted two-frame icon animation.

Keep display pixel_scale and ui_scale at zero for automatic 4K-aware presentation. Defaults start maximized. An optional absolute Edge executable path can be set in the launcher section. Restart the client after changing configuration.

This is a private networking/exploration alpha, not the complete original FireRed/Sigma story. Original campaign scripting, audio, evolution, complete abilities/moves and trainer bots are not implemented. The application can use only the matching server content pack. It has no offline mode, auto-updater or password recovery.

The Windows executable is an unsigned, cross-built development binary; native Windows execution still requires acceptance testing. Follow your normal security review policy. The alpha's LAN plaintext mode is not encrypted; use isolated testing and unique passwords, or the administrator's correctly configured direct TLS server. The extracted art remains third-party material; this package does not grant public redistribution rights.
