# Autonomous Off-Screen Field Simulation

Version: 0.6.2-alpha

The 2,000 autonomous trainers progress in wild gameplay without requiring any human account to be logged in or present on their map.

## Authoritative clocks

Competitive ranked activity uses `next_action_at`. Field activity uses the independent persistent `nextBackgroundFieldAt` value in each bot personality record. Separating these clocks guarantees that ranked matchmaking cannot starve captures or training.

## Background field actions

On each bounded scheduler pass, due non-materialized trainers can perform level-aware regional travel and then run a genuine wild battle through the shared server Battle engine. Captures, EXP, levels, HP/PP, items, collection/party changes, Pokédex observations and travel metadata persist through `ai_commit_field`.

## Human presence

The scheduler runs when the online-player count is zero. When humans are online, only exact bots in a map's stable materialized cohort are excluded from background processing; they use the visible field loop. Hidden residents on that same map continue autonomous field progression.

## Downtime catch-up

The field due time is persistent. After a server restart, overdue trainers remain eligible for bounded catch-up, capped by `background_field_max_catchup_actions` so a long outage cannot create an unbounded CPU/database spike.
