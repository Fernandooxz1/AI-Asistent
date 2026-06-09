import os
import sys
import socket
import subprocess
import logging
import threading
import json
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional


import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, status, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Guardar certificados en .kiro/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
KIRO_DIR = os.path.join(BASE_DIR, ".kiro")
CERT_PATH = os.path.join(KIRO_DIR, "cert.pem")
KEY_PATH = os.path.join(KIRO_DIR, "key.pem")
JWT_KEY_PATH = os.path.join(KIRO_DIR, "jwt_private.pem")

def get_or_generate_jwt_keys():
    os.makedirs(KIRO_DIR, exist_ok=True)
    if os.path.exists(JWT_KEY_PATH):
        try:
            with open(JWT_KEY_PATH, "rb") as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
                logger.info("Clave privada JWT cargada desde disco (.kiro/jwt_private.pem)")
                return private_key, private_key.public_key()
        except Exception as e:
            logger.error(f"Error al cargar clave JWT: {e}. Regenerando...")
            
    # Generar nueva clave
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    try:
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        with open(JWT_KEY_PATH, "wb") as f:
            f.write(pem)
        logger.info("Nueva clave privada JWT generada y guardada en disco (.kiro/jwt_private.pem)")
    except Exception as e:
        logger.error(f"Error al guardar clave JWT: {e}")
        
    return private_key, private_key.public_key()

# Configuración de logging
logger = logging.getLogger("ViernesWebServer")

JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = get_or_generate_jwt_keys()

from .utils import get_pc_volume, set_pc_volume

app = FastAPI(title="Viernes Web Remote Control")

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

# Global state for background tasks
fft_processor = None
telemetry_task = None
log_handler = None
download_watcher = None
clipboard_watcher = None

last_clipboard_value = None
clipboard_lock = threading.Lock()

# Custom WebSocket Logging Handler
class WebSocketLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            if uvicorn_loop and uvicorn_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "log", "message": log_entry}),
                    uvicorn_loop
                )
        except Exception:
            pass

def start_logging_stream():
    global log_handler
    if log_handler is None:
        log_handler = WebSocketLogHandler()
        log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_handler.setFormatter(formatter)
        logging.getLogger().addHandler(log_handler)
        logger.info("Custom WebSocket logging handler registered.")

def stop_logging_stream():
    global log_handler
    if log_handler is not None:
        logging.getLogger().removeHandler(log_handler)
        log_handler = None
        logger.info("Custom WebSocket logging handler unregistered.")

# AudioFFTProcessor Control
def start_fft_processor():
    global fft_processor
    if fft_processor is None:
        from .audio_fft import AudioFFTProcessor
        def fft_callback(bins):
            if uvicorn_loop and uvicorn_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "fft", "bins": bins}),
                    uvicorn_loop
                )
        fft_processor = AudioFFTProcessor(num_bins=64, callback=fft_callback)
        fft_processor.start()
        logger.info("AudioFFTProcessor started.")

def stop_fft_processor():
    global fft_processor
    if fft_processor is not None:
        fft_processor.stop()
        fft_processor.join(timeout=2.0)
        fft_processor = None
        logger.info("AudioFFTProcessor stopped.")

# Telemetry Loop
async def telemetry_loop():
    from .telemetry import get_system_telemetry
    logger.info("Iniciando loop de telemetría de sistema...")
    while True:
        try:
            data = get_system_telemetry()
            await manager.broadcast({"type": "telemetry", "data": data})
        except Exception as e:
            logger.error(f"Error en loop de telemetría: {e}")
        await asyncio.sleep(1.5)

def start_telemetry_loop():
    global telemetry_task
    if telemetry_task is None and uvicorn_loop:
        telemetry_task = uvicorn_loop.create_task(telemetry_loop())

def stop_telemetry_loop():
    global telemetry_task
    if telemetry_task is not None:
        telemetry_task.cancel()
        telemetry_task = None
        logger.info("Loop de telemetría detenido.")

