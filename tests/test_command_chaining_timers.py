import unittest
from unittest.mock import patch, MagicMock, call
import time

from core.intent_parser import IntentParser
from actions.keyboard_automation_action import KeyboardAutomationModule

class TestCommandChainingAndTimers(unittest.TestCase):
    
    # ── COMMAND CHAINING / SPLITTING TESTS ──
    @patch("ollama.chat")
    def test_command_chaining_split(self, mock_chat):
        # Configure IntentParser with keyboard macros
        config = {
            "model_name": "dummy_model",
            "intents": ["automatizacion_teclado"],
            "keyboard_macros": {
                "pone musica": [{"type": "ydotool", "args": ["key", "dummy"]}],
                "abrir firefox": [{"type": "ydotool", "args": ["key", "dummy"]}]
            }
        }
        parser = IntentParser(config=config)
        
        # Test "y" connector split
        res1 = parser.parse("pone musica y abrir firefox")
        mock_chat.assert_not_called()
        self.assertEqual(len(res1), 2)
        self.assertEqual(res1[0]["entities"]["macro"], "pone musica")
        self.assertEqual(res1[1]["entities"]["macro"], "abrir firefox")

        # Test "luego" connector split
        res2 = parser.parse("pone musica luego abrir firefox")
        self.assertEqual(len(res2), 2)
        self.assertEqual(res2[0]["entities"]["macro"], "pone musica")
        self.assertEqual(res2[1]["entities"]["macro"], "abrir firefox")

        # Test "despues" connector split
        res3 = parser.parse("pone musica despues abrir firefox")
        self.assertEqual(len(res3), 2)
        self.assertEqual(res3[0]["entities"]["macro"], "pone musica")
        self.assertEqual(res3[1]["entities"]["macro"], "abrir firefox")

        # Test "después" connector split
        res4 = parser.parse("pone musica después abrir firefox")
        self.assertEqual(len(res4), 2)
        self.assertEqual(res4[0]["entities"]["macro"], "pone musica")
        self.assertEqual(res4[1]["entities"]["macro"], "abrir firefox")

    # ── MACRO SLEEP TIMERS TESTS ──
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_macro_string_sleep_timer(self, mock_run, mock_sleep):
        module = KeyboardAutomationModule()
        
        # String macro with sleeps and keys:
        # Press SUPER + A, sleep 1.5 seconds, then press CTRL + C, sleep 0.5 seconds
        macro_str = "SUPER + A, -1.5, CTRL + C, -0.5"
        
        module._execute_string_macro(macro_str)
        
        # Check sleep durations parsed and executed
        # It also does default 0.05s sleeps after releases in _execute_string_macro
        mock_sleep.assert_any_call(1.5)
        mock_sleep.assert_any_call(0.5)

    # ── DISPATCHER-LEVEL SMART PAUSE TESTS ──
    @patch("time.sleep")
    def test_dispatcher_smart_pause_logic(self, mock_sleep):
        # We simulate the exact dispatch sequential logic from main.py and web_server.py
        def execute_commands_with_pauses(commands, mock_dispatcher):
            for idx, cmd in enumerate(commands):
                if idx > 0:
                    prev_intent = commands[idx-1].get("intent")
                    if prev_intent in ["reproducir_youtube", "abrir_aplicacion", "abrir_navegador", "lanzar_juego"]:
                        time.sleep(2.5)
                    else:
                        time.sleep(0.5)
                mock_dispatcher.dispatch(cmd)

        mock_dispatcher = MagicMock()
        
        # Scenario 1: YouTube play followed by a keyboard macro
        commands_1 = [
            {"intent": "reproducir_youtube", "entities": {"busqueda": "gatos"}},
            {"intent": "automatizacion_teclado", "entities": {"macro": "pone musica"}}
        ]
        execute_commands_with_pauses(commands_1, mock_dispatcher)
        mock_sleep.assert_called_with(2.5)
        
        mock_sleep.reset_mock()
        
        # Scenario 2: Keyboard macro followed by another keyboard macro
        commands_2 = [
            {"intent": "automatizacion_teclado", "entities": {"macro": "pone musica"}},
            {"intent": "automatizacion_teclado", "entities": {"macro": "subir volumen"}}
        ]
        execute_commands_with_pauses(commands_2, mock_dispatcher)
        mock_sleep.assert_called_with(0.5)

if __name__ == "__main__":
    unittest.main()
