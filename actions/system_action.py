import subprocess
import logging
import shlex
from typing import Dict, Any, Set, List

from .base_action import ActionModule

# Logger dedicado al módulo de acciones del sistema
logger = logging.getLogger(__name__)


class SystemActionModule(ActionModule):
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

    def execute(self, entities: Dict[str, Any]) -> bool:
        if not self.validate_entities(entities):
            return False

        command: str = entities["programa"].strip()

        if not self._is_safe_command(command):
            logger.error(f"Ejecución abortada por política de seguridad: '{command}'")
            return False

        try:
            # shlex.split tokeniza el string respetando comillas y escapes
            args = shlex.split(command)

            # ── EL TRUCO PARA APPS DE TERMINAL (TUI) ──
            # Si el programa base es cliamp (o cualquier otra app de terminal pura),
            # lo envolvemos dinámicamente adentro de Alacritty.
            # Nota: Esto se hace DESPUÉS de validar la seguridad, por lo que 
            # la whitelist se sigue respetando perfectamente.
            terminal_apps = ["cliamp"] # Podés sumar "htop", "btop", etc. en el futuro
            
            if args[0] in terminal_apps:
                logger.info(f"Spawneando nueva ventana de Alacritty para TUI: {args[0]}")
                # Reconstruimos los argumentos: alacritty -e cliamp [args...]
                args = ["alacritty", "-e"] + args
            else:
                logger.info(f"Lanzando aplicación gráfica en segundo plano: {args}")

            # Lanzamos el proceso silenciando TODAS las salidas para que ninguna app 
            # (tenga interfaz o no) ensucie la consola padre de Viernes.
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