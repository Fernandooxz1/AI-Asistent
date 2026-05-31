import time
import subprocess
import logging
import unicodedata

logger = logging.getLogger("Viernes")

class KeyboardAutomationModule:
    """
    Módulo encargado de ejecutar macros secuenciales de teclado y comandos de Hyprland.
    Soporta control nativo multimedia (playerctl) y guardas inteligentes de ventana activa.
    """
    def __init__(self, config: dict = None, *args, **kwargs) -> None:
        self.nombre = "KeyboardAutomationModule"
        self.config = config if config else {}
        self.macros_db = self.config.get("keyboard_macros", {})

    def _limpiar_texto(self, texto: str) -> str:
        """Elimina tildes y pasa todo a minúsculas para comparaciones perfectas."""
        texto = texto.lower().strip()
        texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
        return texto

    def _get_active_window(self) -> dict:
        try:
            import json
            res = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, check=True)
            return json.loads(res.stdout)
        except Exception:
            return {}

    def _run_playerctl(self, action: str) -> bool:
        try:
            res = subprocess.run(["playerctl", action], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0
        except Exception:
            return False

    def _run_action(self, action: dict, active_class: str) -> bool:
        act_type = action.get("type")
        
        if act_type == "ydotool":
            cmd = ["ydotool"] + action.get("args", [])
            subprocess.run(cmd, stdout=subprocess.DEVNULL)
            return True
            
        elif act_type == "hyprctl":
            cmd = ["hyprctl"] + action.get("args", [])
            subprocess.run(cmd, stdout=subprocess.DEVNULL)
            return True
            
        elif act_type == "playerctl":
            cmd = ["playerctl"] + action.get("args", [])
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
            
        elif act_type == "comando":
            cmd = action.get("args", [])
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
            
        elif act_type == "sleep":
            time.sleep(action.get("duration", 0.1))
            return True
            
        elif act_type == "active_window_select":
            cases = action.get("cases", {})
            default_actions = action.get("default", [])
            
            matched_actions = default_actions
            for win_class, act_list in cases.items():
                if win_class.lower() == active_class:
                    matched_actions = act_list
                    logger.info(f"Coincidencia de ventana activa '{win_class}': ejecutando acciones específicas.")
                    break
                    
            for sub_action in matched_actions:
                self._run_action(sub_action, active_class)
            return True
            
        return False

    def execute(self, entities: dict) -> bool:
        comando_voz_crudo = entities.get("_raw_text", "")
        
        macro_actions = None
        macro_entidad = entities.get("macro")
        
        # 1. Intentar control nativo multimedia para macros de reproducción antes de emular teclado
        if macro_entidad in ["pausa el video", "pausa la musica", "pone musica"]:
            logger.info(f"Intentando control nativo multimedia (playerctl play-pause) para macro: '{macro_entidad}'")
            if self._run_playerctl("play-pause"):
                return True
            logger.info("Control nativo falló o no hay reproductores activos. Continuando con la macro estándar...")

        # 2. Intentar resolver por entidad "macro" (extraída por la IA o Cortocircuito)
        if macro_entidad and macro_entidad in self.macros_db:
            macro_actions = self.macros_db[macro_entidad]
            logger.info(f"🎯 Macro detectada por entidad: '{macro_entidad}'")
        
        # 3. Fallback: búsqueda difusa de subcadena tradicional si la entidad falló
        if not macro_actions:
            comando_voz = self._limpiar_texto(comando_voz_crudo)
            macros_ordenadas = sorted(self.macros_db.items(), key=lambda item: len(item[0]), reverse=True)
            for key, actions in macros_ordenadas:
                key_limpia = self._limpiar_texto(key)
                if key_limpia in comando_voz:
                    macro_actions = actions
                    macro_entidad = key
                    logger.info(f"🎯 Macro detectada por subcadena: '{key}'")
                    break

        if not macro_actions:
            logger.warning(f"No se encontró ninguna macro de teclado para la frase: '{comando_voz_crudo}'")
            return False

        # Interceptar volumen nativo antes de procesar las acciones físicas (para coordinar el control de PulseAudio/PipeWire)
        if macro_entidad == "baja el volumen":
            logger.info("Ajustando volumen de la PC (bajar 10% nativo)...")
            try:
                from core.utils import change_pc_volume_relative
                change_pc_volume_relative(-10)
                return True
            except Exception as e:
                logger.error(f"Error al bajar volumen nativo: {e}")
        elif macro_entidad == "subi el volumen":
            logger.info("Ajustando volumen de la PC (subir 10% nativo)...")
            try:
                from core.utils import change_pc_volume_relative
                change_pc_volume_relative(10)
                return True
            except Exception as e:
                logger.error(f"Error al subir volumen nativo: {e}")

        # 4. Obtener ventana activa para aplicar guardas inteligentes
        active_win = self._get_active_window()
        active_class = active_win.get("class", "").lower()
        active_title = active_win.get("title", "").lower()
        logger.info(f"Ventana activa detectada: Clase='{active_class}', Título='{active_title}'")

        # 5. Guardas inteligentes: bloquear emulación de teclas de escritura si no estamos en una ventana multimedia
        MEDIA_WINDOW_PREFIXES = ("brave-browser", "brave", "chrome", "google-chrome", "firefox", "chromium", "vlc", "mpv", "spotify")
        SENSITIVE_MACROS = {"pausa el video", "pone video completo", "modo cine"}
        
        is_media_window = any(active_class.startswith(prefix) for prefix in MEDIA_WINDOW_PREFIXES)
        if macro_entidad in SENSITIVE_MACROS and not is_media_window:
            logger.warning(f"⚠️ La macro de teclado '{macro_entidad}' fue bloqueada para prevenir pulsaciones accidentales en la ventana '{active_class}'.")
            return False

        try:
            for action in macro_actions:
                self._run_action(action, active_class)
            return True
        except Exception as e:
            logger.error(f"Error crítico al ejecutar la macro de teclado: {e}")
            return False