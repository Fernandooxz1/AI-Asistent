import os
import sys
import subprocess
import logging
from typing import Final, List

logger = logging.getLogger("Viernes.Utils")

def play_sound(filename: str) -> None:
    """
    Plays a sound file asynchronously using system audio players.
    
    Supported players: aplay (ALSA), paplay (PulseAudio), ffplay (FFmpeg).
    Supports PyInstaller bundle paths dynamically (_MEIPASS).
    
    Args:
        filename: Name of the sound file under the 'sounds' directory.
    """
    # 1. Resolve path depending on standard Python execution or PyInstaller bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path: str = sys._MEIPASS
    else:
        # En desarrollo, usamos el directorio raíz del proyecto (padre de core/)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    sound_path: Final[str] = os.path.join(base_path, "sounds", filename)

    # 2. Check if the sound file actually exists to avoid executing failed processes
    if not os.path.exists(sound_path):
        logger.warning(f"Sound file not found: {sound_path}")
        # Debug list of sounds if directory exists
        sounds_dir = os.path.join(base_path, "sounds")
        if os.path.exists(sounds_dir):
            logger.debug(f"Available files in {sounds_dir}: {os.listdir(sounds_dir)}")
        return

    # 3. Attempt execution using system players in descending order of performance/commonality
    players: Final[List[List[str]]] = [
        ["aplay", "-q", sound_path],
        ["paplay", sound_path],
        ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "quiet", sound_path]
    ]

    for player in players:
        try:
            # start_new_session=True detaches the child process from the parent group
            subprocess.Popen(
                player,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.debug(f"Dispatched sound playback using player: {player[0]}")
            return
        except FileNotFoundError:
            # Expected if the audio utility is not installed; fall back silently
            continue
        except Exception as e:
            logger.debug(f"Failed to play sound via {player[0]}: {e}")
            continue

    logger.warning(
        f"Unable to play sound '{filename}'. Ensure aplay, paplay, or ffplay is installed."
    )
