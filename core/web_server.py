import os
import sys
import socket
import subprocess
import logging
import threading
import json
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Configuración de logging
logger = logging.getLogger("ViernesWebServer")

from .utils import get_pc_volume, set_pc_volume

app = FastAPI(title="Viernes Web Remote Control")

# Guardar certificados en .kiro/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
KIRO_DIR = os.path.join(BASE_DIR, ".kiro")
CERT_PATH = os.path.join(KIRO_DIR, "cert.pem")
KEY_PATH = os.path.join(KIRO_DIR, "key.pem")

def get_asset_dir(name: str) -> Optional[str]:
    """Devuelve el directorio de assets si existe (core/ o raíz del proyecto)."""
    candidates = [
        os.path.join(BASE_DIR, name),
        os.path.join(PROJECT_ROOT, name),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None

# Referencia global al asistente de Viernes
assistant_instance = None
active_mic_source = "pc"  # "pc" o "mobile"
uvicorn_loop = None

# Manager para conexiones de WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Enviar el estado actual al conectarse
        if assistant_instance:
            current_state = getattr(assistant_instance.listener, "current_state", "IDLE")
            await websocket.send_json({"type": "state", "state": current_state})
        # Enviar el volumen de la PC actual al conectar
        try:
            vol = get_pc_volume()
            await websocket.send_json({"type": "volume", "value": vol})
        except Exception:
            pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

def generate_self_signed_cert():
    """Genera certificados SSL autofirmados en el directorio .kiro si no existen."""
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        logger.info("Certificados SSL existentes detectados.")
        return

    logger.info("Generando certificados SSL autofirmados para acceso local HTTPS...")
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        if not os.path.exists(KIRO_DIR):
            os.makedirs(KIRO_DIR, exist_ok=True)

        # Generar clave privada
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Generar certificado
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"AR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Buenos Aires"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"Viernes"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Viernes Assistant"),
            x509.NameAttribute(NameOID.COMMON_NAME, u"viernes.local"),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow() - timedelta(days=1)
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
            critical=False,
        ).sign(key, hashes.SHA256())

        # Guardar clave y certificado
        with open(CERT_PATH, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(KEY_PATH, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        logger.info("Certificados SSL autofirmados creados exitosamente.")
    except Exception as e:
        logger.error(f"Error al generar certificados SSL: {e}. Se intentará correr sin SSL.")

# Callback para enviar el estado del asistente a los clientes conectados
def web_state_callback(state: str):
    import asyncio
    global uvicorn_loop
    if uvicorn_loop and uvicorn_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "state", "state": state}),
            uvicorn_loop
        )
    else:
        logger.warning("[WebServer] El event loop de Uvicorn no está disponible en web_state_callback.")

