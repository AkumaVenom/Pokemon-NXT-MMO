"""Read-only dependency, TLS, content and database-login checks; creates no tables."""
from pathlib import Path
import argparse
import importlib
import sys
from nxt.config import Settings
from nxt.content import Content
from nxt.tls import TLSConfigurationError, load_server_tls

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.ini')
    args = parser.parse_args(argv)
    phase = 'reading configuration'
    try:
        settings = Settings.load(args.config)
        print('Pokemon NXT MMO configuration check\n')
        print('Configuration:', args.config.resolve())
        print('Python:', sys.version.split()[0])
        missing = False
        for name in ('aiohttp', 'pymysql'):
            try:
                module = importlib.import_module(name)
                print(name + ':', getattr(module, '__version__', 'installed'))
            except ImportError:
                print(name + ': MISSING - run 1 - Install Server Dependencies.cmd')
                missing = True
        phase = 'checking TLS certificate and private key'
        tls = load_server_tls(settings)
        if tls is None:
            print('TLS: OFF. Private LAN mode only; internet peers are rejected.')
            print('For online hosting, run 2b - Configure Online Hosting.cmd.')
        else:
            print('TLS: certificate/key pair loaded; minimum protocol TLS 1.2.')
            print('Certificate:', settings.path('network', 'certificate').resolve())
            print('Private key:', settings.path('network', 'private_key').resolve())
            host = settings.config.get('network', 'public_host', fallback='').strip()
            print('Certificate hostname/IP:', host + ' (SAN matches)' if host else 'public_host is not configured; check the exact client hostname/IP against its SAN.')
            print('Players must trust the certificate issuer. Browser trust, public DNS, firewall and router reachability are not tested by this check.')

        if missing:
            return 1

        phase = 'loading world content'
        content = Content(settings.root / 'data/world.json')
        print('Content pack:', content.pack, '| Maps:', len(content.maps), '| Catalog:', len(content.species))
        print('Bind:', settings.bind_ip + ':' + str(settings.port), '| Cap:', settings.max_players)
        print('Database backend:', settings.get('database', 'backend'), '| No credentials displayed')
        if settings.get('database', 'backend') == 'mysql':
            if settings.password() == 'CHANGE_ME_WITH_SETUP':
                print('MySQL: NOT CONFIGURED. Run 2 - Configure MySQL.cmd.')
                return 1
            phase = 'checking MySQL login'
            import pymysql
            ca = str(settings.path('database', 'ssl_ca').resolve()) if settings.get('database', 'ssl_ca') else None
            connection = pymysql.connect(
                ssl_ca=ca, ssl_verify_cert=bool(ca), ssl_verify_identity=bool(ca),
                host=settings.get('database', 'host'), port=settings.int('database', 'port'),
                user=settings.get('database', 'user'), password=settings.password(),
                database=settings.get('database', 'database'), connect_timeout=5,
            )
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    print('MySQL login: OK')
            finally:
                connection.close()
        print('\nLocal configuration checks passed. Start the world server to open the game listener.')
        return 0
    except TLSConfigurationError as error:
        print('CHECK FAILED:', error)
    except Exception as error:
        # Driver/config exceptions can embed passwords; report only safe context.
        code = error.args[0] if error.args and type(error.args[0]) is int else None
        print('CHECK FAILED while ' + phase + ': ' + type(error).__name__ + (f' (error {code})' if code is not None else '') + '.')
        if phase == 'checking MySQL login':
            print('Check MySQL availability and the saved account/database settings. Run 2 - Configure MySQL.cmd if needed.')
        else:
            print('Check the configuration values and extract the complete matching Server package.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
