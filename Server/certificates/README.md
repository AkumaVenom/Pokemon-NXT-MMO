# Server TLS certificates

Run **2b - Configure Online Hosting.cmd** from Server to generate a private-world
certificate/key pair or import an existing matching PEM certificate chain/key.
Enter the exact public hostname/IP that players will use. Setup records the
actual relative paths in Server/config.ini and exports a public-only player kit.

Generated certificates require explicit trust on each player's Windows account.
No shared sample key is shipped. Keep all private keys on the server. Build
snapshots exclude this directory's certificate files and nested key folders.

See Docs/ONLINE_HOSTING.md for player trust, port forwarding, renewal and
upgrading a configured server. Keep TLS enabled for internet connections.
