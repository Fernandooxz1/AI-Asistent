import threading
import time
import logging

logger = logging.getLogger("PomodoroTimer")

class PomodoroTimer:
    def __init__(self, assistant=None):
        self.assistant = assistant
        self.work_duration = 25 * 60  # 25 minutes in seconds
        self.rest_duration = 5 * 60   # 5 minutes in seconds
        
        self.active = False
        self.time_left = self.work_duration
        self.duration = self.work_duration
        self.state = "work"  # "work" or "rest"
        
        self.thread = None
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        
    def start(self):
        should_broadcast = False
        with self.lock:
            if not self.active:
                self.active = True
                self.stop_event.clear()
                # Start countdown thread if not running
                if self.thread is None or not self.thread.is_alive():
                    self.thread = threading.Thread(target=self._run_loop, daemon=True)
                    self.thread.start()
                logger.info("Pomodoro timer started.")
                should_broadcast = True
        if should_broadcast:
            self.broadcast_state()

    def pause(self):
        should_broadcast = False
        with self.lock:
            if self.active:
                self.active = False
                logger.info("Pomodoro timer paused.")
                should_broadcast = True
        if should_broadcast:
            self.broadcast_state()

    def reset(self):
        with self.lock:
            self.active = False
            self.state = "work"
            self.duration = self.work_duration
            self.time_left = self.work_duration
            logger.info("Pomodoro timer reset.")
        self.broadcast_state()

    def get_status(self):
        with self.lock:
            return {
                "active": self.active,
                "time_left": self.time_left,
                "duration": self.duration,
                "state": self.state
            }

    def _run_loop(self):
        while not self.stop_event.is_set():
            time.sleep(1)
            with self.lock:
                if not self.active:
                    continue
                
                if self.time_left > 0:
                    self.time_left -= 1
                else:
                    # Transition between work and rest
                    if self.state == "work":
                        self.state = "rest"
                        self.duration = self.rest_duration
                        self.time_left = self.rest_duration
                        # Play transition sound
                        try:
                            from core.utils import play_sound
                            play_sound("wake.wav")
                        except Exception as e:
                            logger.error(f"Error playing rest transition sound: {e}")
                    else:
                        self.state = "work"
                        self.duration = self.work_duration
                        self.time_left = self.work_duration
                        # Play transition sound
                        try:
                            from core.utils import play_sound
                            play_sound("success.wav")
                        except Exception as e:
                            logger.error(f"Error playing work transition sound: {e}")
            
            self.broadcast_state()

    def broadcast_state(self):
        try:
            import core.web_server as web_server
            if web_server.uvicorn_loop and web_server.uvicorn_loop.is_running():
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    web_server.manager.broadcast({
                        "type": "pomodoro",
                        "data": self.get_status()
                    }),
                    web_server.uvicorn_loop
                )
        except Exception as e:
            logger.debug(f"Could not broadcast Pomodoro state: {e}")
