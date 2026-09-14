"""One catalog for local-console parsing, filtered help and the shipped manual.

No entry in this catalog is exposed through the client packet dispatcher.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class CommandSpec:
    name: str
    usage: str
    summary: str
    category: str
    aliases: tuple = ()
    developer: bool = False
    confirm: bool = False


def spec(name, usage, summary, category, aliases=(), developer=False, confirm=False):
    return CommandSpec(name, usage, summary, category, tuple(aliases), developer, confirm)

COMMANDS = (
    spec('help', '[command|category]', 'Filtered command help and exact syntax.', 'Console', ('commands',)),
    spec('confirm', '<token>', 'Execute one unexpired, unchanged destructive preview.', 'Console'),
    spec('cancel', '[token]', 'Discard a pending destructive preview, or all previews.', 'Console'),
    spec('serverinfo', '', 'Version, pack, uptime, sessions, battles, trades and tick timing.', 'Information', ('status',)),
    spec('who', '[page]', 'Online account IDs, names and maps; 50 per page.', 'Information', ('players',)),
    spec('online', '', 'Current online player count.', 'Information'),
    spec('version', '', 'Gameplay version, content pack and console protocol.', 'Information'),
    spec('uptime', '', 'Elapsed time for this world process.', 'Information'),
    spec('time', '', 'Actual server-local clock and current Crystal encounter period.', 'Information'),
    spec('playerinfo', '<player>', 'Account/character summary without credentials.', 'Players', ('profile', 'stats')),
    spec('where', '<player>', 'Authoritative saved/current location.', 'Players', ('location',)),
    spec('team', '<player>', 'Party slots, stable Pokémon IDs, varieties, levels and HP.', 'Players', ('pokemon',)),
    spec('collection', '<player> [page]', 'Owned Pokémon IDs, including PC storage; 50 per page.', 'Players'),
    spec('pokemoninfo', '<player> <uid|party:N>', 'Detailed owned Pokémon, growth and moves.', 'Players'),
    spec('bag', '<player>', 'Current inventory with stable item IDs.', 'Players'),
    spec('money', '<player>', 'Current currency balance.', 'Players', ('balance',)),
    spec('species', '[query] [page]', 'Find exact species keys and available varieties.', 'Catalog'),
    spec('items', '[query] [page]', 'Find item keys and names.', 'Catalog'),
    spec('moves', '[query] [page]', 'Find move IDs and names.', 'Catalog'),
    spec('maps', '[query] [page]', 'Find playable map IDs, region and safe spawn.', 'Catalog'),
    spec('iteminfo', '<item>', 'Inspect an existing item definition.', 'Catalog'),
    spec('givepokemon', '<player> <species> [level=5] [variety=normal]', 'Grant a new unique Pokémon; overflow remains in PC storage.', 'Pokemon', ('gp',)),
    spec('removepokemon', '<player> <uid|party:N>', 'Remove one owned Pokémon, preserving a viable party.', 'Pokemon', ('rp',), confirm=True),
    spec('heal', '<player>', 'Restore party HP, status and PP.', 'Pokemon'),
    spec('healall', '', 'Atomically heal all online idle parties; busy players are listed/skipped.', 'Pokemon', confirm=True),
    spec('evolve', '<player> <uid|party:N> [target]', 'Apply an eligible authored evolution, consuming its item when required.', 'Pokemon'),
    spec('setlevel', '<player> <uid|party:N> <1..100>', 'Set exact level/threshold XP; preserve identity and chosen moves.', 'Pokemon', confirm=True),
    spec('setexp', '<player> <uid|party:N> <total>', 'Set bounded species-curve total XP and corresponding level.', 'Pokemon', confirm=True),
    spec('learn', '<player> <uid|party:N> <move> <slot:1..4>', 'Teach an earned native move into an explicit slot.', 'Pokemon'),
    spec('forget', '<player> <uid|party:N> <slot:1..4>', 'Forget one chosen move; empty moves use existing Struggle.', 'Pokemon', confirm=True),
    spec('setnature', '<player> <uid|party:N> <nature>', 'Set a supported nature by name or 0..24 ID.', 'Pokemon', confirm=True),
    spec('setivs', '<player> <uid|party:N> <HP ATK DEF SPA SPD SPE>', 'Set six IVs (0..31); recalculate stats without healing damage.', 'Pokemon', confirm=True),
    spec('setvariety', '<player> <uid|party:N> <variety>', 'Set Normal/Ancient/Metallic/Shiny/Mystic/Shadow with verified art.', 'Pokemon', confirm=True),
    spec('setshiny', '<player> <uid|party:N> <true|false>', 'Compatibility form: true=Shiny, false=Normal.', 'Pokemon', confirm=True),
    spec('giveitem', '<player> <item> <1..999>', 'Add to an existing supported inventory stack.', 'Inventory', ('gi',)),
    spec('removeitem', '<player> <item> <1..999>', 'Remove an exact quantity, never silently clamp.', 'Inventory', confirm=True),
    spec('setitem', '<player> <item> <0..999>', 'Set an exact supported item stack.', 'Inventory', confirm=True),
    spec('clearinventory', '<player>', 'Clear bag items only; not Pokémon, badges or money.', 'Inventory', confirm=True),
    spec('givemoney', '<player> <amount>', 'Add currency within the existing 2,000,000,000 cap.', 'Economy'),
    spec('removemoney', '<player> <amount>', 'Remove currency only when the balance covers it.', 'Economy', confirm=True),
    spec('setmoney', '<player> <0..2000000000>', 'Set an exact balance.', 'Economy', confirm=True),
    spec('economy', '', 'Aggregate account and currency totals, including live balances.', 'Economy'),
    spec('teleport', '<player> <map> [x y]', 'Move to a verified walkable tile; never bypass object collision.', 'World', ('tp', 'teleportplayer', 'setlocation')),
    spec('goto', '<player> <destination-player>', 'Move an explicit player to a safe tile near another player.', 'World', ('bring',)),
    spec('unstuck', '<player>', 'Return a character to its safe home spawn; no badge grants.', 'World'),
    spec('tradecancel', '<player>', 'Cancel an active trade/invitation without transferring assets.', 'Trading'),
    spec('tradehistory', '<player> [limit:1..100]', 'Inspect committed trades for an account.', 'Trading'),
    spec('blocktrade', '<player> <true|false>', 'Persistently block/unblock trading; cancel an active offer on block.', 'Trading', confirm=True),
    spec('warn', '<player> <reason>', 'Record a durable warning; notify an online player privately.', 'Moderation'),
    spec('warnings', '<player> [limit:1..100]', 'Read recorded local-console warnings.', 'Moderation'),
    spec('kick', '<player> [reason]', 'Disconnect the selected online session; never a replacement session.', 'Moderation', confirm=True),
    spec('ban', '<player> <permanent|10m|2h|7d> <reason>', 'Persist a timed or permanent login ban and disconnect.', 'Moderation', confirm=True),
    spec('unban', '<player>', 'Remove the account ban without clearing an independent lock.', 'Moderation', confirm=True),
    spec('lockaccount', '<player> <reason>', 'Persist a login lock independent of bans; disconnect if online.', 'Accounts', confirm=True),
    spec('unlockaccount', '<player>', 'Remove only the independent account lock.', 'Accounts', confirm=True),
    spec('resetpassword', '<player>', 'Generate a fresh strong password, show once here, then disconnect.', 'Accounts', confirm=True),
    spec('freeze', '<player>', 'Persist an idle-player gameplay freeze; chat/login remain available.', 'Moderation', confirm=True),
    spec('unfreeze', '<player>', 'Remove the gameplay freeze.', 'Moderation'),
    spec('history', '<player> [limit:1..100]', 'Read the transactional administrative audit for an account.', 'Moderation'),
    spec('connections', '', 'Local-only session IDs, names and directly connected peer addresses.', 'Diagnostics'),
    spec('ipinfo', '<player>', 'Local-only current transport peer; no fabricated historical IP.', 'Diagnostics'),
    spec('save', '[player]', 'Checkpoint one account, or every online account when omitted.', 'Maintenance'),
    spec('saveall', '', 'Checkpoint every online character atomically.', 'Maintenance', ('dbsave',)),
    spec('reloadconfig', '', 'Reload only console policy and registration_enabled; reject other edits.', 'Maintenance', ('reload',), confirm=True),
    spec('gc', '', 'Request Python cyclic garbage collection and report collected objects.', 'Diagnostics'),
    spec('memory', '', 'Report actual process memory where supported and GC counts.', 'Diagnostics'),
    spec('threads', '', 'List current process thread names/IDs.', 'Diagnostics'),
    spec('logs', '[lines:1..100]', 'Read recent local console audit events, with bounded output.', 'Diagnostics'),
    spec('shutdown', '[seconds:0..3600]', 'Schedule a clean save/disconnect/lease-release shutdown.', 'Maintenance', ('stop', 'quit'), confirm=True),
    spec('restart', '[seconds:0..3600]', 'Cleanly stop and ask the supplied launcher to restart (exit 75).', 'Maintenance', confirm=True),
    spec('cancelshutdown', '', 'Cancel a scheduled shutdown/restart before it begins.', 'Maintenance'),
    spec('createaccount', '<username> <Kanto|Johto> <starter>', 'Create an ordinary test account; show generated password once locally.', 'Developer', developer=True, confirm=True),
    spec('clonepokemon', '<player> <uid|party:N>', 'Copy one Pokémon for testing with a new unique ownership ID.', 'Developer', developer=True),
    spec('testbattle', '<player> <species> [level=5] [variety=normal]', 'Start a cloned AI test duel: no real rewards/capture/items or gym wins.', 'Developer', ('battle', 'spawnwild'), developer=True),
    spec('win', '<player>', 'Finish only a console-created test duel as a win.', 'Developer', developer=True),
    spec('lose', '<player>', 'Finish only a console-created test duel as a loss.', 'Developer', developer=True),
    spec('endbattle', '<player>', 'Cancel only a console-created test duel.', 'Developer', developer=True),
    spec('sethp', '<player> <uid|party:N> <hp>', 'Set a test Pokémon HP within its real stat bounds.', 'Developer', developer=True, confirm=True),
    spec('setstatus', '<player> <uid|party:N> <none|burn|poison|toxic|paralysis|sleep>', 'Set only statuses the battle engine implements.', 'Developer', developer=True, confirm=True),
    spec('addmove', '<player> <uid|party:N> <move> <slot:1..4>', 'Teach any existing move into an explicit slot for testing.', 'Developer', developer=True, confirm=True),
    spec('clearmoves', '<player> <uid|party:N>', 'Clear moves for testing; the existing Struggle fallback remains.', 'Developer', developer=True, confirm=True),
)
BY_NAME = {c.name: c for c in COMMANDS}
ALIASES = {a: c.name for c in COMMANDS for a in c.aliases}
assert len(BY_NAME) == len(COMMANDS)
assert not set(BY_NAME).intersection(ALIASES)
assert sum(len(c.aliases) for c in COMMANDS) == len(ALIASES)

def canonical(name):
    name = name.casefold().lstrip('/')
    return ALIASES.get(name, name)
