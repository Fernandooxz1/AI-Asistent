import unittest
from unittest.mock import patch, MagicMock, call
import subprocess

from core.intent_parser import IntentParser
from core.utils import get_pc_volume, set_pc_volume

class TestPhoneticSanitizationAndVolume(unittest.TestCase):
    
    # ── PHONETIC SANITIZATION & FUZZY MATCHES TESTS ──
    @patch("ollama.chat")
    def test_phonetic_sanitization_and_fuzzy_matching(self, mock_chat):
        # Configure IntentParser with phonetic mapping and keyboard macros
        config = {
            "model_name": "dummy_model",
            "intents": ["automatizacion_teclado"],
            "phonetics": {
                "abrirr": "abrir",
                "musika": "musica"
            },
            "keyboard_macros": {
                "abrir musica": [{"type": "ydotool", "args": ["key", "dummy"]}]
            }
        }
        
        parser = IntentParser(config=config)
        
        # Scenario 1: Input has "abrirr musika", which should be sanitized to "abrir musica"
        # and then match the macro "abrir musica" exactly (substring) resulting in a shortcircuit.
        result = parser.parse("abrirr musika")
        
        # Verify it shortcircuited without calling Ollama
        mock_chat.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["intent"], "automatizacion_teclado")
        self.assertEqual(result[0]["entities"]["macro"], "abrir musica")

        # Scenario 2: Fuzzy matching using RapidFuzz Levenshtein ratio.
        # "abrir musyc" (no phonetics apply, but similar to "abrir musica")
        # should fuzzy match "abrir musica" (similarity is high, above 75%)
        # and shortcircuit.
        result_fuzzy = parser.parse("abrir musyc")
        mock_chat.assert_not_called()
        self.assertEqual(len(result_fuzzy), 1)
        self.assertEqual(result_fuzzy[0]["intent"], "automatizacion_teclado")
        self.assertEqual(result_fuzzy[0]["entities"]["macro"], "abrir musica")

    # ── VOLUME CONTROL TESTS (pactl & amixer) ──
    @patch("subprocess.run")
    def test_get_pc_volume_pactl_success(self, mock_run):
        # Mock pactl success
        mock_pactl_res = MagicMock()
        mock_pactl_res.returncode = 0
        mock_pactl_res.stdout = "Volume: front-left: 32768 /  50% / -18.06 dB, front-right: 32768 /  50% / -18.06 dB"
        mock_run.return_value = mock_pactl_res
        
        volume = get_pc_volume()
        
        self.assertEqual(volume, 50)
        mock_run.assert_called_once_with(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

    @patch("subprocess.run")
    def test_get_pc_volume_amixer_fallback(self, mock_run):
        # Mock pactl failure (status 1) and amixer success
        mock_pactl_res = MagicMock()
        mock_pactl_res.returncode = 1
        
        mock_amixer_res = MagicMock()
        mock_amixer_res.returncode = 0
        mock_amixer_res.stdout = "Simple mixer control 'Master',0\n  Mono: Playback 40 [62%] [-24.00dB] [on]"
        
        mock_run.side_effect = [mock_pactl_res, mock_amixer_res]
        
        volume = get_pc_volume()
        
        self.assertEqual(volume, 62)
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_has_calls([
            call(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False),
            call(["amixer", "get", "Master"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        ])

    @patch("subprocess.run")
    def test_get_pc_volume_all_failed(self, mock_run):
        # Mock both pactl and amixer failures
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res
        
        volume = get_pc_volume()
        
        # Should return fallback 50
        self.assertEqual(volume, 50)

    @patch("subprocess.run")
    def test_set_pc_volume_pactl(self, mock_run):
        set_pc_volume(75)
        
        # Verify it tries pactl first
        mock_run.assert_any_call(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "75%"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @patch("subprocess.run")
    def test_set_pc_volume_amixer_fallback(self, mock_run):
        # Mock pactl raising exception to test ALSA fallback
        mock_run.side_effect = [OSError("pactl not found"), MagicMock()]
        
        set_pc_volume(40)
        
        self.assertEqual(mock_run.call_count, 2)
        mock_run.assert_has_calls([
            call(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "40%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            call(["amixer", "set", "Master", "40%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ])

if __name__ == "__main__":
    unittest.main()