# DownloadWatcher Integration
def download_callback(filepath):
    filename = os.path.basename(filepath)
    logger.info(f"Download complete: {filename}")
    if uvicorn_loop and uvicorn_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "download_complete",
                "filename": filename,
                "path": filepath
            }),
            uvicorn_loop
        )

def start_download_watcher():
    global download_watcher
    if download_watcher is None:
        from .download_watcher import DownloadWatcher
        watch_dir = None
        if assistant_instance and hasattr(assistant_instance, "config"):
            watch_dir = assistant_instance.config.get("download_dir")
        download_watcher = DownloadWatcher(watch_dir=watch_dir, callback=download_callback)
        download_watcher.start()
        logger.info(f"DownloadWatcher started on {download_watcher.watch_dir}.")

def stop_download_watcher():
    global download_watcher
    if download_watcher is not None:
        download_watcher.stop()
        download_watcher = None
        logger.info("DownloadWatcher stopped.")

# Clipboard Integration Helpers
def get_local_clipboard() -> str:
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception as e:
        logger.error(f"Error pasting from clipboard via pyperclip: {e}")
        try:
            res = subprocess.run(["wl-paste", "-n"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return res.stdout.decode('utf-8', errors='ignore')
        except Exception as ex:
            logger.error(f"Error pasting from clipboard via wl-paste: {ex}")
            return ""

def set_local_clipboard(text: str):
    global last_clipboard_value
    with clipboard_lock:
        last_clipboard_value = text
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception as e:
            logger.error(f"Error copying to clipboard via pyperclip: {e}")
            try:
                subprocess.run(["wl-copy"], input=text.encode('utf-8'), check=True)
            except Exception as ex:
                logger.error(f"Error copying to clipboard via wl-copy: {ex}")

def handle_clipboard_change(text: str):
    global last_clipboard_value
    with clipboard_lock:
        if text == last_clipboard_value or not text:
            return
        last_clipboard_value = text
    if uvicorn_loop and uvicorn_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "clipboard", "text": text}),
            uvicorn_loop
        )

