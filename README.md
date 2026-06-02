# 🤖 Viernes (AI-Voice-Assistant)

Viernes es un asistente de voz inteligente, rápido y 100% local diseñado específicamente para entornos Linux con Wayland (como Hyprland u Omarchy). Utiliza el poder de **Ollama (Qwen 2.5)** para el procesamiento de lenguaje natural (NLP) y ejecuta automatizaciones de sistema, macros de teclado a nivel hardware y consultas dinámicas en tiempo real.

A diferencia de los asistentes comerciales, Viernes no depende de servicios de pago en la nube, respeta plenamente tu privacidad y tiene la capacidad de saltarse las restricciones de seguridad de Wayland interactuando directamente con el Kernel de Linux a través de `/dev/uinput` y `ydotool`. Además, expone un **servidor web/WebSocket HTTPS** que te permite controlarlo y usar el micrófono de tu móvil como entrada de voz a través de la red local (LAN).

---

## ✨ Características Principales

* **🧠 Procesamiento Local:** Clasificación de lenguaje natural y extracción de intenciones/entidades utilizando modelos de Ollama (ej: `qwen2.5:3b`) de forma 100% offline.
* **🖥️ HUD Holográfico de Escritorio (Estilo Stark J.A.R.V.I.S./V.I.E.R.N.E.S.):** Rediseño completo de la interfaz local con CustomTkinter. Es una ventana flotante, semitransparente, frameless y arrastrable. Cuenta con un canvas animado 2D del Reactor de Arco que rota y pulsa en tiempo real según el estado del asistente (ESCUCHANDO, GRABANDO, PROCESANDO, INACTIVO) y un control deslizante interactivo para ajustar el umbral de sensibilidad del Noise Gate.
* **🌐 Respuestas Conversacionales Dinámicas:** Módulo capaz de responder preguntas de conocimiento general y de tiempo real. 
  - **Consultas estáticas/históricas:** Utiliza la base de conocimientos nativa del LLM local (ej: *"¿cuántos goles hizo Messi en 2012?"*).
  - **Consultas en tiempo real:** Raspa automáticamente fragmentos de internet de forma gratuita con **DuckDuckGo** y los sintetiza con Qwen (ej: *"¿contra quién juega River el sábado?"* o *"¿qué día es hoy?"* con inyección dinámica del reloj del sistema).
* **⛓️ Encadenamiento de Comandos ("AND"):** Soporta secuencias de órdenes en una sola frase (ej: *"busca el último video de Hytale en youtube, ponelo en pantalla completa y subí el volumen"*).
* **⏳ Pausas de Carga Inteligentes:** Al ejecutar cadenas de comandos, el orquestador espera de forma inteligente **2.5 segundos** después de abrir aplicaciones gráficas pesadas (Brave, YouTube, Steam) para darles tiempo a cargar y tomar foco, y **0.5 segundos** entre macros de teclado simples.
* **⚡ Cortocircuito de Macros (Reflejo):** Sistema de reflejos de coincidencia difusa (`rapidfuzz`) de alta velocidad. Si detecta comandos exactos o fonéticos de volumen, reproducción o control, los ejecuta en milisegundos sin invocar a la IA.
* **🔈 Atenuación de Audio en Activación (Ducking):** Al detectar la palabra de activación, Viernes reduce de inmediato el volumen general del sistema al 10%. Esto evita que el micrófono capte interferencias del audio de la PC y mejora sustancialmente la precisión de transcripción de Whisper. El volumen original se restaura automáticamente una vez ejecutada la orden.
* **📱 Control Remoto Web por Red Local (PWA & HTTPS Seguro):** Servidor FastAPI + WebSocket integrado con HTTPS seguro (certificados SSL autofirmados generados de forma automática en `.kiro/` con soporte SAN). Permite:
  - **Soporte PWA:** Aplicación Web Progresiva instalable en iOS y Android con almacenamiento en caché offline mediante Service Worker (`static/sw.js`).
  - **Certificados SSL Automáticos con SAN:** Generación automática de certificados SSL autofirmados inyectando la dirección IP LAN dinámica actual en los campos Subject Alternative Names (SAN). Esto permite el acceso HTTPS seguro, obligatorio en navegadores móviles modernos para otorgar permisos de micrófono (`getUserMedia`).
  - **Emparejamiento Seguro (JWT + PIN/QR):** Las conexiones y APIs de configuración están protegidas mediante JSON Web Tokens (JWT) firmados con criptografía asimétrica RS256. El cliente móvil debe emparejarse escaneando un código QR dinámico desde la interfaz HUD de la PC o ingresando manualmente un PIN de 6 dígitos.
  - **Redirección de Voz Móvil (Mobile TTS):** Si el micrófono del móvil está seleccionado como la entrada activa, la síntesis de voz se redirige directamente a los altavoces del móvil por WebSockets, utilizando la API Web Speech del navegador (con desbloqueo específico en iOS Safari).
  - Ver el estado del asistente en tiempo real (IDLE, grabando, procesando).
  - Usar la entrada de micrófono del móvil (iPhone/Android) para enviar notas de voz que se transcriben en la PC usando Whisper.
  - Controlar volumen de forma bidireccional mediante sliders.
  - Comandos multimedia directos (`play-pause`, `next`, `previous`) sincronizados por `playerctl` e interpolación de barra de progreso.
