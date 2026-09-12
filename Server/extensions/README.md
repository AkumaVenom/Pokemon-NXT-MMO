# Trusted world extensions

Only the server administrator may install Python files here. Never accept extension
files from a client or an in-game upload. Files starting with `_` are ignored.

An enabled `.py` file may expose `register(world)` and subscribe through
`world.hook(event, callback)`. Current events: `login`, `logout`, `move`,
`battle_end`, `trade_complete`. Hooks execute inside the authoritative world
operation. Keep them short, non-blocking and deterministic. Do not call blocking
I/O or acquire `world.lock` recursively from a hook.

This is an extension seam, not a sandbox. A future trainer-bot controller should
submit validated server intents through a queue, use the same collision/battle/
ownership services, and give its persistent state an explicit migration. Do not
have a bot fabricate client HP, trade snapshots or account credentials.

The example is disabled by its underscore prefix. Rename it only after review.
