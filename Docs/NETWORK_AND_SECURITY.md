# Network, account and operational security

## Private alpha by default

The shipped server binds `0.0.0.0:7777` with TLS off and explicit private-LAN testing enabled. A direct non-private peer is rejected without TLS. This is a convenience for isolated LAN testing, not secure transport: passwords, chat and gameplay packets can be observed or modified on an untrusted network. Use unique test passwords and a trusted isolated network.

The private-peer check is not a firewall, VPN trust policy or reverse-proxy authentication scheme. An internet-facing proxy connecting from a private address can defeat the intended LAN boundary. **Do not put a plaintext reverse proxy in front of this alpha.** Do not expose the default plaintext listener to the internet and assume the application check is sufficient.

## Direct TLS deployment

For a later private internet test, provide a certificate whose subject alternative name matches the exact hostname (or IP address) clients enter. Use a certificate trusted by the operating system/browser, or an appropriately managed private CA for controlled testing. A mismatched or untrusted certificate must be fixed, not ignored.

```ini
; Server/config.ini
[network]
bind_ip = 0.0.0.0
port = 7777
tls = true
certificate = certificates/server.crt
private_key = certificates/server.key
allow_insecure_lan = false
```

```ini
; Client/config.ini
[server]
host=your-certificate-hostname
port=7777
tls=true
```

Restart both apps. The direct service uses TLS 1.2 or newer. The client does not contain a certificate-validation bypass. Keep the private key server-only. Certificate generation/renewal, public DNS, router forwarding and successful Windows TLS deployment are not automated or tested by this alpha. Public deployment also needs a security review and load test; TLS alone does not make it production-ready.

MySQL belongs on loopback or a protected database network. The game client never needs DB access. `database.ssl_ca` enables CA and identity verification for a remote MySQL connection; use an absolute CA path or a path relative to Server. Do not send remote database credentials over an untrusted plaintext connection.

## Built-in protections and limits

Names and command types are validated server-side. Quantities require integer values; booleans, NaN and Infinity are not valid substitute numbers. Passwords are scrypt-hashed with independent salts. User text is rendered with DOM text nodes, not HTML injection. Login rate limits, chat limits, maximum packet size, pending-login cap, bounded outbound queues and duplicate-login prevention are implemented. The world cap is never more than 1,000. These controls are regression-tested, not a substitute for penetration testing.

Default values: 64 pending logins; six new login connections per source IP per minute; 8,192-byte incoming packets; 128 queued outgoing messages per authenticated connection; five chat messages per ten seconds per account. Slow consumers are disconnected. Accounts behind one NAT share the IP login budget; adjust deliberately for a trusted test rather than removing limits.

The local client shell exposes only app content and non-secret bootstrap settings. It rejects an unexpected Host header, forbids file traversal/directory listing, and applies a restrictive content policy. A local browser profile and helper process are temporary. No client-side password storage, email recovery, MFA, permissioned GM login or account management portal is implemented.

Server extensions execute trusted Python code with server privileges. Never install an unreviewed file from a player. Do not run the service as a privileged system administrator unnecessarily. Protect Server/config.ini, environment variables, TLS keys, logs and backups with operating-system permissions.

## Backups and recovery

Use a dedicated NXT database, not a shared table namespace with the other game. Back up `Server/config.ini`, the matching content pack and the whole MySQL database. A consistent MySQL dump can be made with the installed database tools; for example, from a secured admin terminal:

```text
mysqldump --single-transaction --routines --triggers -u BACKUP_USER -p pokemon_nxt_mmo > pokemon_nxt_mmo_backup.sql
```

Use an account with appropriate backup privileges and let the password prompt handle the password. The command is a template, not a verified backup on your host. Confirm restore procedures in a separate database before relying on backups. Do not restore a live database while the world is running.

Stop the world cleanly before copying the explicit developer SQLite database. An active WAL database is not backed up correctly by blindly copying just its main file. The supplied SQLite mode has no automatic import/export bridge to MySQL.

A forced shutdown can lose unsaved movement and unfinished session progress. Completed owner exchanges are transactional, but this build has no off-machine durability or disaster-recovery guarantee. Protect the MySQL host/storage accordingly and keep a tested backup.

## Before inviting external players

Complete Windows client/server launch and MySQL persistence acceptance, enable and verify direct TLS, restrict database access, secure secrets, review dependencies and server code, test restore, monitor tick/save errors, test disconnect/replay/slow-consumer behavior, and benchmark realistic concurrent load. Check rights to distribute the extracted assets. This alpha is not an authorization to operate a public Pokemon service.
