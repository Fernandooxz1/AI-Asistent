import unittest
from unittest.mock import patch, MagicMock
import subprocess
import json

from actions.window_control_action import WindowControlActionModule, get_similarity, normalize_text, clean_query_words


class TestWindowControlActionModule(unittest.TestCase):

    def test_clean_query_words(self):
        self.assertEqual(clean_query_words("el video de youtube"), "youtube")
        self.assertEqual(clean_query_words("la ventana de brave"), "brave")
        self.assertEqual(clean_query_words("el stream de davo"), "davo")
        self.assertEqual(clean_query_words("notebookLM"), "notebooklm")
        self.assertEqual(clean_query_words(""), "")
        self.assertEqual(clean_query_words(None), "")

    def test_normalize_text(self):
        self.assertEqual(normalize_text("Café"), "cafe")
        self.assertEqual(normalize_text(" Davo - Kick "), "davo - kick")
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")

    def test_get_similarity(self):
        # Substring exact matches
        self.assertEqual(get_similarity("davo", "Davo Xeneize - Kick - Brave"), 100.0)
        self.assertEqual(get_similarity("brave", "brave-browser"), 100.0)
        
        # Fuzzy match
        sim = get_similarity("davoo", "Davo Xeneize - Kick - Brave")
        self.assertTrue(sim >= 75.0)

        # No match
        self.assertTrue(get_similarity("steam", "Alacritty") < 50.0)

    def test_validate_entities_success(self):
        module = WindowControlActionModule()
        self.assertTrue(module.validate_entities({"ventana_query": "brave"}))

    def test_validate_entities_failure(self):
        module = WindowControlActionModule()
        self.assertFalse(module.validate_entities({}))
        self.assertFalse(module.validate_entities({"ventana_query": ""}))
        self.assertFalse(module.validate_entities({"ventana_query": 123}))

    @patch("subprocess.run")
    def test_execute_success(self, mock_run):
        # Mock hyprctl clients -j response
        clients_json = json.dumps([
            {
                "address": "0x565030d720c0",
                "class": "Alacritty",
                "title": "fernandooxz1@PCLinux:~"
            },
            {
                "address": "0x565032688c50",
                "class": "brave-youtube.com__-Default",
                "title": "PSG CAMPEON DE CHAMPIONS - YouTube"
            }
        ])
        
        # Configure subprocess mock
        mock_response_clients = MagicMock()
        mock_response_clients.return_value.returncode = 0
        mock_response_clients.return_value.stdout = clients_json
        
        mock_response_close = MagicMock()
        mock_response_close.return_value.returncode = 0
        
        mock_run.side_effect = [
            mock_response_clients.return_value,  # first call: hyprctl clients -j
            mock_response_close.return_value     # second call: hyprctl dispatch closewindow ...
        ]

        module = WindowControlActionModule()
        result = module.execute({"ventana_query": "youtube"})
        
        self.assertTrue(result)
        # Verify calls
        mock_run.assert_any_call(
            ["hyprctl", "clients", "-j"],
            capture_output=True,
            text=True,
            check=True
        )
        mock_run.assert_any_call(
            ["hyprctl", "eval", 'hl.dsp.window.close("address:0x565032688c50")'],
            capture_output=True,
            text=True
        )

    @patch("subprocess.run")
    def test_execute_no_match(self, mock_run):
        clients_json = json.dumps([
            {
                "address": "0x565030d720c0",
                "class": "Alacritty",
                "title": "fernandooxz1@PCLinux:~"
            }
        ])
        
        mock_response = MagicMock()
        mock_response.returncode = 0
        mock_response.stdout = clients_json
        mock_run.return_value = mock_response

        module = WindowControlActionModule()
        result = module.execute({"ventana_query": "nonexistent_app"})
        
        self.assertFalse(result)
        mock_run.assert_called_once_with(
            ["hyprctl", "clients", "-j"],
            capture_output=True,
            text=True,
            check=True
        )

    @patch("subprocess.run")
    def test_execute_hyprctl_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        module = WindowControlActionModule()
        result = module.execute({"ventana_query": "brave"})
        
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_execute_fallback(self, mock_run):
        # Mock clients JSON response
        clients_json = json.dumps([
            {
                "address": "0x565032688c50",
                "class": "brave",
                "title": "Brave Browser"
            }
        ])

        # Lua command fails (returns non-zero or error in stdout), fallback succeeds
        mock_res_clients = MagicMock(returncode=0, stdout=clients_json)
        mock_res_lua_fail = MagicMock(returncode=1, stdout="error: nil value")
        mock_res_fallback_ok = MagicMock(returncode=0)

        mock_run.side_effect = [
            mock_res_clients,
            mock_res_lua_fail,
            mock_res_fallback_ok
        ]

        module = WindowControlActionModule()
        result = module.execute({"ventana_query": "brave"})

        self.assertTrue(result)
        # Verify both commands were tried
        mock_run.assert_any_call(
            ["hyprctl", "eval", 'hl.dsp.window.close("address:0x565032688c50")'],
            capture_output=True,
            text=True
        )
        mock_run.assert_any_call(
            ["hyprctl", "dispatch", "closewindow", "address:0x565032688c50"],
            capture_output=True,
            text=True,
            check=True
        )

    @patch("subprocess.run")
    def test_execute_lua_unsupported_fallback(self, mock_run):
        # Mock clients JSON response
        clients_json = json.dumps([
            {
                "address": "0x565032688c50",
                "class": "brave",
                "title": "Brave Browser"
            }
        ])

        # Lua command returns code 0 but with unsupported warning, fallback succeeds
        mock_res_clients = MagicMock(returncode=0, stdout=clients_json)
        mock_res_lua_unsupported = MagicMock(returncode=0, stdout="eval is only supported with the lua config manager")
        mock_res_fallback_ok = MagicMock(returncode=0)

        mock_run.side_effect = [
            mock_res_clients,
            mock_res_lua_unsupported,
            mock_res_fallback_ok
        ]

        module = WindowControlActionModule()
        result = module.execute({"ventana_query": "brave"})

        self.assertTrue(result)
        # Verify both commands were tried
        mock_run.assert_any_call(
            ["hyprctl", "eval", 'hl.dsp.window.close("address:0x565032688c50")'],
            capture_output=True,
            text=True
        )
        mock_run.assert_any_call(
            ["hyprctl", "dispatch", "closewindow", "address:0x565032688c50"],
            capture_output=True,
            text=True,
            check=True
        )


if __name__ == "__main__":
    unittest.main()
