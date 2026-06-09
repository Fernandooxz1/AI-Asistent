import threading
import logging
import io
import socket
import sys
import time
import math
from typing import Optional

from actions.system_action import SystemActionModule
from actions.browser_action import BrowserActionModule
from actions.youtube_play_action import YoutubePlayActionModule

import customtkinter as ctk
from PIL import Image, ImageDraw
import pystray

from main import ViernesAssistant

# ─── Configuración Global ─────────────────────────────────────────────────────
SINGLETON_PORT = 65432
logger = logging.getLogger("ViernesGUI")

# ─── Paleta de colores Stark J.A.R.V.I.S. / V.I.E.R.N.E.S. ─────────────────────
_BG_DARK   = "#080b12"
_PANEL     = "#0c1220"
_ACCENT    = "#00f3ff"  # Neon Cyan
_TEXT_DIM  = "#a0aec0"
_ERROR     = "#ff3b30"  # Neon Red

def check_singleton():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", SINGLETON_PORT))
            s.sendall(b"MOSTRAR")
            logger.info("Instancia de Viernes ya detectada. Enviando señal MOSTRAR y saliendo.")
            sys.exit(0)
    except (socket.error, ConnectionRefusedError):
        pass


class ViernesGUI(ctk.CTk):
    def __init__(self) -> None:
        # Configurar clase para Hyprland float/pin rules
        super().__init__(className="viernes-hud")

        # ── Configuración de la ventana ───────────────────────────────────
        ctk.set_appearance_mode("dark")
        self.title("Viernes Assistant HUD")
        self.geometry("340x440")
        self.resizable(False, False)
        
        # Hacerla sin bordes (frameless) y siempre visible (floating)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.92) # Semi-transparente
        self.configure(fg_color=_BG_DARK)

        # Interceptar el botón de cerrar
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        # Habilitar arrastre con el ratón
        self._drag_x = 0
        self._drag_y = 0
        self.bind("<Button-1>", self.start_drag)
        self.bind("<B1-Motion>", self.do_drag)

        # ── Inicializar el asistente ──────────────────────────────────────
        self._stop_event = threading.Event()
        try:
            self.assistant = ViernesAssistant(state_callback=self.update_status_ui)
        except (ValueError, FileNotFoundError) as e:
            self._show_fatal_error(str(e))
            return

        # ── Configuración inicial de animación ───────────────────────────
        self._accent_color = _ACCENT
        self._accent_secondary = "#0f426c"
        self._anim_speed = 2
        self._pulse_speed = 1.2
        self._base_core_size = 18
        self._pulse_max_offset = 4
        self._hud_angle = 0
        self._pulse_val = 0

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

        # Iniciar loops de polling y animación
        self._poll_status()
        self._animate_hud()

    def start_drag(self, event):
        widget_path = str(event.widget).lower()
        if "slider" in widget_path or "button" in widget_path:
            self._drag_active = False
            return
        self._drag_active = True
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def do_drag(self, event):
        if not getattr(self, "_drag_active", False):
            return
        dx = event.x_root - self._drag_x
        dy = event.y_root - self._drag_y
        x = self.winfo_x() + dx
        y = self.winfo_y() + dy
        self.geometry(f"+{x}+{y}")
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _start_singleton_server(self) -> None:
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
        self.deiconify()
        self.lift()
        self.focus_force()

    def _build_ui(self) -> None:
        # Contenedor principal con borde neon y esquinas redondeadas simuladas
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color=_BG_DARK,
            border_color=_ACCENT,
            border_width=1.5,
            corner_radius=20
        )
        self.main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Permitir arrastre también haciendo clic en el main_frame
        self.main_frame.bind("<Button-1>", self.start_drag)
        self.main_frame.bind("<B1-Motion>", self.do_drag)

        # Header con info del sistema al estilo Stark HUD
        header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 0))
        
        ctk.CTkLabel(
            header_frame,
            text="V.I.E.R.N.E.S. Core",
            font=ctk.CTkFont(family="Courier", size=13, weight="bold"),
            text_color="#4a5568"
        ).pack(side="left")
        
        ctk.CTkLabel(
            header_frame,
            text="ONLINE",
            font=ctk.CTkFont(family="Courier", size=10, weight="bold"),
            text_color=_ACCENT
        ).pack(side="right")

        # Canvas del Reactor de Arco
        self.canvas = ctk.CTkCanvas(
            self.main_frame,
            width=200,
            height=200,
            bg=_BG_DARK,
            highlightthickness=0
        )
        self.canvas.pack(pady=(10, 5))
        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)

        # Etiqueta de estado J.A.R.V.I.S.
        self._status_label = ctk.CTkLabel(
            self.main_frame,
            text="INICIALIZANDO...",
            font=ctk.CTkFont(family="Courier", size=14, weight="bold"),
            text_color=_ACCENT
        )
        self._status_label.pack(pady=5)

        # Etiqueta de Pomodoro
        self._pomodoro_label = ctk.CTkLabel(
            self.main_frame,
            text="🍅 POMODORO: INACTIVO",
            font=ctk.CTkFont(family="Courier", size=11, weight="bold"),
            text_color=_TEXT_DIM
        )
        self._pomodoro_label.pack(pady=(2, 5))

        # Slider de Sensibilidad
        slider_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        slider_frame.pack(fill="x", padx=30, pady=5)

        ctk.CTkLabel(
            slider_frame, 
            text="NOISE GATE THRESHOLD:", 
            font=ctk.CTkFont(family="Courier", size=9, weight="bold"), 
            text_color=_TEXT_DIM
        ).pack(side="left")

        self._sensitivity_label = ctk.CTkLabel(
            slider_frame,
            text=f"{int(self.assistant.listener.recognizer.energy_threshold)}",
            font=ctk.CTkFont(family="Courier", size=10, weight="bold"),
            text_color=_ACCENT
        )
        self._sensitivity_label.pack(side="right")

        self._slider = ctk.CTkSlider(
            self.main_frame,
            from_=100,
            to=4000,
            number_of_steps=390,
            button_color=_ACCENT,
            button_hover_color="#7ac0e8",
            progress_color=_ACCENT,
            fg_color="#1a202c",
            command=self._on_slider_change,
        )
        self._slider.set(self.assistant.listener.recognizer.energy_threshold)
        self._slider.pack(fill="x", padx=30, pady=(0, 15))

        # Botones flotantes minimalistas
        btn_row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(
            btn_row,
            text="REMOTE CONTROL",
            fg_color="transparent",
            border_color=_ACCENT,
            border_width=1,
            hover_color="#092635",
            text_color=_ACCENT,
            corner_radius=10,
            height=32,
            font=ctk.CTkFont(family="Courier", size=10, weight="bold"),
            command=self._open_web_remote_info,
        ).pack(side="left", expand=True, padx=(0, 5))

        ctk.CTkButton(
            btn_row,
            text="OCULTAR",
            fg_color="transparent",
            border_color="#2d3748",
            border_width=1,
            hover_color="#171f2c",
            text_color=_TEXT_DIM,
            corner_radius=10,
            height=32,
            font=ctk.CTkFont(family="Courier", size=10, weight="bold"),
            command=self._hide_to_tray,
        ).pack(side="right", expand=True)

    def _show_fatal_error(self, message: str) -> None:
        ctk.CTkLabel(self, text="❌ Error de inicialización", font=ctk.CTkFont(size=18, weight="bold"), text_color=_ERROR).pack(pady=40)
        ctk.CTkLabel(self, text=message, wraplength=300, font=ctk.CTkFont(size=12), text_color=_TEXT_DIM).pack(padx=20)

    def update_status_ui(self, estado: str) -> None:
        """Sincroniza los parámetros de animación con el estado del asistente."""
        if estado == "ESCUCHANDO_WAKE":
            self._accent_color = "#00f3ff"       # Cyan
            self._accent_secondary = "#0c2844"
            self._anim_speed = 2
            self._pulse_speed = 1.2
            self._base_core_size = 18
            self._pulse_max_offset = 4
            status_text = "ESCUCHANDO..."
        elif estado == "GRABANDO_COMANDO":
            self._accent_color = "#ff9500"       # Naranja/Rojo
            self._accent_secondary = "#ff3b30"
            self._anim_speed = 6
            self._pulse_speed = 3.5
            self._base_core_size = 15
            self._pulse_max_offset = 12
            status_text = "CAPTURANDO VOZ..."
        elif estado == "PROCESANDO":
            self._accent_color = "#00a2ff"       # Azul Neón
            self._accent_secondary = "#00f3ff"
            self._anim_speed = 4
            self._pulse_speed = 2.0
            self._base_core_size = 20
            self._pulse_max_offset = 2
            status_text = "PROCESANDO..."
        elif estado == "DESCARGANDO_MODELO":
            self._accent_color = "#a855f7"       # Violeta / Púrpura
            self._accent_secondary = "#3b0764"
            self._anim_speed = 1.5
            self._pulse_speed = 1.0
            self._base_core_size = 14
            self._pulse_max_offset = 6
            status_text = "DESCARGANDO MODELO..."
        else:
            self._accent_color = "#4a5568"       # Gris/Inactivo
            self._accent_secondary = "#1a202c"
            self._anim_speed = 0.5
            self._pulse_speed = 0.4
            self._base_core_size = 10
            self._pulse_max_offset = 1
            status_text = "SISTEMA INACTIVO"

        self.after(0, lambda: self.main_frame.configure(border_color=self._accent_color))
        self.after(0, lambda: self._slider.configure(button_color=self._accent_color, progress_color=self._accent_color))
        self.after(0, lambda: self._sensitivity_label.configure(text_color=self._accent_color))
        self.after(0, lambda: self._status_label.configure(text=status_text, text_color=self._accent_color))

    def _animate_hud(self) -> None:
        """Bucle de renderizado 2D en tiempo real para el Reactor de Arco."""
        if self._stop_event.is_set():
            return

        self._hud_angle = (self._hud_angle + self._anim_speed) % 360
        self._pulse_val += 0.05 * self._pulse_speed
        
        # Obtener energía en tiempo real de la captura de audio
        energy = getattr(self.assistant.listener, "current_energy", 0.0)
        energy_factor = min(energy / 1000.0, 1.5)  # Factor escalado máx 1.5
        
        pulse_size = self._base_core_size + (self._pulse_max_offset * math.sin(self._pulse_val))
        # Escalar el núcleo con la voz del usuario
        pulse_size += energy_factor * 12.0
        
        # Limpiar
        self.canvas.delete("all")
        
        # Efecto de vibración física en los ejes cx, cy si hay sonido/voz significativo
        cx, cy = 100, 100
        if energy > 100:
            import random
            shake_amt = min(energy / 150.0, 5.0)  # Desplazamiento máximo de 5 píxeles
            cx += random.uniform(-shake_amt, shake_amt)
            cy += random.uniform(-shake_amt, shake_amt)

        # Dibujar líneas de mira / retícula
        self.canvas.create_line(cx-90, cy, cx-70, cy, fill="#121e30", width=1)
        self.canvas.create_line(cx+70, cy, cx+90, cy, fill="#121e30", width=1)
        self.canvas.create_line(cx, cy-90, cx, cy-70, fill="#121e30", width=1)
        self.canvas.create_line(cx, cy+70, cx, cy+90, fill="#121e30", width=1)

        # Círculo externo tenue
        self.canvas.create_oval(cx-85, cy-85, cx+85, cy+85, outline="#101d32", width=1)

        # Destellos / espigas de energía radiantes desde el exterior al hablar
        if energy > 100:
            spike_count = 12
            outer_r = 85
            max_spike_len = 14.0
            spike_len = min((energy / 1000.0) * max_spike_len, max_spike_len)
            for i in range(spike_count):
                angle_rad = math.radians(i * (360 / spike_count) + self._hud_angle)
                x1 = cx + outer_r * math.cos(angle_rad)
                y1 = cy + outer_r * math.sin(angle_rad)
                x2 = cx + (outer_r + spike_len) * math.cos(angle_rad)
                y2 = cy + (outer_r + spike_len) * math.sin(angle_rad)
                self.canvas.create_line(x1, y1, x2, y2, fill=self._accent_color, width=1)

        # Anillo giratorio principal (conmutador segmentado)
        self.canvas.create_arc(cx-80, cy-80, cx+80, cy+80, start=self._hud_angle, extent=60, outline=self._accent_color, width=2, style="arc")
        self.canvas.create_arc(cx-80, cy-80, cx+80, cy+80, start=self._hud_angle+120, extent=60, outline=self._accent_color, width=2, style="arc")
        self.canvas.create_arc(cx-80, cy-80, cx+80, cy+80, start=self._hud_angle+240, extent=60, outline=self._accent_color, width=2, style="arc")

        # Anillo secundario contra-rotatorio
        self.canvas.create_arc(cx-65, cy-65, cx+65, cy+65, start=-self._hud_angle*1.3 + 45, extent=100, outline=self._accent_secondary, width=1, style="arc")
        self.canvas.create_arc(cx-65, cy-65, cx+65, cy+65, start=-self._hud_angle*1.3 + 225, extent=100, outline=self._accent_secondary, width=1, style="arc")

        # Círculo discontinuo intermedio
        self.canvas.create_oval(cx-45, cy-45, cx+45, cy+45, outline=self._accent_secondary, width=1, dash=(5, 5))

        # Núcleo pulsante
        self.canvas.create_oval(cx-pulse_size-5, cy-pulse_size-5, cx+pulse_size+5, cy+pulse_size+5, outline=self._accent_color, width=1)
        self.canvas.create_oval(cx-pulse_size, cy-pulse_size, cx+pulse_size, cy+pulse_size, fill=self._accent_color, outline="")

        # Arco de progreso Pomodoro alrededor del núcleo
        if hasattr(self.assistant, "pomodoro"):
            pomo = self.assistant.pomodoro.get_status()
            if pomo["active"]:
                angle_extent = 360 * (pomo["time_left"] / pomo["duration"])
                pomo_color = "#00f3ff" if pomo["state"] == "work" else "#ff9500"
                self.canvas.create_arc(cx-52, cy-52, cx+52, cy+52, start=90, extent=-angle_extent, outline=pomo_color, width=3, style="arc")

        # Textos informativos de telemetría HUD
        self.canvas.create_text(cx-68, cy+78, text="HUD: ACTV", fill="#182c44", font=("Courier", 7, "bold"))
        self.canvas.create_text(cx+58, cy+78, text=f"ROT:{int(self._hud_angle)}", fill="#182c44", font=("Courier", 7, "bold"))

        self.after(33, self._animate_hud)

    def _on_slider_change(self, value: float) -> None:
        int_value = int(value)
        self.assistant.listener.update_sensitivity(int_value)
        self._sensitivity_label.configure(text=str(int_value))

    def _poll_status(self) -> None:
        if self._assistant_thread.is_alive():
            energy = int(self.assistant.listener.recognizer.energy_threshold)
            self._sensitivity_label.configure(text=str(energy))
            if hasattr(self.assistant, "pomodoro"):
                pomo = self.assistant.pomodoro.get_status()
                if pomo["active"]:
                    mins = pomo["time_left"] // 60
                    secs = pomo["time_left"] % 60
                    state_str = "TRABAJO" if pomo["state"] == "work" else "DESCANSO"
                    color = "#00f3ff" if pomo["state"] == "work" else "#ff9500"
                    self._pomodoro_label.configure(
                        text=f"🍅 {state_str}: {mins:02d}:{secs:02d}",
                        text_color=color
                    )
                else:
                    self._pomodoro_label.configure(
                        text="🍅 POMODORO: INACTIVO",
                        text_color=_TEXT_DIM
                    )
        else:
            self._status_label.configure(text="DESCONECTADO", text_color=_ERROR)
        self.after(500, self._poll_status)

    def _make_tray_image(self) -> Image.Image:
        # Generar icono de tray con el color cyan Stark
        image = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), outline="#00f3ff", width=4)
        draw.ellipse((22, 22, 42, 42), fill="#00f3ff")
        return image

    def _create_tray_icon(self) -> pystray.Icon:
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar HUD",   self._show_from_tray, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Apagar Asistente", self._quit_app),
        )
        return pystray.Icon(name="viernes", icon=self._make_tray_image(), title="Viernes HUD", menu=menu)

    def _hide_to_tray(self) -> None:
        logger.info("Ocultando ventana al system tray...")
        self.withdraw()

    def _show_from_tray(self, icon: pystray.Icon, item) -> None:
        self.after(0, self.show_window)

    def _quit_app(self, icon: pystray.Icon, item) -> None:
        logger.info("Saliendo por completo de Viernes...")
        self._stop_event.set()
        icon.stop()
        self.after(0, self.quit)
        self.after(0, self.destroy)

    def _open_web_remote_info(self) -> None:
        try:
            lan_ip = get_lan_ip()
            pair_token = getattr(self.assistant, "pair_token", "")
            pair_pin = getattr(self.assistant, "pair_pin", "")
            url = f"https://{lan_ip}:8000/?pair_token={pair_token}"
            ViernesWebRemoteWindow(self, url, pair_pin)
        except Exception as e:
            logger.error(f"Error al abrir info de web remote: {e}")