* **🔇 Puerta de Ruido Inteligente (Noise Gate):** Filtro de supresión de ruido basado en energía RMS en `core/audio_listener.py` con umbral configurable (`noise_gate_threshold` en `config.json`). Reemplaza con silencio absoluto (ceros) las muestras de audio que no superan el nivel de energía umbral, evitando disparos involuntarios y previniendo alucinaciones de Whisper.
* **🔊 Control de Volumen General Unificado:** Control de volumen unificado que actúa directamente sobre el canal de audio del sistema (PipeWire/PulseAudio mediante `pactl`), sincronizando de forma instantánea (~0ms) el control de volumen del slider del panel web móvil con los comandos de voz de volumen de la PC.
* **⌨️ Automatización a Nivel Hardware:** Utiliza `ydotool` para inyectar eventos reales de entrada en el Kernel, evitando restricciones del compositor.
* **🛡️ Sanitización Fonética:** Filtro de corrección automática para mapear palabras homófonas o mal interpretadas por el micrófono (ej: *"davoxs"*, *"da"* -> *"davo"*; *"hightail"* -> *"hytale"*).

---

## 🛠️ Tecnologías Utilizadas

* **Lenguaje:** Python 3 (empaquetado e independiente con PyInstaller) y CustomTkinter para la GUI.
* **Reconocimiento de Voz (STT):** Vosk (es-0.42 pequeño para la palabra de activación local) + Faster-Whisper (modelo medium en CUDA para una transcripción de voz remota y local ultra-precisa).
* **Sintetizador de Voz (TTS):** Motor TTS local en español (apoyado en `espeak` o `espeak-ng`).
* **Procesamiento NLP:** Ollama local (`qwen2.5:3b` o superior) forzando formato de respuesta JSON para asegurar robustez.
* **Control Remoto:** FastAPI, Uvicorn, WebSockets y Cryptography para SSL locales.
* **Automatización:** `ydotool`, `hyprctl`, `playerctl`.

---

## 📦 Instalación y Requisitos

### 1. Dependencias del Sistema
Asegúrate de instalar Python, Ollama, ydotool y las librerías de sonido y UI necesarias (Gtk/AppIndicator):
```bash
sudo pacman -S python ollama ydotool libappindicator-gtk3 playerctl
```

### 2. Configuración de ydotool (Wayland)
Para simular eventos de teclado en Wayland, agrega tu usuario al grupo `input` y habilita el daemon:
```bash
sudo usermod -aG input $USER
# Reinicia tu sesión de usuario para aplicar el grupo
systemctl --user enable --now ydotool
```

