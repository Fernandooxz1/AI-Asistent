import threading
import logging
import io
import socket
import sys
from typing import Optional

from actions.system_action import SystemActionModule
from actions.browser_action import BrowserActionModule
from actions.youtube_play_action import YoutubePlayActionModule
# Si tenés más módulos en la carpeta actions/, agregalos acá abajo igual

import customtkinter as ctk
from PIL import Image, ImageDraw
import pystray

from main import ViernesAssistant

# ─── Configuración Global ─────────────────────────────────────────────────────
SINGLETON_PORT = 65432
logger = logging.getLogger("ViernesGUI")

# ─── Paleta de colores ────────────────────────────────────────────────────────
_BG        = "#3e3d3d"
_PANEL     = "#656565"
_ACCENT    = "#30a1de"  
_TEXT_DIM  = "#d7d7d7"
_LISTENING = "#30a1de"
_COMMAND   = "#30a1de"
_ERROR     = "#f87171"
_IDLE      = "#6b7280"


# ─── Lógica Singleton (Socket) ────────────────────────────────────────────────
def check_singleton():
    """
    Intenta conectarse al puerto del singleton. Si tiene éxito, envía la señal
    de mostrar y cierra la instancia actual.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", SINGLETON_PORT))
            s.sendall(b"MOSTRAR")
            logger.info("Instancia de Viernes ya detectada. Enviando señal MOSTRAR y saliendo.")
            sys.exit(0)
    except (socket.error, ConnectionRefusedError):
        # No hay otra instancia corriendo
        pass


class ViernesGUI(ctk.CTk):
    """
    Interfaz gráfica de Viernes basada en CustomTkinter con soporte para Singleton.
    """

    def __init__(self) -> None:
        super().__init__()

        # ── Configuración de la ventana ───────────────────────────────────
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Viernes Assistant")
        self.geometry("400x520")
        self.resizable(False, False)
        self.configure(fg_color=_BG)

        # Interceptar el botón de cerrar (X)
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        # ── Inicializar el asistente ──────────────────────────────────────
        self._stop_event = threading.Event()
        try:
            self.assistant = ViernesAssistant(state_callback=self.update_status_ui)
        except (ValueError, FileNotFoundError) as e:
            self._show_fatal_error(str(e))
            return

        # ── Construir la UI ───────────────────────────────────────────────
        self._build_ui()

        # ── Iniciar servidor Singleton (Socket) ───────────────────────────
        self._start_singleton_server()

        # ── Iniciar el tray antes de arrancar el hilo del asistente ───────
        self._tray_icon = self._create_tray_icon()
        self._tray_thread = threading.Thread(
            target=self._tray_icon.run,
            daemon=True,
            name="ViernesTray"
        )
        self._tray_thread.start()

        # ── Lanzar el asistente en segundo plano ──────────────────────────
        self._assistant_thread = threading.Thread(
            target=self.assistant.run,
            kwargs={"stop_event": self._stop_event},
            daemon=True,
            name="ViernesAssistant"
        )
        self._assistant_thread.start()

        # ── Polling de estado cada 500ms ─────────────────────────────────
        self._poll_status()

    # ─── Lógica de Socket Server ───────────────────────────────────────────────

    def _start_singleton_server(self) -> None:
        """Inicia un hilo servidor para escuchar señales de nuevas instancias."""
        def server_loop():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("127.0.0.1", SINGLETON_PORT))
                    s.listen(5)
                    logger.info(f"Servidor Singleton escuchando en el puerto {SINGLETON_PORT}")
                    
                    while not self._stop_event.is_set():
                        s.settimeout(2.0)
                        try:
                            conn, addr = s.accept()
                            with conn:
                                data = conn.recv(1024)
                                if data == b"MOSTRAR":
                                    logger.info("Recibida señal MOSTRAR vía socket.")
                                    self.after(0, self.show_window)
                        except socket.timeout:
                            continue
            except Exception as e:
                logger.error(f"Error en el servidor Singleton: {e}")

        threading.Thread(target=server_loop, daemon=True, name="SingletonServer").start()

    def show_window(self) -> None:
        """Restaura, enfoca y trae al frente la ventana."""
        self.deiconify()
        self.lift()
        self.focus_force()  # Forzar foco nativo del SO

    # ─── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Construye todos los widgets de la ventana principal."""
        header = ctk.CTkFrame(self, fg_color=_BG)
        header.pack(fill="x", padx=30, pady=(30, 0))

        ctk.CTkLabel(
            header,
            text="Viernes",
            font=ctk.CTkFont(family="Segoe UI", size=56, weight="bold"),
            text_color=_ACCENT,
        ).pack()

        ctk.CTkLabel(
            header,
            text=" AI Asistent",
            font=ctk.CTkFont(size=12),
            text_color=_TEXT_DIM,
        ).pack(pady=(2, 0))

        ctk.CTkFrame(self, fg_color="#2a2a2a", height=1).pack(fill="x", padx=30, pady=20)

        status_panel = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=12)
        status_panel.pack(fill="x", padx=30, pady=(0, 16))

        ctk.CTkLabel(status_panel, text="Status", font=ctk.CTkFont(size=11), text_color=_TEXT_DIM).pack(anchor="w", padx=16, pady=(12, 0))

        self._status_dot = ctk.CTkLabel(
            status_panel,
            text="● Listening keyword...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_IDLE,
        )
        self._status_dot.pack(anchor="w", padx=16, pady=(2, 12))

        mic_panel = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=12)
        mic_panel.pack(fill="x", padx=30, pady=(0, 16))

        mic_header = ctk.CTkFrame(mic_panel, fg_color="transparent")
        mic_header.pack(fill="x", padx=16, pady=(12, 0))

        ctk.CTkLabel(mic_header, text="Microphone", font=ctk.CTkFont(size=11), text_color=_TEXT_DIM).pack(side="left")

        self._sensitivity_label = ctk.CTkLabel(
            mic_header,
            text=f"{int(self.assistant.listener.recognizer.energy_threshold)}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_ACCENT,
        )
        self._sensitivity_label.pack(side="right")

        self._slider = ctk.CTkSlider(
            mic_panel,
            from_=100,
            to=4000,
            number_of_steps=390,
            button_color=_ACCENT,
            button_hover_color="#7ac0e8",
            progress_color=_ACCENT,
            fg_color="#2a2a2a",
            command=self._on_slider_change,
        )
        self._slider.set(self.assistant.listener.recognizer.energy_threshold)
        self._slider.pack(fill="x", padx=16, pady=(6, 16))

        info_panel = ctk.CTkFrame(self, fg_color=_PANEL, corner_radius=12)
        info_panel.pack(fill="x", padx=30, pady=(0, 16))

        info_row = ctk.CTkFrame(info_panel, fg_color="transparent")
        info_row.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(info_row, text="Key word", font=ctk.CTkFont(size=11), text_color=_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(info_row, text=f"« {self.assistant.listener.wake_word} »", font=ctk.CTkFont(size=12, weight="bold"), text_color=_ACCENT).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=30, pady=(0, 30))

        ctk.CTkButton(
            btn_row,
            text="Web Remote",
            fg_color=_ACCENT,
            hover_color="#3cb9fc",
            text_color="#ffffff",
            corner_radius=10,
            height=38,
            width=160,
            command=self._open_web_remote_info,
        ).pack(side="left", expand=True, padx=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="Minimize",
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            text_color=_TEXT_DIM,
            corner_radius=10,
            height=38,
            width=160,
            command=self._hide_to_tray,
        ).pack(side="right", expand=True)

    def _show_fatal_error(self, message: str) -> None:
        """Muestra un mensaje de error crítico."""
        ctk.CTkLabel(self, text="❌ Error de inicialización", font=ctk.CTkFont(size=18, weight="bold"), text_color=_ERROR).pack(pady=40)
        ctk.CTkLabel(self, text=message, wraplength=340, font=ctk.CTkFont(size=12), text_color=_TEXT_DIM).pack(padx=30)

    # ─── Callbacks de estado ───────────────────────────────────────────────────

    def update_status_ui(self, estado: str) -> None:
        """Actualiza el indicador de estado de la GUI de forma thread-safe."""
        STATE_MAP = {
            "ESCUCHANDO_WAKE":  ("● Esperando comando 'Viernes'...",  _LISTENING),
            "GRABANDO_COMANDO": ("● Escuchando...",  "#22d3ee"),
            "PROCESANDO":       ("● Pensando...",             "#e2d73c"),
        }
        text, color = STATE_MAP.get(estado, (f"● {estado}", _TEXT_DIM))
        self.after(0, lambda t=text, c=color: self._status_dot.configure(text=t, text_color=c))

    def _on_slider_change(self, value: float) -> None:
        """Ajusta la sensibilidad del micrófono."""
        int_value = int(value)
        self.assistant.listener.update_sensitivity(int_value)
        self._sensitivity_label.configure(text=str(int_value))

    def _poll_status(self) -> None:
        """Polling de estado dinámico."""
        if self._assistant_thread.is_alive():
            energy = int(self.assistant.listener.recognizer.energy_threshold)
            self._sensitivity_label.configure(text=str(energy))
        else:
            self._set_status("● Detenido", _ERROR)
        self.after(500, self._poll_status)

    def _set_status(self, text: str, color: str) -> None:
        self.after(0, lambda: self._status_dot.configure(text=text, text_color=color))

    # ─── System Tray ───────────────────────────────────────────────────────────

    def _make_tray_image(self) -> Image.Image:
        return Image.new("RGB", (64, 64), color="#5d93ea")

    def _create_tray_icon(self) -> pystray.Icon:
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar Window",   self._show_from_tray, default=True),
            pystray.MenuItem("Ajustes",          self._open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir por completo", self._quit_app),
        )
        return pystray.Icon(name="viernes", icon=self._make_tray_image(), title="Viernes Assistant", menu=menu)

    def _hide_to_tray(self) -> None:
        logger.info("Ocultando ventana al system tray...")
        self.withdraw()

    def _show_from_tray(self, icon: pystray.Icon, item) -> None:
        self.after(0, self.show_window)

    def _open_settings(self, icon: pystray.Icon, item) -> None:
        self.after(0, self.show_window)

    def _quit_app(self, icon: pystray.Icon, item) -> None:
        logger.info("Saliendo por completo de Viernes...")
        self._stop_event.set()
        icon.stop()
        self.after(0, self.quit)
        self.after(0, self.destroy)

    def _open_web_remote_info(self) -> None:
        """Abre la ventana con el QR y la URL de control remoto."""
        try:
            import socket
            def get_lan_ip() -> str:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    ip = s.getsockname()[0]
                    s.close()
                    return ip
                except Exception:
                    return "127.0.0.1"
            
            lan_ip = get_lan_ip()
            url = f"https://{lan_ip}:8000/"
            
            # Abrir ventana toplevel
            ViernesWebRemoteWindow(self, url)
        except Exception as e:
            logger.error(f"Error al abrir info de web remote: {e}")


