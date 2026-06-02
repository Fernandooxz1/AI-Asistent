import unittest
import subprocess
from unittest.mock import patch, call
from actions.keyboard_automation_action import KeyboardAutomationModule

class TestKeyboardMacros(unittest.TestCase):
    
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_execute_string_macro_combo(self, mock_run, mock_sleep):
        module = KeyboardAutomationModule()
        # Test combo "SUPER + SHIFT + M"
        module._execute_string_macro("SUPER + SHIFT + M")
        
        # SUPER=125, SHIFT=42, M=50
        # Expected presses: 125:1, 42:1, 50:1 (in order)
        # Expected releases: 50:0, 42:0, 125:0 (in reverse order)
        
        mock_run.assert_has_calls([
            call(["ydotool", "key", "125:1"], stdout=subprocess.DEVNULL),
            call(["ydotool", "key", "42:1"], stdout=subprocess.DEVNULL),
            call(["ydotool", "key", "50:1"], stdout=subprocess.DEVNULL),
            call(["ydotool", "key", "50:0"], stdout=subprocess.DEVNULL),
            call(["ydotool", "key", "42:0"], stdout=subprocess.DEVNULL),
            call(["ydotool", "key", "125:0"], stdout=subprocess.DEVNULL)
        ])
        
        # Check that we slept between presses (0.2s) and after release (0.05s)
        mock_sleep.assert_has_calls([
            call(0.2),
            call(0.2),
            call(0.2),
            call(0.05)
        ])

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_execute_string_macro_sleep_and_cmd(self, mock_run, mock_sleep):
        module = KeyboardAutomationModule()
        # Test "SUPER + A, -1.5, cmd:pkill -f dummy"
        module._execute_string_macro("SUPER + A, -1.5, cmd:pkill -f dummy")
        
        # Assert sleep 1.5 was called
        mock_sleep.assert_any_call(1.5)
        
        # Assert system command was executed
        mock_run.assert_any_call(["pkill", "-f", "dummy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == '__main__':
    unittest.main()