class ClipboardWatcher(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = False
        self.process = None

    def run(self):
        self.running = True
        try:
            subprocess.run(["wl-paste", "-n"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
            self.process = subprocess.Popen(
                ["wl-paste", "--watch", "echo", "CHANGED"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            logger.info("ClipboardWatcher: using reactive wl-paste --watch.")
            while self.running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break
                if "CHANGED" in line:
                    val = get_local_clipboard()
                    handle_clipboard_change(val)
        except Exception as e:
            logger.info(f"ClipboardWatcher: wl-paste --watch not available or failed ({e}). Falling back to polling.")

        # Polling fallback loop
        last_val = get_local_clipboard()
        while self.running:
            try:
                time.sleep(1.0)
                curr_val = get_local_clipboard()
                if curr_val != last_val:
                    last_val = curr_val
                    handle_clipboard_change(curr_val)
            except Exception as e:
                logger.debug(f"Error in clipboard polling: {e}")

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                pass
            self.process = None

def start_clipboard_watcher():
    global clipboard_watcher
    if clipboard_watcher is None:
        clipboard_watcher = ClipboardWatcher()
        clipboard_watcher.start()
        logger.info("ClipboardWatcher started.")

def stop_clipboard_watcher():
    global clipboard_watcher
    if clipboard_watcher is not None:
        clipboard_watcher.stop()
        clipboard_watcher = None
        logger.info("ClipboardWatcher stopped.")

# Manager para conexiones de WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        # If this is the first client, start all services
        if len(self.active_connections) == 1:
            logger.info("First client connected. Starting all background services...")
            start_fft_processor()
            start_telemetry_loop()
            start_logging_stream()
            start_download_watcher()
            start_clipboard_watcher()

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
        # Enviar el estado actual del Pomodoro al conectarse
        try:
            if assistant_instance and hasattr(assistant_instance, "pomodoro"):
                await websocket.send_json({
                    "type": "pomodoro",
                    "data": assistant_instance.pomodoro.get_status()
                })
        except Exception:
            pass
        # Enviar el valor actual del portapapeles al conectar
        try:
            curr_clip = get_local_clipboard()
            if curr_clip:
                await websocket.send_json({"type": "clipboard", "text": curr_clip})
        except Exception:
            pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # If this was the last client, stop all services
        if len(self.active_connections) == 0:
            logger.info("Last client disconnected. Stopping all background services...")
            stop_fft_processor()
            stop_telemetry_loop()
            stop_logging_stream()
            stop_download_watcher()
            stop_clipboard_watcher()

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
    """Genera certificados SSL autofirmados en el directorio .kiro si no existen o si la IP cambió."""
    import ipaddress
    lan_ip = get_lan_ip()
    ip_txt_path = os.path.join(KIRO_DIR, "cert_ip.txt")
    
    ip_changed = True
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH) and os.path.exists(ip_txt_path):
        try:
            with open(ip_txt_path, "r") as f:
                saved_ip = f.read().strip()
            if saved_ip == lan_ip:
                ip_changed = False
                logger.info(f"Certificados SSL existentes detectados y válidos para la IP {lan_ip}.")
                return
        except Exception:
            pass

    if ip_changed:
        logger.info(f"Generando nuevos certificados SSL autofirmados para la IP local {lan_ip}...")
        # Limpiar viejos si existen
        for p in [CERT_PATH, KEY_PATH, ip_txt_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

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
            x509.NameAttribute(NameOID.COMMON_NAME, lan_ip),
        ])

        # SANs setup
        san_items = [
            x509.DNSName(u"localhost"),
            x509.DNSName(u"viernes.local"),
        ]
        if lan_ip and lan_ip != "127.0.0.1":
            try:
                san_items.append(x509.IPAddress(ipaddress.ip_address(lan_ip)))
            except Exception as ex:
                logger.warning(f"No se pudo agregar IP {lan_ip} a SANs: {ex}")

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.now(timezone.utc) - timedelta(days=1)
        ).not_valid_after(
            datetime.now(timezone.utc) + timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName(san_items),
            critical=False,
        ).sign(key, hashes.SHA256())

        # Guardar clave, certificado e IP
        with open(CERT_PATH, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(KEY_PATH, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(ip_txt_path, "w") as f:
            f.write(lan_ip)
        logger.info(f"Certificados SSL autofirmados creados exitosamente para la IP: {lan_ip}.")
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

@app.get("/manifest.json")
async def get_manifest():
    static_dir = get_asset_dir("static")
    if static_dir:
        manifest_path = os.path.join(static_dir, "manifest.json")
        if os.path.exists(manifest_path):
            return FileResponse(manifest_path, media_type="application/json")
    return {"error": "manifest.json not found"}

@app.get("/sw.js")
async def get_sw():
    static_dir = get_asset_dir("static")
    if static_dir:
        sw_path = os.path.join(static_dir, "sw.js")
        if os.path.exists(sw_path):
            return FileResponse(sw_path, media_type="application/javascript")
    return {"error": "sw.js not found"}

@app.get("/icon-{icon_name}.png")
async def get_icon(icon_name: str):
    static_dir = get_asset_dir("static")
    if static_dir:
        icon_path = os.path.join(static_dir, f"icon-{icon_name}.png")
        if os.path.exists(icon_path):
            return FileResponse(icon_path, media_type="image/png")
    return {"error": f"icon-{icon_name}.png not found"}

@app.get("/favicon.ico")
async def get_favicon():
    static_dir = get_asset_dir("static")
    if static_dir:
        favicon_path = os.path.join(static_dir, "favicon.ico")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path, media_type="image/x-icon")
        icon_path = os.path.join(static_dir, "icon-192.png")
        if os.path.exists(icon_path):
            return FileResponse(icon_path, media_type="image/png")
    return {"error": "favicon not found"}

@app.get("/cert.pem")
async def download_cert():
    if os.path.exists(CERT_PATH):
        return FileResponse(CERT_PATH, media_type="application/x-x509-ca-cert", filename="viernes-cert.pem")
    return {"error": "Certificate not found"}

@app.get("/auth/pair")
async def auth_pair(pair_token: Optional[str] = Query(None), pair_pin: Optional[str] = Query(None)):
    global assistant_instance
    token_to_check = pair_token or pair_pin
    if not token_to_check:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing pairing token or PIN"
        )
        
    is_valid = False
    if assistant_instance:
        if token_to_check == assistant_instance.pair_token:
            is_valid = True
        elif token_to_check == assistant_instance.pair_pin:
            is_valid = True

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid pairing token or PIN"
        )
    payload = {
        "exp": datetime.now(timezone.utc) + timedelta(days=365),
        "sub": "viernes-remote-client"
    }
    token = jwt.encode(payload, JWT_PRIVATE_KEY, algorithm="RS256")
    return {"token": token}

async def verify_jwt_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])
        return payload
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}"
        )

