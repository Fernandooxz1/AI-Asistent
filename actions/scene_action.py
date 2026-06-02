import subprocess
import logging
import shlex
import time
import importlib
from typing import Dict, Any, Optional, List
import psutil

from .base_action import ActionModule

logger = logging.getLogger(__name__)


class SceneActionModule(ActionModule):
    """
    Módulo de acción para la ejecución dinámica de escenarios y perfiles del sistema.
    Permite cerrar procesos, abrir aplicaciones en workspaces específicos de Hyprland,
    ejecutar macros de teclado, ajustar el volumen del sistema, reproducir en YouTube
    e iniciar un temporizador de Pomodoro de forma automática.
    """

    def validate_entities(self, entities: Dict[str, Any]) -> bool:
        """
        Valida que la entidad 'escenario' esté presente y corresponda a un escenario
        configurado en config.json.
        """
        escenario = entities.get("escenario")
        if not escenario:
            logger.warning("Entidad 'escenario' ausente o vacía.")
            return False

        if not isinstance(escenario, str):
            logger.warning(f"Entidad 'escenario' tiene tipo inválido: {type(escenario)}")
            return False

        # Comprobar contra los escenarios configurados en config.json
        scenes = self.config.get("scenes", {})
        escenario_lower = escenario.lower().strip()
        
        matched_scene = None
        for scene_name in scenes.keys():
            if scene_name.lower() == escenario_lower:
                matched_scene = scene_name
                break

        if not matched_scene:
            logger.warning(f"Escenario '{escenario}' no encontrado en la configuración.")
            return False

        # Estandarizar la entidad con la grafía exacta de la configuración
        entities["escenario"] = matched_scene
        return True

    def _get_workspace_for_app(self, app_cmd: str) -> Optional[int]:
        """
        Determina dinámicamente en qué workspace de Hyprland debe lanzarse
        una aplicación en base al contenido de su comando.
        """
        app_cmd_lower = app_cmd.lower()
        if "notebooklm.google.com" in app_cmd_lower:
            return 1
        elif "gemini.google.com" in app_cmd_lower:
            return 2
        elif "agy" in app_cmd_lower:
            return 1
        elif "youtube.com" in app_cmd_lower:
            return 9
        return None

    def execute(self, entities: Dict[str, Any]) -> bool:
        """
        Ejecuta todas las acciones asociadas al escenario seleccionado.
        """
        if not self.validate_entities(entities):
            return False

        escenario_name = entities["escenario"]
        scene_config = self.config.get("scenes", {}).get(escenario_name, {})
        logger.info(f"Iniciando activación del escenario: '{escenario_name}'")

        # ── 1. CERRAR PROCESOS (close_processes) ──
        close_processes = scene_config.get("close_processes", [])
        if close_processes:
            logger.info(f"Cerrando procesos de la lista negra: {close_processes}")
            close_set = {p.lower() for p in close_processes}
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pname = proc.info['name']
                    if pname:
                        pname_lower = pname.lower()
                        # Hacemos coincidencia exacta o por prefijo común para seguridad
                        if pname_lower in close_set or any(pname_lower.startswith(target) for target in close_set):
                            logger.info(f"Terminando de forma limpia '{pname}' (PID: {proc.info['pid']})")
                            proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

        # ── 2. ESTABLECER VOLUMEN (volume_level) ──
        volume_level = scene_config.get("volume_level")
        if volume_level is not None:
            try:
                from core.utils import set_pc_volume
                logger.info(f"Ajustando volumen del sistema a {volume_level}%")
                set_pc_volume(int(volume_level))
            except Exception as e:
                logger.error(f"Error al ajustar el volumen del sistema a {volume_level}: {e}")

        # ── 3. EJECUTAR COMANDOS DE SISTEMA (system_commands) ──
        system_commands = scene_config.get("system_commands", [])
        if system_commands:
            logger.info("Ejecutando comandos del sistema...")
            for cmd in system_commands:
                try:
                    logger.info(f"Comando: '{cmd}'")
                    # Ejecutar comandos secuenciales de forma síncrona
                    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:
                    logger.error(f"Error al ejecutar el comando del sistema '{cmd}': {e}")

        # ── 4. ABRIR APLICACIONES (open_apps) Y ENRUTAR WORKSPACES ──
        open_apps = scene_config.get("open_apps", [])
        target_workspaces = []
        if open_apps:
            logger.info("Abriendo aplicaciones configuradas...")
            for app in open_apps:
                try:
                    workspace = self._get_workspace_for_app(app)
                    if workspace is not None:
                        target_workspaces.append(workspace)
                        # Intentar lanzar nativamente en el workspace con reglas vía Hyprland-Lua
                        lua_cmd = f'hl.dsp.exec_cmd("[workspace {workspace} silent] {app}")'
                        logger.info(f"Intentando abrir '{app}' en workspace {workspace} vía Lua: {lua_cmd}")
                        res = subprocess.run(["hyprctl", "dispatch", lua_cmd], capture_output=True, text=True)
                        if res.returncode == 0 and "error" not in res.stdout.lower():
                            logger.info(f"Aplicación '{app}' lanzada exitosamente en workspace {workspace} vía Lua.")
                            time.sleep(0.1)
                            continue
                        else:
                            logger.warning(f"Fallo al abrir vía Lua ({res.stdout.strip()}). Usando fallback...")
                            
                            # Fallback 1: Intentar cambiar de workspace con Lua antes de lanzar
                            ws_cmd = f'hl.dsp.focus({{ workspace = "{workspace}" }})'
                            res_ws = subprocess.run(["hyprctl", "dispatch", ws_cmd], capture_output=True, text=True)
                            if res_ws.returncode != 0 or "error" in res_ws.stdout.lower():
                                # Fallback 2: Cambiar de workspace estándar
                                subprocess.run(["hyprctl", "dispatch", "workspace", str(workspace)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            time.sleep(0.2)

                    logger.info(f"Lanzando aplicación en segundo plano: {app}")
                    args = shlex.split(app)
                    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(0.1)  # Pequeño delay de espaciado secuencial
                except Exception as e:
                    logger.error(f"Error al abrir la aplicación '{app}': {e}")

        # ── 5. EJECUTAR MACROS (macros) ──
        macros = scene_config.get("macros", [])
        if macros:
            logger.info("Ejecutando macros de teclado...")
            try:
                from actions.keyboard_automation_action import KeyboardAutomationModule
                keyboard_module = KeyboardAutomationModule(config=self.config)
                for macro in macros:
                    logger.info(f"Macro: '{macro}'")
                    if macro in self.config.get("keyboard_macros", {}):
                        keyboard_module.execute({"macro": macro})
                    else:
                        # Si no existe en la config, ejecutarla directamente como string macro
                        keyboard_module._execute_string_macro(macro)
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error al ejecutar macros de teclado: {e}")

        # ── 6. REPRODUCIR YOUTUBE (youtube_play) ──
        youtube_play = scene_config.get("youtube_play")
        if youtube_play:
            logger.info(f"Iniciando reproducción de YouTube para: '{youtube_play}'")
            try:
                from actions.youtube_play_action import YoutubePlayActionModule
                yt_module = YoutubePlayActionModule(config=self.config)
                yt_module.execute({"busqueda": youtube_play})
            except Exception as e:
                logger.error(f"Error al iniciar reproducción de YouTube para '{youtube_play}': {e}")

        # ── 7. TEMPORIZADOR DE POMODORO (pomodoro) ──
        if scene_config.get("pomodoro") or scene_config.get("pomodoro_enabled"):
            logger.info("Tratando de iniciar Pomodoro...")
            try:
                if hasattr(self, "assistant") and self.assistant and hasattr(self.assistant, "pomodoro"):
                    logger.info("Iniciando Pomodoro directamente a través del asistente.")
                    self.assistant.pomodoro.start()
                else:
                    logger.info("Iniciando Pomodoro de forma dinámica (modo test/fallback)...")
                    pomodoro_module = None
                    pomodoro_class = None
                    for mod_name in ["actions.pomodoro_action", "actions.pomodoro"]:
                        try:
                            pomodoro_module = importlib.import_module(mod_name)
                            break
                        except ImportError:
                            continue
                    if pomodoro_module:
                        for cls_name in ["PomodoroActionModule", "PomodoroModule"]:
                            if hasattr(pomodoro_module, cls_name):
                                pomodoro_class = getattr(pomodoro_module, cls_name)
                                break
                    if pomodoro_class:
                        logger.info("Instanciando y ejecutando módulo de Pomodoro...")
                        pomo_instance = pomodoro_class(config=self.config)
                        pomo_instance.execute({})
                    else:
                        logger.warning("Pomodoro habilitado pero no se encontró la clase de acción de Pomodoro o la referencia del asistente.")
            except Exception as e:
                logger.error(f"Error al iniciar el Pomodoro: {e}")

        # ── 8. ENFOCAR WORKSPACE PRINCIPAL AL FINALIZAR ──
        if target_workspaces:
            primary_ws = target_workspaces[0]
            logger.info(f"Enfocando workspace principal al finalizar: {primary_ws}")
            # Intentar enfocar con Lua primero
            ws_cmd = f'hl.dsp.focus({{ workspace = "{primary_ws}" }})'
            res = subprocess.run(["hyprctl", "dispatch", ws_cmd], capture_output=True, text=True)
            if res.returncode != 0 or "error" in res.stdout.lower():
                # Fallback estándar
                subprocess.run(["hyprctl", "dispatch", "workspace", str(primary_ws)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logger.info(f"Escenario '{escenario_name}' activado con éxito.")
        return True
