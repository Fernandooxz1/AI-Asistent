import os
import sys
import json
import logging
from typing import Optional
from dotenv import load_dotenv

from audio_listener import AudioListener
from intent_parser import IntentParser
from dispatcher import Dispatcher

# ─── Configuración global de logging ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("Kiro")


class KiroAssistant:
    """
    Orquestador principal del asistente de voz Kiro.

    Coordina el ciclo de vida completo de cada interacción:
        AudioListener → wake word → record_command
        → IntentParser → Dispatcher → ActionModule

    El diseño es resiliente: cualquier fallo en un módulo de acción individual
    es capturado en el bucle principal para que el asistente retome la escucha
    sin crashear.
    """

    def __init__(self, config_path: str = "config.json", state_callback=None) -> None:
        """
        Inicializa todos los subsistemas de Kiro.

        Pasos:
        1. Carga las variables de entorno desde .env.
        2. Valida que GEMINI_API_KEY esté definida.
        3. Lee y parsea el archivo de configuración JSON.
        4. Instancia AudioListener, IntentParser y Dispatcher.

        Args:
            config_path:    Ruta al archivo de configuración JSON.
            state_callback: Función opcional que recibe strings de estado del listener.
                            Se pasa directamente a AudioListener para notificar cambios
                            de fase a la GUI de forma desacoplada.

        Raises:
            ValueError: Si GEMINI_API_KEY no está definida en el entorno.
            FileNotFoundError: Si el archivo de configuración no existe.
            json.JSONDecodeError: Si el archivo de configuración no es JSON válido.
        """
        # 0. Calcular ruta base real (Soporte para PyInstaller --onefile)
        # Si el script está congelado (binario), usamos la ruta del ejecutable.
        # Si no, usamos la ruta del archivo .py actual.
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
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
        self.listener   = AudioListener(config, state_callback=state_callback)
        self.parser     = IntentParser(config=config)
        self.dispatcher = Dispatcher(config=config)

        logger.info("Todos los subsistemas iniciados correctamente.")

    def run(self, stop_event: Optional["threading.Event"] = None) -> None:
        """
        Bucle principal de ejecución del asistente.

        Ciclo:
            1. Espera la wake word de forma bloqueante.
            2. Graba el comando del usuario.
            3. Parsea el texto con Gemini para obtener intent + entities.
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
                intent_json: dict = self.parser.parse(comando)

                # ── Paso 4: Mostrar resultado del parser ───────────────────
                intent   = intent_json.get("intent", "desconocido")
                entities = intent_json.get("entities", {})
                print()
                print(f"  🧠 Intent detectado : {intent}")
                print(f"  📦 Entidades        : {entities}")
                print()

                # ── Paso 5: Despachar al módulo de acción ─────────────────
                try:
                    self.dispatcher.dispatch(intent_json)
                except Exception as e:
                    logger.error(f"Error en el módulo de acción para '{intent}': {e}")

        except KeyboardInterrupt:
            print()
            print("👋 Kiro apagado. ¡Hasta la próxima!")
            print()

        logger.info("Bucle del asistente finalizado.")


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        assistant = KiroAssistant()
        assistant.run()
    except (ValueError, FileNotFoundError) as e:
        # Errores de configuración al iniciar: se muestran limpiamente sin traceback
        print(f"\n❌ Error de inicialización: {e}\n")
    except Exception as e:
        logger.critical(f"Error fatal inesperado al iniciar Kiro: {e}", exc_info=True)