### 3. Clonar y Configurar Dependencias Python
```bash
git clone git@github.com:Fernandooxz1/AI-Asistent.git
cd AI-Asistent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ Configuración (`config.json`)

Toda la base de conocimiento y comandos se configuran a través del archivo central `config.json`. Cualquier usuario puede personalizar el asistente añadiendo macros de teclado, juegos de Steam, atajos o correcciones fonéticas.

### Estructura del Archivo
* **`model_name`**: El modelo local a usar en Ollama (ej: `"qwen2.5:3b"`).
* **`whisper_model`**: El modelo local de Whisper para la transcripción (ej: `"medium"` o `"small"`).
* **`keyboard_macros`**: Atajos a nivel hardware. Soporta tipos de ejecución:
  - `"ydotool"`: Envía teclas físicas mediante códigos de teclado (ej: `{"type": "ydotool", "args": ["key", "29:1", "46:1", "46:0", "29:0"]}`).
  - `"comando"`: Dispara comandos de bash genéricos de forma invisible.
* **`phonetics`**: Tabla de reemplazos de coincidencia difusa para sanear palabras mal interpretadas por Whisper antes de enviarlas al LLM.

---

## 🛠️ Guía de Extensibilidad: ¿Cómo modificar o agregar funciones?

El proyecto está estructurado bajo un patrón modular organizado:

```
Viernes/
├── main.py                 # Orquestador del asistente
├── gui.py                  # Interfaz gráfica CustomTkinter
├── core/                   # Módulos del núcleo (audio, intent, dispatcher, web_server)
├── actions/                # Módulos de acción individuales
├── static/                 # Frontend HTML del control remoto web
├── scripts/                # Scripts de compilación y diagnóstico
└── tests/                  # Unit tests del sistema
```

### 1. Agregar una Nueva Macro de Teclado
Simplemente añade la llave y sus acciones en el diccionario `keyboard_macros` en `config.json`. El parser detectará automáticamente la nueva macro de manera semántica o mediante el cortocircuito directo sin requerir tocar el código.

### 2. Crear un Nuevo Módulo de Acción (Plugin)
Todas las acciones heredan y se encuentran en la carpeta [actions/](file:///home/fernandooxz1/Work/tries/Viernes/actions/):
1. Crea un archivo en `actions/mi_nueva_accion.py`.
2. Define una clase (ej. `MiNuevaClaseModule`) con un método `execute(self, entities: dict) -> bool`.
3. Registra tu intención en `config.json`:
   - Agrega tu intención a la lista `"intents"`.
   - Asocia el intent con tu clase en `"intent_mapping"`: `"mi_intencion": "MiNuevaClaseModule"`.
4. En [core/dispatcher.py](file:///home/fernandooxz1/Work/tries/Viernes/core/dispatcher.py), importa estáticamente tu nueva clase dentro del método `_discover_modules` (bajo el bloque `if getattr(sys, 'frozen', False):`) para asegurar compatibilidad al empaquetarse en binario.

### 3. Modificar la Lógica Conversacional o el Buscador Web
- El motor de raspado gratuito y síntesis se encuentra en [actions/conversational_action.py](file:///home/fernandooxz1/Work/tries/Viernes/actions/conversational_action.py).
- Si deseas cambiar las reglas o prompt del sistema de NLP, modifícalos en el prompt de [core/intent_parser.py](file:///home/fernandooxz1/Work/tries/Viernes/core/intent_parser.py).

---

## 🚀 Uso

### Ejecutar en Desarrollo
Asegúrate de que Ollama esté corriendo e inicia:
```bash
python main.py
```
O inicia con la GUI:
```bash
python gui.py
```

### Compilar y Ejecutar en Standalone (PyInstaller)
Para generar un binario independiente comprimido de alta velocidad que no dependa del entorno virtual de Python:
```bash
bash scripts/build_app.sh
```
El ejecutable resultante estará en `dist/viernes/viernes`. Puedes crear un atajo de teclado en tu sistema gráfico para lanzarlo mediante el comando:
```bash
/home/tu_usuario/Ruta/AI-Asistent/dist/viernes/viernes
```

### Ejecutar Pruebas Unitarias
El proyecto cuenta con suites de pruebas automáticas para validar el comportamiento del despachador, del parser de intenciones y de la seguridad del servidor web. Ejecútalas dentro de tu entorno virtual con:
```bash
PYTHONPATH=. venv/bin/pytest tests/
```


---
**Desarrollado con ☕ por Fernando Ortiz.**