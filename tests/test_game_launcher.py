import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import subprocess

from actions.game_launcher_action import GameLauncherModule, replace_roman_numerals


class TestGameLauncherModule(unittest.TestCase):

    def setUp(self):
        self.config = {
            "games": {
                "resident evil 8": {"platform": "steam", "id": "12345"},
                "dragon ball": {"platform": "lutris", "id": "dbz_id"}
            }
        }
        self.launcher = GameLauncherModule(self.config)

    def test_replace_roman_numerals(self):
        self.assertEqual(replace_roman_numerals("baldur's gate iii"), "baldur's gate 3")
        self.assertEqual(replace_roman_numerals("grand theft auto v"), "grand theft auto 5")
        self.assertEqual(replace_roman_numerals("doom ii"), "doom 2")

    @patch("subprocess.Popen")
    @patch("actions.game_launcher_action.GameLauncherModule._liberar_vram_y_cerrar")
    def test_execute_from_config_steam(self, mock_liberar, mock_popen):
        result = self.launcher.execute({"juego": "resident evil 8"})
        self.assertTrue(result)
        mock_popen.assert_called_once_with(
            ["xdg-open", "steam://rungameid/12345"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        mock_liberar.assert_called_once()

    @patch("subprocess.Popen")
    @patch("actions.game_launcher_action.GameLauncherModule._liberar_vram_y_cerrar")
    def test_execute_from_config_lutris_workspace(self, mock_liberar, mock_popen):
        result = self.launcher.execute({"juego": "dragon ball", "workspace": "4"})
        self.assertTrue(result)
        mock_popen.assert_called_once_with(
            ["hyprctl", "dispatch", "exec", "[workspace 4 silent] lutris lutris:rungame/dbz_id"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        mock_liberar.assert_called_once()

    @patch("os.path.exists")
    @patch("os.walk")
    @patch("builtins.open", new_callable=mock_open, read_data="[Desktop Entry]\nName=Baldur's Gate III\nExec=steam steam://rungameid/13747480236176441344\n")
    @patch("subprocess.Popen")
    @patch("actions.game_launcher_action.GameLauncherModule._liberar_vram_y_cerrar")
    def test_execute_desktop_fallback(self, mock_liberar, mock_popen, mock_file, mock_walk, mock_exists):
        # Setup filesystem mocks
        mock_exists.return_value = True
        mock_walk.return_value = [
            ("/home/fernando/.local/share/applications", [], ["Baldur's Gate III.desktop"])
        ]

        result = self.launcher.execute({"juego": "baldurs-gate-3", "workspace": "3"})
        self.assertTrue(result)
        mock_popen.assert_called_once_with(
            ["hyprctl", "dispatch", "exec", "[workspace 3 silent] steam steam://rungameid/13747480236176441344"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        mock_liberar.assert_called_once()


if __name__ == "__main__":
    import subprocess
    unittest.main()
