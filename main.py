import os
import sys
import json
import logging
import time
import subprocess
import threading
from typing import Optional
from dotenv import load_dotenv


from core.audio_listener import AudioListener
from core.intent_parser import IntentParser
from core.dispatcher import Dispatcher
from core import tts


# ─── Configuración global de logging ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Viernes")


class ViernesAssistant:
    """
    Orquestador principal del asistente de voz Viernes.

    Coordina el ciclo de vida completo de cada interacción:
        AudioListener → wake word → record_command
        → IntentParser → Dispatcher → ActionModule

    El diseño es resiliente: cualquier fallo en un módulo de acción individual
    es capturado en el bucle principal para que el asistente retome la escucha
    sin crashear.
    """

    def __init__(self, config_path: str = "config.json", state_callback=None) -> None:
        """
        Inicializa todos los subsistemas de Viernes.

        Pasos:
        1. Carga las variables de entorno desde .env.
        2. Lee y parsea el archivo de configuración JSON.
        3. Instancia AudioListener, IntentParser y Dispatcher.

        Args:
            config_path:    Ruta al archivo de configuración JSON.
            state_callback: Función opcional que recibe strings de estado del listener.
                            Se pasa directamente a AudioListener para notificar cambios
                            de fase a la GUI de forma desacoplada.

        Raises:
            FileNotFoundError: Si el archivo de configuración no existe.
            json.JSONDecodeError: Si el archivo de configuración no es JSON válido.
        """
        # 0. Calcular ruta base real (Soporte para PyInstaller --onefile)
        # Si el script está congelado (binario), usamos la ruta del ejecutable.
        # Si no, usamos la ruta del archivo .py actual.
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(os.path.realpath(sys.executable))
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        # 1. Cargar variables de entorno desde .env usando ruta absoluta
        env_path = os.path.join(base_path, ".env")
        load_dotenv(dotenv_path=env_path)


        # 3. Leer configuración desde disco (asegurar ruta absoluta)
        if not os.path.isabs(config_path):
            config_path = os.path.join(base_path, config_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"No se encontró el archivo de configuración en: '{config_path}'"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            config: dict = json.load(f)

        logger.info(f"Configuración cargada desde '{config_path}'")

        # 3. Instanciar subsistemas
        self.callbacks = []
        if state_callback:
            self.callbacks.append(state_callback)

        self.listener   = AudioListener(config, state_callback=self.notify_state)
        self.parser     = IntentParser(config=config)
        self.dispatcher = Dispatcher(config=config)

        # Iniciar servidor web de control remoto
        self._start_web_server()

        # 4. Verificar e iniciar Ollama de forma automática si no está corriendo
        self.ollama_process = None
        if self._check_ollama_running():
            logger.info("Ollama ya está corriendo en el puerto 11434.")
        else:
            logger.info("Ollama no está corriendo. Iniciando servicio local de Ollama...")
            try:
                self.ollama_process = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                # Esperar hasta 3 segundos a que responda el puerto
                for _ in range(6):
                    time.sleep(0.5)
                    if self._check_ollama_running():
                        logger.info("Servicio local de Ollama iniciado con éxito.")
                        break
                else:
                    logger.warning("El servicio local de Ollama tardó demasiado en responder.")
            except Exception as e:
                logger.error(f"No se pudo iniciar Ollama automáticamente: {e}")

        logger.info("Todos los subsistemas iniciados correctamente.")


    def _check_ollama_running(self) -> bool:
        """Verifica si el servicio de Ollama responde en el puerto por defecto 11434."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("127.0.0.1", 11434))
                return True
        except (socket.error, ConnectionRefusedError):
            return False

    def notify_state(self, state: str) -> None:
        """Notifica el cambio de estado a todos los callbacks registrados."""
        if hasattr(self, "listener"):
            self.listener.current_state = state
        for cb in self.callbacks:
            try:
                cb(state)
            except Exception as e:
                logger.error(f"Error en callback de estado remoto: {e}")

    def _start_web_server(self) -> None:
        """Inicia el servidor FastAPI en un hilo separado para control remoto LAN."""
        try:
            import core.web_server as web_server
            web_thread = threading.Thread(
                target=web_server.run_server,
                args=(self,),
                daemon=True,
                name="ViernesWebServer"
            )
            web_thread.start()
            logger.info("Servidor web de control remoto (FastAPI/WebSockets) iniciado exitosamente.")
        except Exception as e:
            logger.error(f"Error al iniciar servidor web de control remoto: {e}")

    def run(self, stop_event: Optional["threading.Event"] = None) -> None:

        """
        Bucle principal de ejecución del asistente.

        Ciclo:
            1. Espera la wake word de forma bloqueante.
            2. Graba el comando del usuario.
            3. Parsea el texto con Ollama para obtener intent + entities.
            4. Loguea la intención detectada para trazabilidad.
            5. Despacha el intent al módulo de acción correspondiente.
            6. Vuelve al paso 1.

        Args:
            stop_event: threading.Event opcional. Cuando se hace set(), el bucle
                        termina ordenadamente al final del ciclo actual. Si es None,
                        el asistente corre hasta Ctrl+C (modo consola).
        """
        try:
            while True:
                # Chequear señal de parada (para integración con GUI)
                if stop_event and stop_event.is_set():
                    break

                # ── Paso 1: Detectar wake word ─────────────────────────────
                detected = self.listener.wait_for_wake_word()

                if not detected:
                    logger.warning("No se pudo acceder al micrófono. Reintentando...")
                    continue

                if stop_event and stop_event.is_set():
                    break

                # ── Paso 2: Grabar el comando ──────────────────────────────
                comando: Optional[str] = self.listener.record_command()

                if not comando:
                    logger.info("No se capturó ningún comando. Volviendo a escuchar.")
                    continue

                # ── Paso 3: Parsear la intención ───────────────────────────
                logger.info(f"Procesando comando: '{comando}'")
                try:
                    commands = self.parser.parse(comando)
                    if isinstance(commands, dict):
                        commands = [commands]
                except Exception as e:
                    logger.error(f"Error al parsear el comando '{comando}': {e}")
                    commands = [{"intent": "error", "entities": {}}]

                # ── Paso 4: Confirmación de voz (TTS) única ──────────────────────
                if len(commands) > 1:
                    tts.say("Entendido jefe, ejecutando secuencia")
                else:
                    cmd = commands[0]
                    intent = cmd.get("intent", "desconocido")
                    entities = cmd.get("entities", {})
                    if intent in ["desconocido", "error"]:
                        tts.say("No te entendí jefe, ¿podrías repetirlo?")
                    else:
                        if intent == "abrir_aplicacion":
                            programa = entities.get("programa", "")
                            tts.say(f"Entendido jefe, abriendo {programa}")
                        elif intent == "abrir_navegador":
                            plataforma = entities.get("plataforma", "")
                            tts.say(f"Entendido jefe, abriendo {plataforma}")
                        elif intent == "reproducir_youtube":
                            busqueda = entities.get("busqueda", "")
                            tts.say(f"Entendido jefe, buscando {busqueda} en youtube")
                        elif intent == "lanzar_juego":
                            juego = entities.get("juego", "")
                            tts.say(f"Entendido jefe, lanzando {juego}")
                        elif intent == "automatizacion_teclado":
                            tts.say("Ejecutando macro, jefe")
                        elif intent == "conversar":
                            pass  # El módulo ConversationalModule reproduce la respuesta directamente
                        else:
                            tts.say("Entendido jefe")

                # ── Paso 5: Despachar secuencialmente a los módulos de acción ───────
                for idx, cmd in enumerate(commands):
                    intent = cmd.get("intent", "desconocido")
                    entities = cmd.get("entities", {})
                    
                    print()
                    print(f"  🧠 Intent detectado ({idx+1}/{len(commands)}): {intent}")
                    print(f"  📦 Entidades        : {entities}")
                    print()
                    
                    if intent in ["desconocido", "error"]:
                        continue

                    # Pausa inteligente entre comandos
                    if idx > 0:
                        prev_intent = commands[idx-1].get("intent")
                        # Si el comando anterior fue abrir algo o reproducir youtube, pausamos 2.5 segundos para dar tiempo a la carga
                        if prev_intent in ["reproducir_youtube", "abrir_aplicacion", "abrir_navegador", "lanzar_juego"]:
                            logger.info("Pausando 2.5 segundos para permitir la carga de la acción anterior...")
                            time.sleep(2.5)
                        else:
                            time.sleep(0.5)
                            
                    try:
                        self.dispatcher.dispatch(cmd)
                    except Exception as e:
                        logger.error(f"Error en el módulo de acción para '{intent}': {e}")

        except KeyboardInterrupt:
            print()
            print("👋 Viernes apagado. ¡Hasta la próxima!")
            print()
        finally:
            if hasattr(self, "listener") and getattr(self.listener, "original_volume", None) is not None:
                try:
                    from core.utils import set_pc_volume
                    set_pc_volume(self.listener.original_volume)
                    logger.info("Volumen del sistema restaurado al apagar el asistente.")
                except Exception:
                    pass
            if self.ollama_process:
                logger.info("Deteniendo el servicio local de Ollama...")
                try:
                    self.ollama_process.terminate()
                    self.ollama_process.wait(timeout=2)
                except Exception as e:
                    logger.error(f"Error al detener Ollama: {e}")
            logger.info("Bucle del asistente finalizado.")



# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        assistant = ViernesAssistant()
        assistant.run()
    except (ValueError, FileNotFoundError) as e:
        # Errores de configuración al iniciar: se muestran limpiamente sin traceback
        print(f"\n❌ Error de inicialización: {e}\n")
    except Exception as e:
        logger.critical(f"Error fatal inesperado al iniciar Viernes: {e}", exc_info=True)
