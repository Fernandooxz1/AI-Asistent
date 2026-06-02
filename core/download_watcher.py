import os
import time
import logging
import threading
from typing import Callable, Optional, Set, Dict, Tuple

# Try importing watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

logger = logging.getLogger("Viernes.DownloadWatcher")

TEMP_EXTENSIONS: Set[str] = {'.crdownload', '.part', '.tmp', '.download'}

class DownloadWatcher:
    def __init__(self, watch_dir: Optional[str] = None, callback: Optional[Callable[[str], None]] = None):
        """
        Monitors a download directory (default ~/Descargas) for completed downloads.
        
        Args:
            watch_dir: Directory to watch. Defaults to ~/Descargas.
            callback: Function to call when a download completes. Takes the absolute file path as an argument.
        """
        if watch_dir is None:
            self.watch_dir = os.path.expanduser("~/Descargas")
        else:
            self.watch_dir = os.path.abspath(watch_dir)
            
        self.callback = callback or self._default_callback
        self.observer = None
        self.running = False
        
        # Track directly written files: {filepath: (last_size, last_mtime, first_seen_time, stable_count)}
        self.active_writes: Dict[str, Tuple[int, float, float, int]] = {}
        self.lock = threading.Lock()
        self.poll_thread: Optional[threading.Thread] = None

    def _default_callback(self, filepath: str) -> None:
        logger.info(f"Download completed: {filepath}")

    def start(self) -> None:
        """Starts the download watcher."""
        if self.running:
            logger.warning("DownloadWatcher is already running.")
            return

        # Ensure download directory exists
        try:
            os.makedirs(self.watch_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create watch directory {self.watch_dir}: {e}")
            return

        self.running = True
        self.active_writes.clear()

        # Start the polling thread to check for stable files (direct writes)
        self.poll_thread = threading.Thread(target=self._poll_active_writes, daemon=True, name="DownloadWatcherPoll")
        self.poll_thread.start()

        if HAS_WATCHDOG:
            logger.info(f"Starting Watchdog observer on {self.watch_dir}")
            event_handler = self._create_event_handler()
            self.observer = Observer()
            self.observer.schedule(event_handler, self.watch_dir, recursive=False)
            self.observer.start()
        else:
            logger.warning("watchdog library not found. Falling back to passive directory polling.")

    def stop(self) -> None:
        """Stops the download watcher."""
        if not self.running:
            return

        self.running = False
        
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=2.0)
            except Exception as e:
                logger.error(f"Error stopping observer: {e}")
            self.observer = None

        if self.poll_thread:
            self.poll_thread.join(timeout=2.0)
            self.poll_thread = None

        logger.info("DownloadWatcher stopped.")

    def is_running(self) -> bool:
        return self.running

    def _create_event_handler(self):
        watcher_self = self
        
        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                watcher_self._handle_created_or_modified(event.src_path)

            def on_modified(self, event):
                if event.is_directory:
                    return
                watcher_self._handle_created_or_modified(event.src_path)

            def on_moved(self, event):
                if event.is_directory:
                    return
                watcher_self._handle_moved(event.src_path, event.dest_path)

        return Handler()

    def _has_temp_extension(self, path: str) -> bool:
        _, ext = os.path.splitext(path)
        return ext.lower() in TEMP_EXTENSIONS or path.endswith('.part')

    def _handle_created_or_modified(self, filepath: str) -> None:
        # Ignore files with temporary extensions
        if self._has_temp_extension(filepath):
            return

        # If it's a normal file, track it to verify when it's fully written
        with self.lock:
            if filepath not in self.active_writes:
                try:
                    stat = os.stat(filepath)
                    now = time.time()
                    self.active_writes[filepath] = (stat.st_size, stat.st_mtime, now, 0)
                    logger.debug(f"Tracking new file for completion: {filepath}")
                except OSError:
                    pass

    def _handle_moved(self, src_path: str, dest_path: str) -> None:
        was_temp = self._has_temp_extension(src_path)
        is_normal = not self._has_temp_extension(dest_path)

        if is_normal:
            if was_temp:
                # Chrome/Firefox temp file completion
                logger.info(f"Detected transition from temp file: {src_path} -> {dest_path}")
                self._trigger_callback(dest_path)
            else:
                # Normal file moved here from elsewhere. It is already complete,
                # but track it to ensure stability (e.g. if it's a slow copy).
                self._handle_created_or_modified(dest_path)

            # Clean up any tracking for the src_path
            with self.lock:
                self.active_writes.pop(src_path, None)

    def _trigger_callback(self, filepath: str) -> None:
        try:
            self.callback(filepath)
        except Exception as e:
            logger.error(f"Error in DownloadWatcher callback: {e}")

    def _poll_active_writes(self) -> None:
        """
        Background polling loop:
        1. Checks size/mtime stability for directly written files.
        2. If watchdog is not available, scans the directory passively.
        """
        last_passive_scan = 0.0
        known_files_passive = set()
        
        if not HAS_WATCHDOG:
            try:
                known_files_passive = set(os.listdir(self.watch_dir))
            except Exception:
                pass

        while self.running:
            time.sleep(1.0)
            now = time.time()

            # 1. Passive directory polling fallback (if watchdog is missing)
            if not HAS_WATCHDOG:
                if now - last_passive_scan >= 2.0:
                    last_passive_scan = now
                    try:
                        current_files = set(os.listdir(self.watch_dir))
                        new_files = current_files - known_files_passive
                        for fname in new_files:
                            fpath = os.path.join(self.watch_dir, fname)
                            if os.path.isfile(fpath):
                                self._handle_created_or_modified(fpath)
                        known_files_passive = current_files
                    except Exception as e:
                        logger.error(f"Error in passive directory scanning: {e}")

            # 2. Check stability of active writes
            completed_files = []
            with self.lock:
                for filepath, (last_size, last_mtime, first_seen, stable_count) in list(self.active_writes.items()):
                    try:
                        stat = os.stat(filepath)
                        current_size = stat.st_size
                        current_mtime = stat.st_mtime

                        if current_size == last_size and current_mtime == last_mtime:
                            new_stable_count = stable_count + 1
                            if new_stable_count >= 2:
                                completed_files.append(filepath)
                                self.active_writes.pop(filepath, None)
                            else:
                                self.active_writes[filepath] = (current_size, current_mtime, first_seen, new_stable_count)
                        else:
                            self.active_writes[filepath] = (current_size, current_mtime, first_seen, 0)
                    except OSError:
                        self.active_writes.pop(filepath, None)

            # Trigger callbacks outside the lock
            for filepath in completed_files:
                logger.info(f"Detected completed direct write/copy: {filepath}")
                self._trigger_callback(filepath)
