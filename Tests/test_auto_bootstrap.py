"""Automatic build packaging/security contracts; no downloads or system changes."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nxt_auto_build_test', ROOT/'Build/build.py')
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class BootstrapContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT/'Build/toolchains.json').read_text())
        self.lib = (ROOT/'Build/bootstrap_lib.ps1').read_text()
        self.main = (ROOT/'Build/bootstrap_windows.ps1').read_text()
        self.bat = (ROOT/'BUILD_ALL.bat').read_text()

    def test_manifest_uses_versioned_official_https_downloads(self):
        self.assertEqual(self.manifest['schema'], 1)
        for name, host in [('python','www.python.org'),('go','dl.google.com')]:
            tool=self.manifest[name]
            u=urlparse(tool['url'])
            self.assertEqual(u.scheme,'https')
            self.assertEqual(u.hostname,host)
            self.assertEqual(Path(u.path).name,tool['filename'])
            self.assertRegex(tool['sha256'],r'^[0-9a-f]{64}$')
            self.assertRegex(tool['version'],r'^\d+\.\d+\.\d+$')
            self.assertIn(tool['version'],tool['filename'])
            self.assertFalse(u.username or u.password or u.query or u.fragment)

    def test_bootstrap_does_not_assign_readonly_powershell_variables(self):
        # This check runs even on Linux, where native PowerShell tests are skipped.
        # PowerShell names are case-insensitive: a local $home still writes HOME.
        readonly_assignment = re.compile(
            r'\$(?:local:|script:|global:|private:)?(?:home|host|pid|psversiontable|'
            r'pshome|shellid|executioncontext|true|false|null)\s*(?:[+*/%-]?=(?!=)|\+\+|--)',
            re.IGNORECASE,
        )
        for path in sorted((ROOT/'Build').glob('*.ps1')):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if not line.lstrip().startswith('#'):
                    self.assertIsNone(readonly_assignment.search(line),
                                      f'{path.name}:{number}: assignment to a PowerShell automatic variable')

    def test_build_version_matches_entry_point_and_manifest(self):
        self.assertEqual(self.manifest['bootstrap_version'], builder.BUILD_TOOL_VERSION)
        self.assertIn('SOURCE BUILD '+builder.BUILD_TOOL_VERSION, self.bat)
        self.assertIn('Pokemon-NXT-MMO-Build/'+builder.BUILD_TOOL_VERSION, self.lib)

    def test_python_full_installer_keeps_password_gui_and_pip(self):
        self.assertTrue(self.manifest['python']['filename'].endswith('-amd64.exe'))
        for flag in ['InstallAllUsers=0','Include_pip=1','Include_tcltk=1','Include_launcher=0','PrependPath=0','AppendPath=0','AssociateFiles=0']:
            self.assertIn("'"+flag+"'",self.lib)
        self.assertIn('Get-AuthenticodeSignature',self.lib)
        self.assertIn('Python Software Foundation',self.lib)
        self.assertIn("$signature.Status -ne 'Valid'",self.lib)

    def test_bat_uses_builtin_powershell_not_preinstalled_python_or_go(self):
        self.assertIn('bootstrap_windows.ps1',self.bat)
        self.assertIn('System32\\WindowsPowerShell\\v1.0\\powershell.exe',self.bat)
        self.assertIn('Sysnative',self.bat)
        self.assertIn('DisableDelayedExpansion',self.bat)
        self.assertNotIn(':missing_python',self.bat)
        self.assertNotIn('py -3',self.bat)
        self.assertNotIn('goto missing_python',self.bat)
        self.assertIn('NXT_BUILD_NO_PAUSE',self.bat)
        self.assertIn('exit /b %BUILD_RESULT%',self.bat)

    def test_bat_and_server_cmd_have_windows_line_endings(self):
        for path in [ROOT/'BUILD_ALL.bat',ROOT/'Server/1 - Install Server Dependencies.cmd']:
            data=path.read_bytes()
            self.assertIn(b'\r\n',data)
            self.assertNotIn(b'\n',data.replace(b'\r\n',b''))

    def test_bootstrap_files_are_retained_in_every_complete_source_release(self):
        for name in ['Build/bootstrap_windows.ps1','Build/bootstrap_lib.ps1','Build/toolchains.json','Tests/check_bootstrap_windows.ps1','Tests/test_auto_bootstrap.py']:
            self.assertTrue(builder.is_source_file(PurePosixPath(name)),name)
        for name in ['Build/bootstrap_windows.ps1','Build/bootstrap_lib.ps1','Build/toolchains.json']:
            self.assertIn(name,builder.REQUIRED_SOURCE)

    def test_downloads_fail_closed_on_hash_mismatch_and_preserve_no_partial(self):
        self.assertIn('Test-NxtHash $partial $Tool.sha256',self.lib)
        self.assertIn('SHA-256 mismatch',self.lib)
        self.assertIn('Remove-Item -LiteralPath $partial',self.lib)
        self.assertIn('$attempt -le 3',self.lib)
        self.assertIn('$request.AllowAutoRedirect = $false',self.lib)
        self.assertIn('Assert-NxtUrl $next.AbsoluteUri',self.lib)

    def test_no_global_policy_firewall_path_or_database_mutation(self):
        scripts=self.main+'\n'+self.lib
        for prohibited in ['Set-ExecutionPolicy','Set-MpPreference','netsh ','CREATE DATABASE','CREATE USER','ALTER USER','-Verb RunAs','Invoke-Expression','iex ','setx ']:
            self.assertNotIn(prohibited,scripts)
        self.assertIn("[Environment]::SetEnvironmentVariable($key,$null,'Process')",self.main)
        self.assertIn("$env:NXT_GO = $go.Path",self.main)
        self.assertIn("$env:NXT_PYTHON = $python.Path",self.main)

    def test_offline_mode_and_build_exit_codes_propagate(self):
        self.assertIn("$offline = $buildArguments -contains '--no-install'",self.main)
        self.assertIn('-Offline:$offline',self.main)
        self.assertIn('$resultCode = $buildResult.ExitCode',self.main)
        self.assertIn('exit $resultCode',self.main)

    def test_server_setup_finds_the_managed_python_without_path(self):
        setup=(ROOT/'Server/1 - Install Server Dependencies.cmd').read_text()
        self.assertIn('%LOCALAPPDATA%\\Programs\\PokemonNXT\\Python313\\python.exe',setup)
        self.assertIn('if defined NXT_PYTHON goto custompython',setup)
        self.assertIn('"%NXT_PYTHON%" -m venv .venv',setup)
        self.assertNotIn('mysql.exe',setup)

    def test_toolchain_downloads_are_not_accidentally_packaged(self):
        for name in ['.build/bootstrap.json','.build/downloads/python-3.13.15-amd64.exe','.build/venv.previous-123/pyvenv.cfg','Build/python.exe','Build/go.zip']:
            self.assertFalse(builder.is_source_file(PurePosixPath(name)),name)

    def test_snapshot_includes_real_bootstrap_bytes(self):
        # Exercise the production source copier, not just extension assertions.
        with tempfile.TemporaryDirectory(prefix='NXT bootstrap snapshot ') as tmp:
            dest=Path(tmp)/'stage'; dest.mkdir()
            builder.snapshot_source(ROOT,dest)
            for name in ['BUILD_ALL.bat','Build/bootstrap_windows.ps1','Build/bootstrap_lib.ps1','Build/toolchains.json']:
                self.assertEqual((ROOT/name).read_bytes(),(dest/name).read_bytes())
            self.assertIn('CHANGE_ME_WITH_SETUP',(dest/'Server/config.ini').read_text())
            self.assertNotIn('bootstrap.json',[str(p.relative_to(dest)) for p in dest.iterdir()])

class VenvProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='NXT probe ')
        self.root=Path(self.temp.name)
        self.exe=self.root/'python.exe'; self.exe.write_bytes(b'not-executed')
    def tearDown(self): self.temp.cleanup()
    def result(self, version=None, bits=64, code=0):
        return subprocess.CompletedProcess([],code,json.dumps({'version':list(sys.version_info[:2]) if version is None else version,'bits':bits}), '')
    def test_healthy_matching_venv(self):
        with patch.object(builder.subprocess,'run',return_value=self.result()):
            self.assertTrue(builder.build_venv_healthy(self.exe,self.root))
    def test_missing_executable(self):
        self.exe.unlink(); self.assertFalse(builder.build_venv_healthy(self.exe,self.root))
    def test_wrong_architecture(self):
        with patch.object(builder.subprocess,'run',return_value=self.result(bits=32)):
            self.assertFalse(builder.build_venv_healthy(self.exe,self.root))
    def test_wrong_minor_version(self):
        with patch.object(builder.subprocess,'run',return_value=self.result(version=[2,7])):
            self.assertFalse(builder.build_venv_healthy(self.exe,self.root))
    def test_failed_process(self):
        with patch.object(builder.subprocess,'run',return_value=self.result(code=1)):
            self.assertFalse(builder.build_venv_healthy(self.exe,self.root))
    def test_invalid_response(self):
        with patch.object(builder.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'not json','')):
            self.assertFalse(builder.build_venv_healthy(self.exe,self.root))
    def test_timeout_and_missing_runtime(self):
        for exc in [OSError('missing base'),subprocess.TimeoutExpired('python',30)]:
            with self.subTest(exc=exc), patch.object(builder.subprocess,'run',side_effect=exc):
                self.assertFalse(builder.build_venv_healthy(self.exe,self.root))

class VenvRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='NXT recovery ')
        self.root=Path(self.temp.name); self.cache=self.root/'.build'; self.cache.mkdir()
        self.env=self.cache/'venv'; self.env.mkdir()
        (self.env/'keep.txt').write_text('old environment preserved')
        self.log=Mock()
        self.args=argparse.Namespace(existing_environment=False,no_install=False)
    def tearDown(self): self.temp.cleanup()
    def test_broken_build_environment_is_preserved_and_recreated(self):
        def fake_run(cmd,**kwargs):
            if '-m' in cmd and 'venv' in cmd:
                Path(cmd[-1]).mkdir()
            return ''
        with patch.object(builder,'build_venv_healthy',side_effect=[False,True]),patch.object(builder,'run',side_effect=fake_run):
            builder.ensure_python(self.args,self.root,self.cache,self.log)
        backups=list(self.cache.glob('venv.previous-*'))
        self.assertEqual(len(backups),1)
        self.assertEqual((backups[0]/'keep.txt').read_text(),'old environment preserved')
        self.assertTrue(self.env.is_dir())
        self.assertFalse((self.root/'Server').exists())
    def test_offline_broken_venv_is_not_modified(self):
        self.args.no_install=True
        with patch.object(builder,'build_venv_healthy',return_value=False), patch.object(builder,'run') as run:
            with self.assertRaises(builder.BuildError): builder.ensure_python(self.args,self.root,self.cache,self.log)
            run.assert_not_called()
        self.assertTrue((self.env/'keep.txt').exists())
        self.assertEqual(list(self.cache.glob('venv.previous-*')),[])
    def test_online_pip_uses_official_index_and_exact_requirements(self):
        with patch.object(builder,'build_venv_healthy',return_value=True),patch.object(builder,'run',return_value='') as run:
            builder.ensure_python(self.args,self.root,self.cache,self.log)
        command=run.call_args_list[0].args[0]
        for value in ['--isolated','https://pypi.org/simple','--only-binary=:all:',self.root/'Server/requirements.txt']:
            self.assertIn(value,command)
    def test_failed_environment_creation_stops_before_pip(self):
        with patch.object(builder,'build_venv_healthy',return_value=False),patch.object(builder,'run') as run:
            with self.assertRaises(builder.BuildError): builder.ensure_python(self.args,self.root,self.cache,self.log)
            self.assertEqual(run.call_count,1)

@unittest.skipUnless(sys.platform=='win32','Windows PowerShell execution requires Windows; not simulated as passed')
class NativePowerShellTests(unittest.TestCase):
    def test_bootstrap_helper_contracts_on_windows(self):
        powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        result=subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Tests/check_bootstrap_windows.ps1')],capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        self.assertIn('BOOTSTRAP HELPER TESTS PASSED',result.stdout)

if __name__=='__main__': unittest.main()
