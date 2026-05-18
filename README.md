# 🤖 Viernes (AI-Asistent)

Viernes es un asistente de voz inteligente, rápido y 100% local diseñado específicamente para entornos Linux con Wayland (como Hyprland u Omarchy). Utiliza el poder de **Ollama (Llama 3)** para el procesamiento de lenguaje natural (NLP) y ejecuta automatizaciones de sistema y teclado a nivel de hardware.

A diferencia de los asistentes comerciales, Viernes no depende de la nube, respeta tu privacidad y tiene la capacidad de saltarse las restricciones de Wayland interactuando directamente con el Kernel de Linux a través de `/dev/uinput`.

## ✨ Características Principales

* **🧠 Procesamiento Local:** Entiende lenguaje natural usando modelos de lenguaje locales mediante Ollama.
* **⚡ Cortocircuito de Macros:** Sistema de reflejos instantáneos que bypasea la IA para comandos críticos (pausa, pantalla completa) ejecutándolos en milisegundos.
* **⌨️ Automatización a Nivel Hardware:** Utiliza `ydotool` para inyectar eventos de teclado reales, evitando bloqueos de los compositores de ventanas.
* **🎵 Control de Procesos en Segundo Plano:** Integración nativa con `tmux` para enviar comandos a reproductores de terminal (como `cliamp`) sin necesidad de cambiar de escritorio ni perder el foco.
* **🛡️ Sanitización Fonética:** Corrección automática de palabras mal interpretadas por el micrófono antes de ser procesadas por el LLM.
* **🧹 Cierre Limpio (Graceful Exit):** Capacidad de purgar la VRAM liberando los procesos de Ollama por completo al cerrarse con un simple comando de voz.

## 🛠️ Tecnologías Utilizadas

* **Lenguaje:** Python 3
* **IA:** Ollama (Llama 3)
* **Automatización:** `ydotool`, `hyprctl`, `tmux`
* **SO Objetivo:** Arch Linux / CachyOS (Wayland)

## 📦 Instalación y Requisitos

### 1. Dependencias del Sistema
Asegúrate de tener instalado Python, Ollama, tmux y ydotool:
```bash
sudo pacman -S python ollama tmux ydotool
```

### 2. Configuración de ydotool (Importante para Wayland)
Viernes simula hardware real para evitar problemas de permisos. Necesitas agregarte al grupo `input` y habilitar el servicio de usuario:
```bash
sudo usermod -aG input $USER
# Reinicia tu sesión o PC antes de continuar
systemctl --user enable --now ydotool
```

### 3. Clonar el repositorio
```bash
git clone git@github.com:Fernandooxz1/AI-Asistent.git
cd AI-Asistent
```

### 4. Entorno Virtual (Opcional pero recomendado)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## ⚙️ Configuración (`config.json`)

Viernes es completamente modular. Todas sus acciones y atajos se definen en un archivo `config.json` en la raíz del proyecto.

**Ejemplo de estructura de Macros:**
```json
{
  "keyboard_macros": {
    "pantalla completa": [
      {"type": "ydotool", "args": ["key", "125:1", "33:1", "33:0", "125:0"]}
    ],
    "modo cine": [
      {"type": "ydotool", "args": ["type", "t"]}
    ],
    "pausa la musica": [
      {"type": "comando", "args": ["tmux", "send-keys", "-t", "reproductor", "space"]}
    ],
    "adios viernes": [
      {"type": "comando", "args": ["pkill", "-f", "ollama"]},
      {"type": "comando", "args": ["pkill", "-f", "kirito"]}
    ]
  }
}
```
*(Nota: Viernes entiende dinámicamente estos comandos de voz basándose en las llaves del JSON).*

## 🚀 Uso

Asegúrate de que el servidor de Ollama esté corriendo en segundo plano:
```bash
systemctl start ollama
```

Inicia el asistente:
```bash
./dist/kirito
```
*(O ejecuta `python main.py` si estás en el entorno de desarrollo).*

Di la palabra de activación (por defecto: **"Viernes"**) seguida de tu comando, por ejemplo:
* *"Viernes, abrí el navegador"*
* *"Viernes, tengo ganas de jugar al Hytale"*
* *"Viernes, pausa la música"*
* *"Viernes, adiós viernes"*

## 📝 Estructura del Proyecto

* `intent_parser.py`: Motor de NLP que conecta con Llama 3 local y maneja el "bypass" de macros de alta velocidad.
* `actions/`: Módulos de ejecución separados por dominio (sistema, teclado, juegos).
* `config.json`: Base de datos de macros, fonética e intenciones permitidas.
* `build_app.sh`: Script para compilar el proyecto en un binario independiente usando PyInstaller.

## 🤝 Contribuciones

¡Las contribuciones (Pull Requests, Reportes de Bugs) son bienvenidas! Si usas un gestor de ventanas distinto, siéntete libre de adaptar los comandos en el JSON a las necesidades de tu entorno.

---
**Desarrollado con ☕ por Fernando Ortiz.**