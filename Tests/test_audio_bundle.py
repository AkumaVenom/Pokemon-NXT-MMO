"""Release gates: damaged audio and incomplete bindings cannot be published."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_audio', ROOT / 'Tools/verify_audio.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AudioBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'Client/app/assets/audio'
        self.assets.mkdir(parents=True)
        (self.root / 'Server/data').mkdir(parents=True)
        world = {'maps': {'town': {}}, 'species': {'mon': {}}, 'moves': {'1': {}}}
        (self.root / 'Server/data/world.json').write_text(json.dumps(world))
        # Minimal Ogg framing fixture for header/timing validation. Real bundle
        # decoding is independently checked by the native export's FFmpeg pass.
        identification = b'\x01vorbis' + struct.pack('<IBI', 0, 2, 44100) + bytes(14)
        header = b'OggS\0\x06' + struct.pack('<Q', 44100) + bytes(12) + b'\x01'
        ogg = self.assets / 'song.ogg'
        ogg.write_bytes(header + bytes([len(identification)]) + identification)
        wav = self.assets / 'cry.wav'
        with wave.open(str(wav), 'wb') as stream:
            stream.setparams((1, 2, 10512, 0, 'NONE', 'not compressed'))
            stream.writeframes(struct.pack('<h', 1000) * 10512)
        def clip(path, kind):
            return {'path': 'audio/' + path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'kind': kind, 'duration': 1.0, 'loop': False}
        names = ('title region_default surf battle_wild battle_trainer victory_wild victory_trainer '
                 'victory_caught defeat ui_select ui_error sendout hit faint capture_throw '
                 'capture_success heal level_up low_hp').split()
        self.catalog = {'format': 1, 'sources': {s: {'sha256': 'a' * 64} for s in ('kanto', 'johto')},
                        'clips': {'song': clip(ogg, 'music'), 'cry': clip(wav, 'cry')},
                        'mapMusic': {'town': 'song'}, 'mapModes': {'town': 'song'},
                        'cries': {'mon': 'cry'}, 'reverseCries': {'mon': 'cry'},
                        'cues': {s: {n: 'song' for n in names} for s in ('kanto', 'johto')},
                        'moveSounds': {s: {'1': {'events': [{'clip': 'song', 'delaySeconds': 0}]}}
                                       for s in ('kanto', 'johto')}}

    def verify(self):
        (self.assets / 'catalog.json').write_text(json.dumps(self.catalog))
        return module.verify(self.root)

    def test_valid_bundle_and_digest(self):
        result = self.verify()
        self.assertEqual(result['clipCount'], 2)
        self.assertEqual(result['catalogSha256'], hashlib.sha256((self.assets / 'catalog.json').read_bytes()).hexdigest())

    def test_corrupt_asset_rejected(self):
        (self.assets / 'cry.wav').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.verify()

    def test_missing_map_binding_rejected(self):
        self.catalog['mapMusic'].clear()
        with self.assertRaisesRegex(ValueError, 'map music coverage'):
            self.verify()

    def test_invalid_loop_rejected(self):
        self.catalog['clips']['song'].update(loop=True, loopStart=.8, loopEnd=1.2)
        with self.assertRaisesRegex(ValueError, 'loop bounds'):
            self.verify()

    def test_unsafe_path_rejected(self):
        self.catalog['clips']['song']['path'] = 'audio/../../secret.wav'
        with self.assertRaisesRegex(ValueError, 'unsafe clip path'):
            self.verify()

    def test_missing_cry_rejected(self):
        self.catalog['reverseCries']['mon'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'missing clip reference'):
            self.verify()

    def test_missing_move_bank_rejected(self):
        self.catalog['moveSounds']['johto'].clear()
        with self.assertRaisesRegex(ValueError, 'move sound coverage'):
            self.verify()

    def test_nonfinite_timing_rejected(self):
        self.catalog['moveSounds']['kanto']['1']['events'][0]['delaySeconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'move sound timing'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
