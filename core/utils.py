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


def get_pc_volume() -> int:
    """Obtiene el volumen actual del sistema Linux en porcentaje (0-100)."""
    try:
        res = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if res.returncode == 0:
            import re
            matches = re.findall(r"(\d+)%", res.stdout)
            if matches:
                return int(matches[0])
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["amixer", "get", "Master"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if res.returncode == 0:
            import re
            matches = re.findall(r"\[(\d+)%\]", res.stdout)
            if matches:
                return int(matches[0])
    except Exception:
        pass
    return 50  # Fallback predeterminado


def set_pc_volume(percentage: int):
    """Establece el volumen del sistema Linux al porcentaje exacto."""
    try:
        # Intentar con PulseAudio/PipeWire (pactl)
        subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percentage}%"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Volumen del sistema ajustado vía pactl a: {percentage}%")
    except Exception:
        # Fallback a ALSA (amixer)
        try:
            subprocess.run(
                ["amixer", "set", "Master", f"{percentage}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"Volumen del sistema ajustado vía amixer a: {percentage}%")
        except Exception as e:
            logger.error(f"No se pudo ajustar el volumen del sistema: {e}")


def change_pc_volume_relative(delta: int) -> None:
    """
    Ajusta el volumen del sistema de forma relativa, respetando la atenuación del asistente.
    """
    try:
        import core.web_server as web_server
        assistant = getattr(web_server, "assistant_instance", None)
    except Exception:
        assistant = None

    if assistant and hasattr(assistant, "listener") and getattr(assistant.listener, "original_volume", None) is not None:
        # Si el volumen está atenuado temporalmente, modificamos el volumen original guardado
        orig = assistant.listener.original_volume
        new_vol = max(0, min(100, orig + delta))
        assistant.listener.original_volume = new_vol
        logger.info(f"[Utils] Ajustando volumen original guardado de {orig}% a {new_vol}% (durante la atenuación)")
    else:
        # Si no está atenuado, modificamos el volumen actual del sistema
        current = get_pc_volume()
        new_vol = max(0, min(100, current + delta))
        set_pc_volume(new_vol)


def get_browser_command() -> str:
    """
    Determina de forma dinámica el comando ejecutable del navegador web predeterminado
    leyendo la configuración de XDG e inspeccionando el correspondiente archivo .desktop.
    """
    try:
        import subprocess
        res = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=2)
        desktop_file = res.stdout.strip()
        if desktop_file:
            paths = [
                os.path.expanduser(f"~/.local/share/applications/{desktop_file}"),
                f"/usr/share/applications/{desktop_file}",
                f"/usr/local/share/applications/{desktop_file}"
            ]
            for path in paths:
                if os.path.exists(path):
                    with open(path, "r", errors="ignore") as f:
                        for line in f:
                            if line.startswith("Exec="):
                                exec_val = line.split("=", 1)[1].strip()
                                cmd = exec_val.split()[0]
                                cmd = cmd.replace('"', '').replace("'", "")
                                return os.path.basename(cmd)
    except Exception as e:
        logger.debug(f"Error al determinar navegador por .desktop: {e}")

    # Fallbacks si no se pudo determinar
    import shutil
    for fallback in ["brave", "firefox", "google-chrome", "chromium", "zen-browser", "microsoft-edge-stable"]:
        if shutil.which(fallback):
            return fallback

    return "xdg-open"