@app.get("/api/config")
async def get_config(token_payload: dict = Depends(verify_jwt_token)):
    global assistant_instance
    if not assistant_instance:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    return {
        "keyboard_macros": assistant_instance.config.get("keyboard_macros", {}),
        "phonetics": assistant_instance.config.get("phonetics", {}),
        "whitelist_apps": assistant_instance.config.get("whitelist_apps", []),
        "games": assistant_instance.config.get("games", {}),
        "scenes": assistant_instance.config.get("scenes", [])
    }

@app.post("/api/config")
async def post_config(new_data: dict, token_payload: dict = Depends(verify_jwt_token)):
    global assistant_instance
    if not assistant_instance:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
        
    config_path = assistant_instance.config_path
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            current_config = json.load(f)
            
        if "keyboard_macros" in new_data:
            current_config["keyboard_macros"] = new_data["keyboard_macros"]
        if "phonetics" in new_data:
            current_config["phonetics"] = new_data["phonetics"]
        if "whitelist_apps" in new_data:
            current_config["whitelist_apps"] = new_data["whitelist_apps"]
        if "games" in new_data:
            current_config["games"] = new_data["games"]
        if "scenes" in new_data:
            current_config["scenes"] = new_data["scenes"]
            
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=2, ensure_ascii=False)
            
        assistant_instance.reload_config()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving config via API: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scenes/activate")
async def activate_scene_endpoint(payload: dict, token_payload: dict = Depends(verify_jwt_token)):
    global assistant_instance
    if not assistant_instance:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    scene_name = payload.get("name")
    if not scene_name:
        raise HTTPException(status_code=400, detail="Missing scene name")
    success = assistant_instance.activate_scene(scene_name)
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Scene not found")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    global active_mic_source
    
    try:
        if not token:
            raise Exception("Missing token")
        jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])
    except Exception as e:
        logger.warning(f"WebSocket connection rejected: {e}")
        await websocket.close(code=1008)
        return

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
                        # Si el asistente está escuchando y tiene el volumen atenuado,
                        # guardamos el volumen de restauración en su lugar para no anular la atenuación.
                        if hasattr(assistant_instance, "listener") and getattr(assistant_instance.listener, "original_volume", None) is not None:
                            logger.info(f"[WS] Asistente atenuado. Guardando {vol_val}% como volumen de restauración.")
                            assistant_instance.listener.original_volume = vol_val
                        else:
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

                elif event_type == "clipboard":
                    text = data.get("text", "")
                    logger.info("Comando de portapapeles recibido de cliente.")
                    threading.Thread(
                        target=set_local_clipboard,
                        args=(text,),
                        daemon=True
                    ).start()

                elif event_type == "pomodoro_control":
                    action = data.get("action")
                    if assistant_instance and hasattr(assistant_instance, "pomodoro"):
                        if action == "start":
                            assistant_instance.pomodoro.start()
                        elif action == "pause":
                            assistant_instance.pomodoro.pause()
                        elif action == "reset":
                            assistant_instance.pomodoro.reset()

                elif event_type == "activate_scene":
                    scene_name = data.get("name")
                    if assistant_instance and scene_name:
                        assistant_instance.activate_scene(scene_name)
    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado.")
    except Exception as e:
        logger.error(f"WebSocket error inesperado: {e}")
    finally:
        manager.disconnect(websocket)
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
