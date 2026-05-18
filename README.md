# Kiro: Asistente de Voz Local (Python)

Kiro es un asistente de voz modular diseñado para ejecutarse localmente, permitiendo el control del sistema, automatización de tareas y navegación web mediante comandos de voz en español. Utiliza la API de Google Gemini para el procesamiento de lenguaje natural y detección de intenciones.

## 🚀 Características Principales

- **Privacidad**: Procesamiento local de voz y comandos.
- **Modularidad**: Sistema de plugins y acciones extensible.
- **Inteligencia**: Integración con Gemini AI para comprensión contextual.
- **Automatización**: Control de interfaz gráfica y comandos de sistema.

## 📂 Estructura del Proyecto

```text
Kiro/
├── actions/        # Módulos de ejecución de comandos (Browser, System, etc.)
├── plugins/        # Extensiones de funcionalidades adicionales
├── tests/          # Suite de pruebas unitarias e integrales
├── config.json     # Configuración global del asistente
├── .env            # Variables de entorno (API Keys)
├── requirements.txt # Dependencias del proyecto
└── README.md       # Documentación principal
```

## 🛠️ Instalación

### Requisitos Previos

- Python 3.10+
- PortAudio (requerido para `pyaudio`)
  - **Linux (Ubuntu/Debian)**: `sudo apt-get install python3-pyaudio portaudio19-dev`
  - **Windows**: Se instala automáticamente vía pip.

### Configuración del Entorno

1. **Clonar o crear el directorio del proyecto**:
   ```bash
   mkdir Kiro
   cd Kiro
   ```

2. **Crear y activar un entorno virtual**:
   ```bash
   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate

   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

## ⚙️ Configuración

1. **API Key**: 
   Copia el archivo `.env.example` a `.env` y añade tu `GEMINI_API_KEY`.
   ```bash
   cp .env.example .env
   ```
   *Puedes obtener una clave gratuita en [Google AI Studio](https://aistudio.google.com/app/apikey).*

2. **Ajustes Personalizados**:
   Edita `config.json` para cambiar la palabra de activación (*wake word*), el idioma o los mapeos de intenciones.

## 🧪 Pruebas

Para ejecutar la suite de pruebas:
```bash
pytest
```

---
**Desarrollado con ❤️ para la comunidad de automatización local.**