def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ViernesWebRemoteWindow(ctk.CTkToplevel):
    def __init__(self, parent, url: str, pair_pin: str) -> None:
        super().__init__(parent)
        self.title("Web Remote Control")
        self.geometry("340x480")
        self.resizable(False, False)
        self.configure(fg_color=_BG_DARK)
        
        # Borde neon también en popup modal
        self.border_frame = ctk.CTkFrame(
            self,
            fg_color=_BG_DARK,
            border_color=_ACCENT,
            border_width=1.5,
            corner_radius=16
        )
        self.border_frame.pack(fill="both", expand=True, padx=4, pady=4)

        try:
            self.transient(parent)
            self.wait_visibility()
            self.grab_set()
        except Exception as e:
            logger.warning(f"No se pudo establecer el grab modal: {e}")

        ctk.CTkLabel(
            self.border_frame,
            text="Web Remote Control",
            font=ctk.CTkFont(family="Courier", size=18, weight="bold"),
            text_color=_ACCENT
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            self.border_frame,
            text=f"PIN Manual: {pair_pin}",
            font=ctk.CTkFont(family="Courier", size=15, weight="bold"),
            text_color="#ff9500"
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            self.border_frame,
            text="Escanea el código QR con tu móvil\n(Deben estar en la misma red Wi-Fi):",
            font=ctk.CTkFont(family="Courier", size=10),
            text_color=_TEXT_DIM,
            justify="center"
        ).pack(pady=(0, 10))

        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=5, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="#080b12", back_color="#ffffff").convert("RGB")
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(180, 180))
            
            qr_label = ctk.CTkLabel(self.border_frame, image=ctk_img, text="")
            qr_label.image = ctk_img
            qr_label.pack(pady=5)
        except Exception as e:
            logger.error(f"Error al generar código QR: {e}")
            ctk.CTkLabel(self.border_frame, text="[Error al generar código QR]", text_color=_ERROR).pack(pady=10)

        url_label = ctk.CTkLabel(
            self.border_frame,
            text=url,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color=_ACCENT,
            cursor="hand2"
        )
        url_label.pack(pady=(15, 10))

        def copy_url(event=None):
            self.clipboard_clear()
            self.clipboard_append(url)
            copied_btn.configure(text="¡COPIADO!", fg_color="#30d158")
            self.after(2000, lambda: copied_btn.configure(text="COPIAR URL", fg_color="transparent"))

        url_label.bind("<Button-1>", copy_url)

        copied_btn = ctk.CTkButton(
            self.border_frame,
            text="COPIAR URL",
            fg_color="transparent",
            border_color="#2d3748",
            border_width=1,
            hover_color="#171f2c",
            text_color=_TEXT_DIM,
            corner_radius=8,
            height=28,
            font=ctk.CTkFont(family="Courier", size=10, weight="bold"),
            command=copy_url
        )
        copied_btn.pack(pady=(0, 20))


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    check_singleton()
    app = ViernesGUI()
    app.mainloop()
