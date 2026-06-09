import unittest
import numpy as np
from unittest.mock import patch, MagicMock
from core.audio_listener import AudioListener

class TestAudioListenerNoiseGate(unittest.TestCase):
    @patch("vosk.Model")
    @patch("vosk.KaldiRecognizer")
    @patch("core.audio_listener.WhisperModel")
    def setUp(self, mock_whisper, mock_kaldi, mock_vosk):
        self.config = {
            "wake_word": "viernes",
            "language": "es-ES",
            "max_recording_duration": 10,
            "silence_threshold": 800,
            "noise_gate_threshold": 400
        }
        self.listener = AudioListener(config=self.config)

    def test_apply_noise_gate_silent(self):
        # Generate quiet audio: values between -100 and 100
        # Energy (RMS) will be low, below the threshold of 400
        quiet_pcm = np.random.randint(-100, 100, 16000, dtype=np.int16).tobytes()
        processed = self.listener._apply_noise_gate(quiet_pcm)
        
        # Should be replaced with complete silence (zeros)
        self.assertEqual(len(processed), len(quiet_pcm))
        self.assertEqual(processed, b"\x00" * len(quiet_pcm))

    def test_apply_noise_gate_loud(self):
        # Generate loud audio: values around 10000
        # Energy (RMS) will be high, above the threshold of 400
        loud_pcm = np.random.randint(9000, 11000, 16000, dtype=np.int16).tobytes()
        processed = self.listener._apply_noise_gate(loud_pcm)
        
        # Should return the original data untouched
        self.assertEqual(processed, loud_pcm)

    def test_apply_noise_gate_disabled(self):
        # Disable noise gate by setting threshold to 0
        self.listener.noise_gate_threshold = 0
        quiet_pcm = np.random.randint(-100, 100, 16000, dtype=np.int16).tobytes()
        processed = self.listener._apply_noise_gate(quiet_pcm)
        
        # Should return original data untouched
        self.assertEqual(processed, quiet_pcm)

    def test_apply_noise_gate_empty_data(self):
        # Empty data should return empty data
        self.assertEqual(self.listener._apply_noise_gate(b""), b"")

if __name__ == "__main__":
    unittest.main()
