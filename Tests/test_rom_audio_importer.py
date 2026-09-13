"""ROM-independent tests of the native audio importer's binary boundaries."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
from extract_rom_audio_metadata import AudioROM, AudioSourceError, decode_dpcm, write_wav
from extract_rom_move_audio import MoveReader


class DeltaPCMTests(unittest.TestCase):
    def test_first_high_nibble_is_padding_then_high_low(self):
        # Absolute=10; padded high nibble F is skipped, then +1,+4,+9,+16.
        self.assertEqual(decode_dpcm(bytes([10, 0xF1, 0x23, 0x40]), 5), bytes([10, 11, 15, 24, 40]))

    def test_delta_wraps_in_signed_eight_bit_domain(self):
        self.assertEqual(decode_dpcm(bytes([127, 0x01, 0x80]), 3), bytes([127, 128, 64]))

    def test_each_64_sample_block_resets_predictor(self):
        packed = bytes([50]) + bytes(32) + bytes([100, 0x02, 0x31])
        self.assertEqual(decode_dpcm(packed, 68), bytes([50] * 64 + [100, 104, 113, 114]))

    def test_truncated_final_block_is_rejected(self):
        with self.assertRaises(AudioSourceError):
            decode_dpcm(bytes([20, 0]), 4)

    def test_negative_count_is_rejected(self):
        with self.assertRaises(AudioSourceError):
            decode_dpcm(b'', -1)

    def test_wav_retains_signed_sample_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cry.wav'
            write_wav(path, bytes([0, 127, 128, 255]), 10512)
            with wave.open(str(path), 'rb') as source:
                self.assertEqual(source.getframerate(), 10512)
                self.assertEqual(source.getnchannels(), 1)
                self.assertEqual(struct.unpack('<4h', source.readframes(4)), (0, 32512, -32768, -256))

    def test_unrecognized_rom_is_rejected_before_offset_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'unknown.gba'
            path.write_bytes(bytes(512))
            with self.assertRaisesRegex(AudioSourceError, 'ROM hash differs'):
                AudioROM(path, 'kanto')


class AnimationSoundTests(unittest.TestCase):
    def reader(self, script):
        rom = AudioROM.__new__(AudioROM)
        rom.data = bytes(16) + script
        rom.source = 'kanto'
        reader = MoveReader.__new__(MoveReader)
        reader.rom = rom
        reader.tasks = {}
        return reader

    def test_loop_sound_keeps_count_spacing_and_signed_pan(self):
        data = bytes([28, 144, 0, 192, 5, 2])
        reader = self.reader(data)
        events, cries = reader.sound(16, 28, data, 10)
        self.assertEqual(cries, [])
        self.assertEqual((events[0]['songId'], events[0]['repeat'], events[0]['intervalFrames'],
                          events[0]['pan'], events[0]['delayFrames']), (144, 2, 5, -64, 10))

    def test_delayed_sound_adds_its_wait_without_changing_script_time(self):
        data = bytes([29, 137, 0, 63, 19])
        reader = self.reader(data)
        events, _ = reader.sound(16, 29, data, 7)
        self.assertEqual(events[0]['delayFrames'], 26)

    def test_invalid_opcode_is_rejected(self):
        reader = self.reader(bytes([255]))
        with self.assertRaises(AudioSourceError):
            reader.command(16)

    def test_truncated_sprite_arguments_are_rejected(self):
        reader = self.reader(bytes([2, 0, 0, 0, 8, 2, 8]))
        with self.assertRaises(AudioSourceError):
            reader.command(16)

    def test_reachable_alternatives_do_not_follow_unconditional_fallthrough(self):
        # Goto SE137, leaving an unreachable SE144 immediately after the goto.
        script = bytes([19]) + struct.pack('<I', 0x08000000 + 25)
        script += bytes([9, 144, 0, 8, 9, 137, 0, 8])
        reader = self.reader(script)
        self.assertEqual(reader.reachable(16)[0], [137])


if __name__ == '__main__':
    unittest.main()
