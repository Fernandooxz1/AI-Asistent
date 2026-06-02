import unittest
import threading
import time
from unittest.mock import MagicMock, patch
from core.pomodoro import PomodoroTimer

class TestPomodoroTimer(unittest.TestCase):
    def setUp(self):
        self.timer = PomodoroTimer()

    def tearDown(self):
        if self.timer.active:
            self.timer.pause()
        self.timer.stop_event.set()

    def test_initial_state(self):
        status = self.timer.get_status()
        self.assertFalse(status["active"])
        self.assertEqual(status["state"], "work")
        self.assertEqual(status["time_left"], 25 * 60)

    @patch("core.pomodoro.PomodoroTimer.broadcast_state")
    def test_start_pause_reset(self, mock_broadcast):
        # Start
        self.timer.start()
        status = self.timer.get_status()
        self.assertTrue(status["active"])
        self.assertTrue(mock_broadcast.called)
        
        # Multiple starts should not deadlock or spawn duplicate threads
        thread_before = self.timer.thread
        self.timer.start()
        self.assertEqual(self.timer.thread, thread_before)
        
        # Pause
        mock_broadcast.reset_mock()
        self.timer.pause()
        status = self.timer.get_status()
        self.assertFalse(status["active"])
        self.assertTrue(mock_broadcast.called)

        # Reset
        mock_broadcast.reset_mock()
        self.timer.reset()
        status = self.timer.get_status()
        self.assertFalse(status["active"])
        self.assertEqual(status["state"], "work")
        self.assertEqual(status["time_left"], 25 * 60)
        self.assertTrue(mock_broadcast.called)

    @patch("core.web_server.manager.broadcast")
    @patch("core.web_server.uvicorn_loop")
    def test_broadcast_state(self, mock_loop, mock_broadcast):
        # Mock uvicorn loop and running status
        mock_loop.is_running.return_value = True
        
        # Trigger broadcast
        self.timer.broadcast_state()
        
        # Assert uvicorn broadcast was called asynchronously
        import asyncio
        from unittest.mock import ANY
        # Check if asyncio.run_coroutine_threadsafe was called
        # We can patch asyncio.run_coroutine_threadsafe to assert it was called
        with patch("asyncio.run_coroutine_threadsafe") as mock_run_safe:
            self.timer.broadcast_state()
            mock_run_safe.assert_called_once()

if __name__ == "__main__":
    unittest.main()
