# Server TLS certificates

Place your server certificate chain and private key here, then set `[network]`
`tls=true`, `certificate=certificates/server.crt`, and
`private_key=certificates/server.key` in Server/config.ini. The certificate must
be trusted by Windows/Edge and match the hostname in Client/config.ini.

Do not put private keys in the client. Do not disable certificate validation.
No sample private key is shipped. See Docs/NETWORK_AND_SECURITY.md.
