import unittest
import subprocess
import shlex
import psutil
from unittest.mock import patch, call, MagicMock

from actions.scene_action import SceneActionModule


class TestSceneActionModule(unittest.TestCase):
    def setUp(self):
        self.config = {
            "whitelist_apps": [
                "brave", "code", "nautilus", "alacritty", "libreoffice", "cliamp", "discord", "steam", "omarchy-launch-webapp"
            ],
            "keyboard_macros": {
                "pone musica": [{"type": "ydotool", "args": ["key", "dummy"]}]
            },
            "scenes": {
                "estudio": {
                    "close_processes": ["discord", "steam"],
                    "open_apps": [
                        "omarchy-launch-webapp https://notebooklm.google.com/",
                        "omarchy-launch-webapp https://gemini.google.com/app?hl=es"
                    ],
                    "macros": [
                        "pone musica",
                        "SUPER + CTRL + N"
                    ],
                    "pomodoro": True
                },
                "gaming": {
                    "close_processes": ["chrome", "brave", "firefox"],
                    "open_apps": ["steam"]
                },
                "trabajo": {
                    "open_apps": [
                        "alacritty -e agy",
                        "omarchy-launch-webapp https://gemini.google.com/app?hl=es",
                        "brave https://youtube.com"
                    ],
                    "youtube_play": "mix de Ariel coronel"
                }
            }
        }
        self.module = SceneActionModule(config=self.config)

    def test_validate_entities_success(self):
        entities = {"escenario": "estudio"}
        self.assertTrue(self.module.validate_entities(entities))
        self.assertEqual(entities["escenario"], "estudio")

    def test_validate_entities_success_case_insensitive(self):
        entities = {"escenario": "GAMING"}
        self.assertTrue(self.module.validate_entities(entities))
        self.assertEqual(entities["escenario"], "gaming")

    def test_validate_entities_missing(self):
        entities = {}
        self.assertFalse(self.module.validate_entities(entities))

    def test_validate_entities_not_configured(self):
        entities = {"escenario": "cine"}
        self.assertFalse(self.module.validate_entities(entities))

    @patch("time.sleep")
    @patch("psutil.process_iter")
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("actions.keyboard_automation_action.KeyboardAutomationModule")
    @patch("actions.youtube_play_action.YoutubePlayActionModule")
    def test_execute_estudio_scene(self, mock_yt_class, mock_kb_class, mock_popen, mock_run, mock_process_iter, mock_sleep):
        # Setup mock processes to be closed
        mock_proc1 = MagicMock()
        mock_proc1.info = {'pid': 1234, 'name': 'Discord'}
        mock_proc2 = MagicMock()
        mock_proc2.info = {'pid': 5678, 'name': 'steamwebhelper'}
        mock_proc3 = MagicMock()
        mock_proc3.info = {'pid': 9999, 'name': 'something_else'}
        mock_process_iter.return_value = [mock_proc1, mock_proc2, mock_proc3]

        # Setup mock KeyboardAutomationModule instance
        mock_kb_instance = MagicMock()
        mock_kb_class.return_value = mock_kb_instance

        with patch("importlib.import_module") as mock_import:
            # Setup mock Pomodoro Action Module
            mock_pomo_module = MagicMock()
            mock_pomo_class = MagicMock()
            mock_pomo_instance = MagicMock()
            mock_pomo_class.return_value = mock_pomo_instance
            mock_pomo_module.PomodoroActionModule = mock_pomo_class
            mock_import.return_value = mock_pomo_module

            # Execute Estudio scene
            entities = {"escenario": "estudio"}
            result = self.module.execute(entities)

            self.assertTrue(result)

            # Assert blacklisted processes were terminated cleanly
            mock_proc1.terminate.assert_called_once()
            mock_proc2.terminate.assert_called_once()
            mock_proc3.terminate.assert_not_called()

            # Assert workspaces were switched sequentially:
            # NotebookLM in workspace 1, Gemini in workspace 2
            mock_run.assert_has_calls([
                call(["hyprctl", "dispatch", "workspace", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                call(["hyprctl", "dispatch", "workspace", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ], any_order=False)

            # Assert applications were launched
            mock_popen.assert_has_calls([
                call(shlex.split("omarchy-launch-webapp https://notebooklm.google.com/"), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                call(shlex.split("omarchy-launch-webapp https://gemini.google.com/app?hl=es"), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ])

            # Assert macros were executed
            mock_kb_instance.execute.assert_called_once_with({"macro": "pone musica"})
            mock_kb_instance._execute_string_macro.assert_called_once_with("SUPER + CTRL + N")

            # Assert Pomodoro was triggered
            mock_import.assert_any_call("actions.pomodoro_action")
            mock_pomo_instance.execute.assert_called_once_with({})

    @patch("time.sleep")
    @patch("psutil.process_iter")
    @patch("subprocess.run")
    @patch("subprocess.Popen")
    @patch("actions.youtube_play_action.YoutubePlayActionModule")
    def test_execute_trabajo_scene(self, mock_yt_class, mock_popen, mock_run, mock_process_iter, mock_sleep):
        mock_process_iter.return_value = []
        mock_yt_instance = MagicMock()
        mock_yt_class.return_value = mock_yt_instance

        entities = {"escenario": "trabajo"}
        result = self.module.execute(entities)

        self.assertTrue(result)

        # Assert workspaces switches:
        # agy -> workspace 1
        # gemini -> workspace 2
        # youtube -> workspace 9
        mock_run.assert_has_calls([
            call(["hyprctl", "dispatch", "workspace", "1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            call(["hyprctl", "dispatch", "workspace", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            call(["hyprctl", "dispatch", "workspace", "9"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ], any_order=False)

        # Assert apps opened
        mock_popen.assert_has_calls([
            call(shlex.split("alacritty -e agy"), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            call(shlex.split("omarchy-launch-webapp https://gemini.google.com/app?hl=es"), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
            call(shlex.split("brave https://youtube.com"), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ])

        # Assert YouTube playback was called for "mix de Ariel coronel"
        mock_yt_instance.execute.assert_called_once_with({"busqueda": "mix de Ariel coronel"})


if __name__ == '__main__':
    unittest.main()
