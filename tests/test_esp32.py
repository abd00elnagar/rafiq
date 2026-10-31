import unittest
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
import jwt

from esp32_socket import esp32


class TestESP32Simulator(unittest.TestCase):

    def test_constants(self):
        """Verify audio and room configuration constants."""
        self.assertEqual(esp32.SAMPLE_RATE, 48000)
        self.assertEqual(esp32.CHANNELS, 1)
        self.assertEqual(esp32.FRAME_MS, 20)
        self.assertEqual(esp32.SAMPLES_PER_FRAME, 48000 * 20 // 1000)
        self.assertEqual(esp32.ROOM_NAME, "esp32-test-room")
        self.assertEqual(esp32.IDENTITY, "python-esp32-simulator")

    def test_token_generation(self):
        """Verify token generation returns a valid JWT with expected claims."""
        token = esp32.create_token()
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 20)

        # Decode without verification to inspect claims
        decoded = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual(decoded.get("sub"), esp32.IDENTITY)
        self.assertEqual(decoded.get("name"), "ESP32 Simulator")
        video_grants = decoded.get("video", {})
        self.assertTrue(video_grants.get("roomJoin"))
        self.assertEqual(video_grants.get("room"), esp32.ROOM_NAME)

    def test_save_audio_empty(self):
        """Verify saving empty audio returns None without crashing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = esp32.save_audio(np.array([], dtype=np.int16), Path(temp_dir), "empty_test")
            self.assertIsNone(result)

    def test_save_audio_valid(self):
        """Verify saving valid PCM audio writes a correct WAV file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_rate = esp32.SAMPLE_RATE
            duration_s = 0.5
            t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
            sine_wave = (np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)

            filepath = esp32.save_audio(sine_wave, Path(temp_dir), "test_sine")
            self.assertIsNotNone(filepath)
            self.assertTrue(Path(filepath).exists())

            # Read back and verify format
            data, sr = sf.read(str(filepath), dtype="int16")
            self.assertEqual(sr, sample_rate)
            self.assertEqual(len(data), len(sine_wave))
            np.testing.assert_array_equal(data, sine_wave)


if __name__ == "__main__":
    unittest.main()
