# Online hosting and certificate setup · 1.2.2

## Fix the missing TLS files

The reported error occurs because TLS is enabled but the certificate or private key named in `Server/config.ini` does not exist. MySQL already connected successfully. Creating a new database or clearing its lease does not fix this error.

In the built **Server** folder, after installing dependencies, run **`2b - Configure Online Hosting.cmd`**. Enter the **public IP or domain that players will actually use**, without `https://`, a port or a path. Use a domain you control that points to your server, or your actual public IP. `0.0.0.0` is a listening address, not a join address. Keep the game port at `7777` unless you deliberately use another port.

Choose **Generate** to create a certificate and private key for a private world. Save the setup, then start **`3 - Start World Server.cmd`**. The setup prints the exact paths to the files and its player connection kit. The server requires TLS 1.2 or newer; no plaintext fallback is enabled.

**Already have a built Server folder?** Copy `setup_online.py`, `setup_online_gui.py` and `2b - Configure Online Hosting.cmd` from this source's Server folder into your existing built Server folder, and copy `Server/nxt/tls.py` into its `nxt` folder. Then run the new CMD there. These four setup files can create the missing certificates without rebuilding the EXE or rerunning MySQL setup. The full source build also includes the early TLS diagnostics described below.

No certificate or private key is shared between installations in this source release. Setup generates a fresh key locally. A certificate must match your actual join address, which is why a generic pre-generated certificate would not solve player connections.

## Connect players

The console equivalent, after dependencies are installed, is:

```text
.venv\Scripts\python.exe setup_online.py --host YOUR_PUBLIC_IP_OR_DOMAIN --generate
```

Replace the placeholder with your actual address.

Give each player the matching **Client folder** and the **online-client-kit-... folder** created by setup. The kit contains the public certificate and join settings; it contains no private key, database credentials or server configuration.

For a generated private certificate, each player must first run **`Trust Server Certificate.cmd`** from that kit. Check the displayed hostname and SHA-256 fingerprint against the server operator's copy using a trusted channel. The script asks for explicit confirmation before adding that single certificate to the current Windows user's trust store. Close and restart the game after trusting it. The kit explains how to remove that certificate later. This trust is specific to the Windows user running the game; corporate policies may prohibit user-added trust.

In **Client/config.ini**, update only `[server]` to the kit's hostname, port and `tls=true`. Keep your display, launcher and sound settings. Use the same hostname/IP that setup validated, including on the host PC. A certificate for your domain does not cover `127.0.0.1` or a different LAN address.

Generated certificates last one year. Generate a replacement before expiry or when changing the public IP/domain, and distribute the new public kit. Restart the world to use a changed certificate and update each player's trust. A generated private certificate is not automatically trusted by strangers on the internet.

For players who should not install private trust, choose **Import** and supply an existing publicly trusted PEM certificate chain and its matching unencrypted PEM private key. The certificate's subject alternative names must cover the join hostname/IP. Put the server leaf first in the chain, followed by issuer intermediates. Setup validates the key, leaf dates, server purpose and hostname; successful import does not prove a public chain is trusted by every player's browser. Obtain/renew that certificate with your certificate provider and rerun setup after renewal. No public-CA issuance or DNS ownership validation is performed by this tool.

## Make the server reachable

Certificate creation fixes TLS startup; it does not configure your router or internet service.

1. Keep MySQL and the world running on the host. Allow inbound **TCP 7777**, or your chosen game port, through Windows Firewall for the world service on the intended network. The listening process is `Server/.venv/Scripts/python.exe`.
2. If hosting behind a router, forward that same external TCP port to the world PC's LAN IP and game port. Keep that LAN IP reserved. For a non-loopback join address, setup changes a loopback-only listener to `0.0.0.0` for DNS/IPv4 or `::` for an explicit IPv6 address. It preserves other specific listen addresses; ensure the displayed address is reachable on the intended network.
3. Point your domain's DNS at the public address. Do not publish an IPv6 AAAA record unless the world is reachable on that IPv6 address too. For an IPv6 listener, configure the matching IPv6 bind address and firewall rules deliberately.
4. From a device outside the server's LAN, open the kit's `https://HOST:PORT/health` address in Edge after trust setup. Expect JSON server status **without** a certificate warning. Then start the game with the same host, port and TLS setting.

Do not expose MySQL port `3306` to players. If the connection times out despite a local healthy server, check the firewall, forwarding and DNS. An ISP using carrier-grade NAT may require a public address from the ISP or a reachable hosting service. Some home routers cannot loop back through their own public address; use local DNS resolving the **same certificate hostname** to the LAN IP for local players, or test from an outside network. Do not solve a hostname error by turning off certificate validation.

## Preserve a configured world during an upgrade

Build the two source parts into a new output. Stop your old world cleanly. Back up and carry forward its existing **Server/config.ini**, database and server-only certificate files to the new Server folder; install dependencies there. Relative certificate paths remain relative to the new Server folder. A config copied without its referenced files causes exactly the reported failure.

Keep the old deployment until the new one works. Do not overwrite configured MySQL settings with the clean build template or rerun MySQL provisioning just for this update. If the old TLS files never existed, run the new online setup to generate/import them. The setup changes only network settings and keeps an original config backup. Distribute only the matching Client folder and its public connection kit to players.

## Diagnose remaining failures

Run **`Check Configuration.cmd`**. TLS is checked before any database connection. The world console writes the full log path before settings load; the normal location is `Server/logs/world.log`.

| Message or symptom | Corrective action |
|---|---|
| Missing certificate/private key | Run online setup, or restore the exact files named by the error. |
| Key does not match certificate | Import the certificate and key from the same issuance. |
| Certificate expired/not yet valid | Correct the PC clock or replace the certificate. |
| Hostname not covered | Enter a SAN-covered hostname or generate a certificate for the actual join address. |
| Browser trust error | Install the correct private-world public certificate, or repair the publicly trusted chain; restart Edge/game. |
| TLS file access denied | Give the world service account access to its server-only key; keep it private. |
| Timeout from outside LAN | Check public DNS, firewall, port forwarding and ISP reachability. |
| Connection refused | Ensure the world is listening on the intended interface/port and remains running. |
| Database already owned | Stop the other world; retain normal lease expiry and ownership protection. |

Python HTTPS/WSS tests verify certificate checking and encrypted connections. Windows trust installation, router settings, public reachability and live MySQL on your PC must still be checked on that deployment. See `ONLINE_HOSTING_TEST_REPORT.md` for executed checks.

## Implementation references

Certificate loading and minimum TLS version follow the [Python SSLContext API](https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_cert_chain). Certificate creation uses the [cryptography X.509 API](https://cryptography.io/en/latest/x509/tutorial/). The optional player trust script uses Microsoft's documented [X.509 certificate-store API](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509store.add?view=net-10.0).