class ViernesWebRemoteWindow(ctk.CTkToplevel):
    """Ventana pop-up que muestra el QR y la URL de control remoto."""
    def __init__(self, parent, url: str) -> None:
        super().__init__(parent)
        self.title("Web Remote Control")
        self.geometry("340x440")
        self.resizable(False, False)
        self.configure(fg_color="#3e3d3d")
        
        # Estilo para que sea modal (seguro ante grab failures en Wayland/Hyprland)
        try:
            self.transient(parent)
            self.wait_visibility()
            self.grab_set()
        except Exception as e:
            logger.warning(f"No se pudo establecer el grab modal (ignorable): {e}")

        ctk.CTkLabel(
            self,
            text="Web Remote Control",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#30a1de"
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            self,
            text="Escanea el código QR con tu móvil\n(Deben estar en la misma red Wi-Fi):",
            font=ctk.CTkFont(size=12),
            text_color="#d7d7d7",
            justify="center"
        ).pack(pady=(0, 15))

        # Generar código QR
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=5, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="#000000", back_color="#ffffff").convert("RGB")
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(180, 180))
            
            qr_label = ctk.CTkLabel(self, image=ctk_img, text="")
            qr_label.image = ctk_img  # Mantener referencia
            qr_label.pack(pady=5)
        except Exception as e:
            logger.error(f"Error al generar código QR: {e}")
            ctk.CTkLabel(self, text="[Error al generar código QR]", text_color="#f87171").pack(pady=10)

        # Enlace visible
        url_label = ctk.CTkLabel(
            self,
            text=url,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color="#30a1de",
            cursor="hand2"
        )
        url_label.pack(pady=(15, 10))

        def copy_url(event=None):
            self.clipboard_clear()
            self.clipboard_append(url)
            copied_btn.configure(text="¡Copiado al portapapeles!", fg_color="#30d158")
            self.after(2000, lambda: copied_btn.configure(text="Copiar URL", fg_color="#2a2a2a"))

        url_label.bind("<Button-1>", copy_url)

        copied_btn = ctk.CTkButton(
            self,
            text="Copiar URL",
            fg_color="#2a2a2a",
            hover_color="#3a3a3a",
            text_color="#d7d7d7",
            corner_radius=8,
            height=28,
            command=copy_url
        )
        copied_btn.pack(pady=(0, 20))


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    check_singleton()  # 1. Verificar si ya existe una instancia
    app = ViernesGUI()    # 2. Si no existe, arrancar normal
    app.mainloop()