@app.get("/")
async def get_index():
    static_dir = get_asset_dir("static")
    if static_dir:
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    return {"message": "Viernes Web Remote Control is running. HTML client not found."}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global active_mic_source
    await manager.connect(websocket)
    audio_buffer = bytearray()
    recording_active = False

    try:
        while True:
            # WebSocket puede recibir texto (comandos) o binario (audio PCM)
            message = await websocket.receive()
            
            # Control de desconexión ASGI Starlette
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
            
            if "bytes" in message:
                # Datos de audio binarios (PCM 16kHz)
                if recording_active:
                    audio_buffer.extend(message["bytes"])
                else:
                    if active_mic_source == "mobile" and assistant_instance:
                        assistant_instance.listener.remote_audio_queue.put(message["bytes"])
            
            elif "text" in message:
                data = json.loads(message["text"])
                event_type = data.get("event")

                if event_type == "start_recording":
                    logger.info("Recibiendo audio remoto del iPhone...")
                    recording_active = True
                    audio_buffer.clear()
                    # Pausar micrófono de la PC (Opción A)
                    if assistant_instance and hasattr(assistant_instance.listener, "is_paused"):
                        assistant_instance.listener.is_paused = True
                    # Notificar estado a todos
                    if assistant_instance:
                        assistant_instance.notify_state("GRABANDO_COMANDO")

                elif event_type == "stop_recording":
                    logger.info("Fin de audio remoto. Procesando...")
                    recording_active = False
                    
                    if assistant_instance and len(audio_buffer) > 0:
                        # Procesar en un hilo separado para no bloquear el WebSocket
                        threading.Thread(
                            target=process_remote_audio,
                            args=(bytes(audio_buffer),),
                            daemon=True
                        ).start()
                    else:
                        if assistant_instance:
                            if hasattr(assistant_instance.listener, "is_paused"):
                                assistant_instance.listener.is_paused = (active_mic_source == "mobile")
                            assistant_instance.notify_state("ESCUCHANDO_WAKE")

                elif event_type == "command":
                    # Comandos de teclado rápidos (Volumen, Pausa, Cine, etc.)
                    cmd_name = data.get("command")
                    logger.info(f"Comando remoto recibido: '{cmd_name}'")
                    if assistant_instance:
                        # Ejecutar macro
                        threading.Thread(
                            target=execute_remote_macro,
                            args=(cmd_name,),
                            daemon=True
                        ).start()

                elif event_type == "volume":
                    vol_val = data.get("value", 50)
                    if assistant_instance:
                        # Ajustar volumen absoluto en Linux
                        threading.Thread(
                            target=set_pc_volume,
                            args=(vol_val,),
                            daemon=True
                        ).start()

                elif event_type == "media_control":
                    action = data.get("action")
                    if action in ["play-pause", "next", "previous"]:
                        logger.info(f"Comando multimedia remoto recibido: {action}")
                        try:
                            subprocess.run(["playerctl", action], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except Exception as e:
                            logger.error(f"Error al ejecutar playerctl {action}: {e}")

                elif event_type == "set_mic_source":
                    source = data.get("source", "pc")
                    logger.info(f"Cambiando micrófono activo a: '{source}'")
                    active_mic_source = source
                    if assistant_instance:
                        if hasattr(assistant_instance.listener, "is_paused"):
                            assistant_instance.listener.is_paused = (source == "mobile")
                        assistant_instance.notify_state("ESCUCHANDO_WAKE")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Cliente WebSocket desconectado.")
        # Si no quedan conexiones activas, restablecer automáticamente al micrófono de la PC
        if len(manager.active_connections) == 0:
            logger.info("No quedan clientes activos conectados. Restableciendo al micrófono de la PC...")
            active_mic_source = "pc"
            if assistant_instance:
                if hasattr(assistant_instance.listener, "is_paused"):
                    assistant_instance.listener.is_paused = False
                assistant_instance.notify_state("ESCUCHANDO_WAKE")

def get_system_media_state() -> dict:
    """Obtiene el estado actual de reproducción usando playerctl de forma eficiente."""
    try:
        res = subprocess.run(
            ["playerctl", "metadata", "-f", "{{status}};{{title}};{{artist}};{{mpris:length}};{{position}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if res.returncode == 0:
            parts = res.stdout.strip().split(";")
            if len(parts) >= 5:
                status = parts[0]
                title = parts[1]
                artist = parts[2]
                duration_us = parts[3]
                position_s = parts[4]
                
                try:
                    duration = float(duration_us) / 1000000.0 if duration_us else 0.0
                except ValueError:
                    duration = 0.0
                    
                try:
                    position = float(position_s) / 1000000.0 if position_s else 0.0
                except ValueError:
                    position = 0.0
                
                return {
                    "active": True,
                    "status": status,
                    "title": title if title else "Desconocido",
                    "artist": artist if artist else "Desconocido",
                    "duration": duration,
                    "position": position
                }
        return {"active": False}
    except Exception:
        return {"active": False}
# set_pc_volume se importa desde .utils

def execute_remote_macro(macro_name: str):
    """Busca y ejecuta una macro a través del dispatcher de Viernes."""
    try:
        intent_json = {
            "intent": "automatizacion_teclado",
            "entities": {"macro": macro_name, "_raw_text": f"ejecutar {macro_name}"}
        }
        # Evitar reproducir pitido en la PC si viene del móvil
        if hasattr(assistant_instance.dispatcher, "suppress_beep"):
            assistant_instance.dispatcher.suppress_beep = True
        
        assistant_instance.dispatcher.dispatch(intent_json)
    except Exception as e:
        logger.error(f"Error al ejecutar macro remota '{macro_name}': {e}")
    finally:
        if hasattr(assistant_instance.dispatcher, "suppress_beep"):
            assistant_instance.dispatcher.suppress_beep = False

def process_remote_audio(audio_bytes: bytes):
    """Procesa el audio recibido por la red usando Whisper, parsea la intención y la ejecuta."""
    try:
        assistant_instance.notify_state("PROCESANDO")
        
        # Convertir bytes (16-bit PCM) a array float32 normalizado
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        logger.info("Transcribiendo comando remoto con Whisper...")
        segments, info = assistant_instance.listener.whisper.transcribe(audio_data, language="es")
        text = " ".join([segment.text for segment in segments]).strip()
        
        if text:
            logger.info(f"Transcripción remota exitosa: '{text}'")
            
            # Decir confirmación y ejecutar
            from . import tts
            try:
                commands = assistant_instance.parser.parse(text)
                if isinstance(commands, dict):
                    commands = [commands]
            except Exception as e:
                logger.error(f"Error al parsear el comando remoto '{text}': {e}")
                commands = [{"intent": "error", "entities": {}}]
            
            # Confirmación de voz (TTS) en PC
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
                        pass
                    else:
                        tts.say("Entendido jefe")

            # Ejecutar acciones (evitando el pitido en la PC)
            if hasattr(assistant_instance.dispatcher, "suppress_beep"):
                assistant_instance.dispatcher.suppress_beep = True
            try:
                import time
                for idx, cmd in enumerate(commands):
                    if idx > 0:
                        prev_intent = commands[idx-1].get("intent")
                        if prev_intent in ["reproducir_youtube", "abrir_aplicacion", "abrir_navegador", "lanzar_juego"]:
                            logger.info("[WebRemote] Pausando 2.5 segundos para permitir la carga de la acción anterior...")
                            time.sleep(2.5)
                        else:
                            time.sleep(0.5)
                    assistant_instance.dispatcher.dispatch(cmd)
            finally:
                if hasattr(assistant_instance.dispatcher, "suppress_beep"):
                    assistant_instance.dispatcher.suppress_beep = False
        else:
            logger.warning("No se detectó audio comprensible en el comando remoto.")
            
    except Exception as e:
        logger.error(f"Error procesando audio remoto: {e}")
    finally:
        if assistant_instance:
            if active_mic_source == "pc":
                if hasattr(assistant_instance.listener, "is_paused"):
                    assistant_instance.listener.is_paused = False
            else:
                if hasattr(assistant_instance.listener, "is_paused"):
                    assistant_instance.listener.is_paused = True
            assistant_instance.notify_state("ESCUCHANDO_WAKE")

def get_lan_ip() -> str:
    """Retorna la dirección IP local de la PC en la red LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # No necesita conectarse realmente
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
# get_pc_volume se importa desde .utils

import asyncio

@app.on_event("startup")
async def startup_event():
    global uvicorn_loop
    uvicorn_loop = asyncio.get_running_loop()
    # Iniciar loops de polling en segundo plano
    asyncio.create_task(poll_volume_loop())
    asyncio.create_task(poll_media_loop())

async def poll_volume_loop():
    logger.info("Iniciando loop de polling de volumen del sistema...")
    last_vol = -1
    while True:
        await asyncio.sleep(1.0)
        try:
            vol = get_pc_volume()
            if vol != last_vol:
                last_vol = vol
                # Enviar el cambio de volumen a todos los dispositivos conectados
                await manager.broadcast({"type": "volume", "value": vol})
        except Exception as e:
            logger.error(f"Error en loop de polling de volumen: {e}")

async def poll_media_loop():
    logger.info("Iniciando loop de polling de estado multimedia (playerctl)...")
    last_media = {}
    while True:
        await asyncio.sleep(1.0)
        try:
            media = get_system_media_state()
            # Always broadcast if active (to update position), skip only if both inactive
            if media == last_media and not media.get("active", False):
                continue
            last_media = media
            await manager.broadcast({"type": "media_update", "media": media})
        except Exception as e:
            logger.error(f"Error en loop de polling multimedia: {e}")

def run_server(assistant, port=8000):
    """Inicia el servidor Uvicorn en un hilo separado."""
    global assistant_instance
    assistant_instance = assistant
    
    # Registrar el callback del servidor web para recibir cambios de estado
    if hasattr(assistant, "callbacks"):
        assistant.callbacks.append(web_state_callback)
    
    generate_self_signed_cert()
    
    # Configurar static files si el directorio existe
    static_dir = get_asset_dir("static")
    if static_dir:
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Configurar sounds directory
    sounds_dir = get_asset_dir("sounds")
    if sounds_dir:
        app.mount("/sounds", StaticFiles(directory=sounds_dir), name="sounds")

    # Iniciar uvicorn con SSL si los archivos existen
    use_ssl = os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH)
    ssl_key = KEY_PATH if use_ssl else None
    ssl_cert = CERT_PATH if use_ssl else None
    
    lan_ip = get_lan_ip()
    protocol = "https" if use_ssl else "http"
    logger.info(f"Iniciando Servidor Web Viernes en: {protocol}://{lan_ip}:{port}")
    
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=port, 
        ssl_keyfile=ssl_key, 
        ssl_certfile=ssl_cert,
        log_level="warning"
    )
    server = uvicorn.Server(config)
    server.run()
