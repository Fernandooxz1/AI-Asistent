import time
import subprocess
import logging
import unicodedata

logger = logging.getLogger("Viernes")

class KeyboardAutomationModule:
    """
    Módulo encargado de ejecutar macros secuenciales de teclado y comandos de Hyprland.
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

    def execute(self, entities: dict) -> bool:
        comando_voz_crudo = entities.get("_raw_text", "")
        
        macro_actions = None
        
        # 1. Intentar resolver por entidad "macro" (extraída por la IA o Cortocircuito)
        macro_entidad = entities.get("macro")
        if macro_entidad and macro_entidad in self.macros_db:
            macro_actions = self.macros_db[macro_entidad]
            logger.info(f"🎯 Macro detectada por entidad: '{macro_entidad}'")
        
        # 2. Fallback: búsqueda difusa de subcadena tradicional si la entidad falló
        if not macro_actions:
            comando_voz = self._limpiar_texto(comando_voz_crudo)
            macros_ordenadas = sorted(self.macros_db.items(), key=lambda item: len(item[0]), reverse=True)
            for key, actions in macros_ordenadas:
                key_limpia = self._limpiar_texto(key)
                if key_limpia in comando_voz:
                    macro_actions = actions
                    logger.info(f"🎯 Macro detectada por subcadena: '{key}'")
                    break

        if not macro_actions:
            logger.warning(f"No se encontró ninguna macro de teclado para la frase: '{comando_voz_crudo}'")
            return False

        try:
            for action in macro_actions:
                act_type = action.get("type")  # 🚨 ACÁ ESTABA EL ERROR: Es "type", no "ydotool"
                
                if act_type == "ydotool":
                    cmd = ["ydotool"] + action.get("args", [])
                    # Sacamos el stderr=DEVNULL para que si ydotool falla, lo veamos en rojo
                    subprocess.run(cmd, stdout=subprocess.DEVNULL)
                    
                elif act_type == "hyprctl":
                    cmd = ["hyprctl"] + action.get("args", [])
                    subprocess.run(cmd, stdout=subprocess.DEVNULL)
                    
                elif act_type == "comando":  # 🚨 NUEVO: Para pausar la música con tmux
                    cmd = action.get("args", [])
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                elif act_type == "sleep":
                    time.sleep(action.get("duration", 0.1))
                    
            return True
        except Exception as e:
            logger.error(f"Error crítico al ejecutar la macro de teclado: {e}")
            return False