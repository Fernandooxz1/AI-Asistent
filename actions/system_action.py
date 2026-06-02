import subprocess
import logging
import shlex
import re
import threading
from typing import Dict, Any, Set, List, Optional

from .base_action import ActionModule

# Logger dedicado al módulo de acciones del sistema
logger = logging.getLogger(__name__)


class SystemActionModule(ActionModule):
    # Class-level variables to hold active shutdown timer thread
    _active_timer: Optional[threading.Timer] = None
    _timer_lock = threading.Lock()

    """
    Módulo de acción para ejecutar programas del sistema operativo.

    ARQUITECTURA DE SEGURIDAD
    ─────────────────────────
    Este módulo opera bajo un modelo de "lista blanca + lista negra" con
    dos capas de protección:

    1. LISTA NEGRA (DANGEROUS_TERMS): Rechaza de inmediato cualquier comando
        que contenga términos destructivos o de escalada de privilegios, incluso
        si el término aparece como argumento. Esto previene ataques de inyección
        del tipo: programa = "code; sudo rm -rf /".
        Esta lista es INMUTABLE y no puede ser modificada desde config.json.

    2. LISTA BLANCA DINÁMICA (config['whitelist_apps']): Sólo se permite ejecutar
        programas cuyos binarios estén listados en config.json bajo 'whitelist_apps'.
        El administrador puede ampliarla sin tocar código.
        Esto garantiza el principio de mínimo privilegio.

    3. SEPARACIÓN SEGURA DE ARGUMENTOS (shlex.split): En lugar de pasar el
        comando como un string a la shell (shell=True), se usa shlex.split()
        para tokenizar el comando y se lo pasa como lista a subprocess.Popen.
        Esto elimina el vector de inyección de shell (shell=False por defecto).

    4. EJECUCIÓN NO BLOQUEANTE (Popen): Se usa Popen en lugar de run() o
        call() para que el proceso se lance en segundo plano sin bloquear el
        hilo principal de Viernes.
    """

    DANGEROUS_TERMS: Set[str] = {
        "sudo",   # Escalada de privilegios
        "su",     # Cambio de usuario
        "rm",     # Eliminación de archivos
        "mkfs",   # Formateo de sistemas de archivos
        "chmod",  # Cambio de permisos
        "chown",  # Cambio de propietario
        "dd",     # Operaciones de bajo nivel en disco
        "pacman", # Gestor de paquetes Arch (puede instalar/borrar software)
        "yay",    # AUR helper (equivalente a pacman)
        "apt",    # Gestor de paquetes Debian/Ubuntu
        "dnf",    # Gestor de paquetes Fedora/RHEL
        "pip",    # Instalador de paquetes Python
        "curl",   # Descarga y ejecución de scripts remotos
        "wget",   # Descarga de archivos
        "bash",   # Intérprete de shell
        "sh",     # Intérprete de shell POSIX
        "zsh",    # Intérprete de shell Zsh
        "python", # Intérprete Python (podría ejecutar código arbitrario)
        "eval",   # Evaluación de código arbitrario
        ">",      # Redirección de salida (sobreescritura de archivos)
        ">>",     # Redirección de salida (append)
        "|",      # Pipe (encadenamiento de comandos)
        "&",      # Ejecución en segundo plano / AND lógico
        ";",      # Separador de comandos
    }

    def validate_entities(self, entities: Dict[str, Any]) -> bool:
        programa = entities.get("programa")

        if not programa:
            logger.warning("Entidad 'programa' ausente o vacía. No se puede ejecutar.")
            return False

        if not isinstance(programa, str):
            logger.warning(f"Entidad 'programa' tiene tipo inválido: {type(programa)}")
            return False

        return True

    def _is_safe_command(self, command: str) -> bool:
        command_lower = command.lower().strip()

        # CAPA 1: Verificación contra la lista negra.
        tokens_lower = set(shlex.split(command_lower)) if command_lower else set()

        for term in self.DANGEROUS_TERMS:
            if term in tokens_lower or term in command_lower:
                logger.critical(
                    f"[SEGURIDAD] Comando rechazado. Término peligroso detectado: "
                    f"'{term}' en el comando: '{command}'"
                )
                return False

        # CAPA 2: Verificación contra la lista blanca dinámica.
        try:
            tokens = shlex.split(command_lower)
        except ValueError as e:
            logger.warning(f"Error al parsear el comando con shlex: {e}")
            return False

        if not tokens:
            logger.warning("El comando resultó vacío tras el parseo.")
            return False

        base_command = tokens[0]

        # Leer la whitelist desde la configuración inyectada por el Dispatcher
        whitelist: List[str] = self.config.get("whitelist_apps", [])

        if not whitelist:
            logger.warning(
                "[SEGURIDAD] 'whitelist_apps' no está definida en config.json. "
                "Todos los comandos serán rechazados por seguridad."
            )
            return False

        if base_command not in whitelist:
            logger.warning(
                f"[SEGURIDAD] Comando rechazado. El programa '{base_command}' "
                f"no está en 'whitelist_apps' de config.json."
            )
            return False

        return True

    @classmethod
    def cancel_shutdown(cls) -> bool:
        """Cancela un apagado programado si existe alguno activo."""
        with cls._timer_lock:
            if cls._active_timer is not None:
                cls._active_timer.cancel()
                cls._active_timer = None
                return True
            return False

    @classmethod
    def schedule_shutdown(cls, seconds: int, qty: int, unit_label: str) -> None:
        """Programa un apagado del sistema mediante systemctl poweroff."""
        def perform_shutdown():
            logger.warning("El temporizador ha expirado. Ejecutando systemctl poweroff...")
            try:
                subprocess.Popen(["systemctl", "poweroff"])
            except Exception as e:
                logger.error(f"Error al ejecutar el apagado del sistema: {e}")

        with cls._timer_lock:
            if cls._active_timer is not None:
                cls._active_timer.cancel()
                logger.info("Cancelando el apagado programado anterior para establecer uno nuevo.")
            
            cls._active_timer = threading.Timer(seconds, perform_shutdown)
            cls._active_timer.daemon = True
            cls._active_timer.start()

        # Feedback de voz y logs
        msg = f"Apagado programado en {qty} {unit_label}."
        logger.warning(msg)
        try:
            from core import tts
            tts.say(msg)
        except Exception as e:
            logger.error(f"Error al reproducir TTS: {e}")

    def _parse_deferred_shutdown(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Analiza el texto para detectar comandos de apagado diferido.
        Soporta minutos, horas y números en español.
        """
        text_lower = text.lower().strip()
        
        # Verificar que sea un comando de apagado
        if not any(k in text_lower for k in ["apaga", "apagar", "shutdown", "poweroff"]):
            return None
            
        spanish_numbers = {
            "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3,
            "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
            "ocho": 8, "nueve": 9, "diez": 10, "quince": 15,
            "veinte": 20, "treinta": 30, "cuarenta": 40,
            "cincuenta": 50
        }
        
        # Regex para capturar la cantidad y la unidad (minutos, horas, etc.)
        pattern = r"(?:en|dentro de|dentro)\s+(?P<cantidad>\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince|veinte|treinta|cuarenta|cincuenta)\s+(?P<unidad>minuto|minutos|min|hora|horas|h)"
        match = re.search(pattern, text_lower)
        
        if match:
            qty_str = match.group("cantidad")
            unit_str = match.group("unidad")
            
            if qty_str.isdigit():
                qty = int(qty_str)
            else:
                qty = spanish_numbers.get(qty_str, 1)
                
            if "min" in unit_str:
                seconds = qty * 60
                unit_label = "minuto" if qty == 1 else "minutos"
            elif "hor" in unit_str or unit_str == "h":
                seconds = qty * 3600
                unit_label = "hora" if qty == 1 else "horas"
            else:
                seconds = qty
                unit_label = "segundos"
                
            return {
                "delay_seconds": seconds,
                "quantity": qty,
                "unit": unit_label
            }
            
        # Si no se especifica tiempo pero se solicita explícitamente apagar la PC,
        # programar para 60 segundos por seguridad (permitiendo cancelación si fue un error).
        if any(k in text_lower for k in ["apaga la pc", "apagar la pc", "apagar el sistema"]):
            return {
                "delay_seconds": 60,
                "quantity": 1,
                "unit": "minuto"
            }
            
        return None

    def execute(self, entities: Dict[str, Any]) -> bool:
        # Obtener el comando e inyectar el texto original de forma segura
        command: str = entities.get("programa", "").strip()
        raw_text: str = entities.get("_raw_text", "").strip()
        
        combined_text = (command + " " + raw_text).lower()

        # 1. Comprobar si se solicita la cancelación de un apagado
        if any(k in combined_text for k in ["cancela", "cancelar"]) and any(k in combined_text for k in ["apaga", "apagado"]):
            if self.cancel_shutdown():
                msg = "El apagado programado ha sido cancelado."
                logger.info(msg)
                try:
                    from core import tts
                    tts.say(msg)
                except Exception:
                    pass
            else:
                msg = "No hay ningún apagado programado en este momento."
                logger.warning(msg)
                try:
                    from core import tts
                    tts.say(msg)
                except Exception:
                    pass
            return True

        # 2. Comprobar si se solicita un apagado programado diferido
        shutdown_info = self._parse_deferred_shutdown(combined_text)
        if shutdown_info:
            self.schedule_shutdown(
                seconds=shutdown_info["delay_seconds"],
                qty=shutdown_info["quantity"],
                unit_label=shutdown_info["unit"]
            )
            return True

        # 3. Comandos normales (ejecutar aplicaciones normales de la whitelist)
        if not self.validate_entities(entities):
            return False

        if not self._is_safe_command(command):
            logger.error(f"Ejecución abortada por política de seguridad: '{command}'")
            return False

        try:
            # shlex.split tokeniza el string respetando comillas y escapes
            args = shlex.split(command)

            # ── EL TRUCO PARA APPS DE TERMINAL (TUI) ──
            terminal_apps = ["cliamp"]
            if args[0] in terminal_apps:
                logger.info(f"Spawneando nueva ventana de Alacritty para TUI: {args[0]}")
                args = ["alacritty", "-e"] + args
            else:
                logger.info(f"Lanzando aplicación gráfica en segundo plano: {args}")

            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        except FileNotFoundError:
            logger.error(
                f"El programa '{command}' no se encontró en el sistema. "
                f"¿Está instalado y en el PATH?"
            )
            return False

        except PermissionError:
            logger.error(
                f"Permiso denegado al intentar ejecutar '{command}'."
            )
            return False

        except Exception as e:
            logger.error(f"Error inesperado al lanzar el proceso '{command}': {e}")
            return False