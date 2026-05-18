# Guía de Extensibilidad - Asistente de Voz Local

Esta guía te explica cómo extender el asistente de voz con nuevas funcionalidades sin modificar el código core.

## Tabla de Contenidos

1. [Crear un Action_Module](#crear-un-action_module)
2. [Crear un Plugin Completo](#crear-un-plugin-completo)
3. [Agregar Soporte para Nuevos Launchers](#agregar-soporte-para-nuevos-launchers)
4. [Configurar Automatizaciones](#configurar-automatizaciones)
5. [Estructura del Proyecto](#estructura-del-proyecto)
6. [Convenciones y Mejores Prácticas](#convenciones-y-mejores-prácticas)

---

## Crear un Action_Module

Los Action_Modules son la forma más simple de agregar nuevas acciones al asistente.

### Paso 1: Crear el archivo del módulo

Crea un nuevo archivo en `actions/` con el nombre de tu módulo:

```bash
touch actions/mi_nuevo_modulo.py
```

### Paso 2: Implementar la interfaz ActionModule

```python
# actions/mi_nuevo_modulo.py
from abc import ABC, abstractmethod
from typing import Optional

class ActionModule(ABC):
    @abstractmethod
    def execute(self, entities: dict) -> bool:
        pass
    
    @abstractmethod
    def validate_entities(self, entities: dict) -> bool:
        pass

class MiNuevoModulo(ActionModule):
    """
    Descripción de lo que hace tu módulo.
    """
    
    def __init__(self):
        """
        Inicializa el módulo con cualquier configuración necesaria.
        """
        self.nombre = "MiNuevoModulo"
    
    def validate_entities(self, entities: dict) -> bool:
        """
        Valida que las entidades requeridas estén presentes.
        
        Args:
            entities: Diccionario de entidades del Intent_JSON
            
        Returns:
            True si las entidades son válidas
        """
        # Ejemplo: validar que existe la entidad "mi_entidad"
        if entities.get("mi_entidad") is None:
            print("Necesito la entidad 'mi_entidad' para ejecutar esta acción")
            return False
        return True
    
    def execute(self, entities: dict) -> bool:
        """
        Ejecuta la acción del módulo.
        
        Args:
            entities: Diccionario de entidades del Intent_JSON
            
        Returns:
            True si la ejecución fue exitosa
        """
        # Validar entidades primero
        if not self.validate_entities(entities):
            return False
        
        try:
            # Tu lógica aquí
            mi_entidad = entities.get("mi_entidad")
            print(f"Ejecutando acción con: {mi_entidad}")
            
            # Ejemplo: abrir una aplicación
            import subprocess
            subprocess.Popen([mi_entidad])
            
            return True
        except Exception as e:
            print(f"Error al ejecutar {self.nombre}: {e}")
            return False
```

### Paso 3: Registrar el módulo en el Dispatcher

Edita `config.json` para mapear tu nuevo intent al módulo:

```json
{
  "intent_mapping": {
    "mi_nuevo_intent": "MiNuevoModulo",
    "abrir_streaming": "BrowserActionModule",
    ...
  }
}
```

### Paso 4: Actualizar el prompt de Gemini

Edita `intent_parser.py` para incluir tu nuevo intent en el prompt:

```python
prompt = f"""
...
Clasifica el comando en una de estas intenciones:
- mi_nuevo_intent: Descripción de cuándo usar este intent
- abrir_streaming: El usuario quiere abrir un stream en vivo
...

Extrae las siguientes entidades si están presentes:
- mi_entidad: descripción de la entidad
...
"""
```

---

## Crear un Plugin Completo

Los plugins son más potentes que los Action_Modules porque pueden registrar múltiples intents y tener su propia configuración.

### Paso 1: Crear la estructura del plugin

```bash
mkdir -p plugins/mi-plugin
touch plugins/mi-plugin/__init__.py
touch plugins/mi-plugin/plugin.py
touch plugins/mi-plugin/config.json
```

### Paso 2: Implementar la interfaz Plugin

```python
# plugins/mi-plugin/plugin.py
from abc import ABC, abstractmethod
from typing import Optional

class Plugin(ABC):
    @abstractmethod
    def get_plugin_id(self) -> str:
        pass
    
    @abstractmethod
    def register_intents(self) -> list:
        pass
    
    @abstractmethod
    def register_entities(self) -> dict:
        pass
    
    @abstractmethod
    def execute(self, intent_json: dict) -> bool:
        pass
    
    @abstractmethod
    def validate_config(self, config: dict) -> bool:
        pass
    
    def get_api_access(self) -> dict:
        pass

class MiPlugin(Plugin):
    """
    Plugin de ejemplo que agrega funcionalidad personalizada.
    """
    
    def __init__(self):
        self.config = None
        self.api_access = None
    
    def get_plugin_id(self) -> str:
        """
        Retorna el ID único del plugin.
        """
        return "mi-plugin"
    
    def register_intents(self) -> list:
        """
        Registra los intents que este plugin maneja.
        """
        return [
            "mi_intent_1",
            "mi_intent_2",
            "mi_intent_3"
        ]
    
    def register_entities(self) -> dict:
        """
        Registra las entidades que este plugin utiliza.
        """
        return {
            "entidad_1": "string",
            "entidad_2": "string",
            "parametro_opcional": "string"
        }
    
    def validate_config(self, config: dict) -> bool:
        """
        Valida la configuración del plugin.
        """
        required_fields = ["api_key", "endpoint"]
        for field in required_fields:
            if field not in config.get("settings", {}):
                print(f"Falta el campo requerido: {field}")
                return False
        return True
    
    def execute(self, intent_json: dict) -> bool:
        """
        Ejecuta la acción del plugin basándose en el intent.
        """
        intent = intent_json.get("intent")
        entities = intent_json.get("entities", {})
        
        # Enrutar a la función apropiada según el intent
        if intent == "mi_intent_1":
            return self._handle_intent_1(entities)
        elif intent == "mi_intent_2":
            return self._handle_intent_2(entities)
        elif intent == "mi_intent_3":
            return self._handle_intent_3(entities)
        else:
            print(f"Intent no reconocido: {intent}")
            return False
    
    def _handle_intent_1(self, entities: dict) -> bool:
        """
        Maneja el intent_1.
        """
        try:
            # Acceder a servicios core si es necesario
            if self.api_access:
                fuzzy_matcher = self.api_access.get("fuzzy_matcher")
                app_discovery = self.api_access.get("app_discovery")
            
            # Tu lógica aquí
            entidad_1 = entities.get("entidad_1")
            print(f"Ejecutando intent_1 con: {entidad_1}")
            
            return True
        except Exception as e:
            print(f"Error en intent_1: {e}")
            return False
    
    def _handle_intent_2(self, entities: dict) -> bool:
        """
        Maneja el intent_2.
        """
        # Implementación similar
        pass
    
    def _handle_intent_3(self, entities: dict) -> bool:
        """
        Maneja el intent_3.
        """
        # Implementación similar
        pass
```

### Paso 3: Crear el archivo de configuración

```json
// plugins/mi-plugin/config.json
{
  "plugin_id": "mi-plugin",
  "enabled": true,
  "intents": ["mi_intent_1", "mi_intent_2", "mi_intent_3"],
  "entities": {
    "entidad_1": "string",
    "entidad_2": "string",
    "parametro_opcional": "string"
  },
  "settings": {
    "api_key": "tu_api_key_aqui",
    "endpoint": "https://api.ejemplo.com",
    "timeout": 10
  }
}
```

### Paso 4: Crear el __init__.py

```python
# plugins/mi-plugin/__init__.py
from .plugin import MiPlugin

# Exportar la clase del plugin
__all__ = ['MiPlugin']
```

### Paso 5: El Plugin_Registry lo descubrirá automáticamente

El sistema descubrirá y cargará tu plugin automáticamente al iniciar. No necesitas modificar ningún archivo core.

---

## Agregar Soporte para Nuevos Launchers

Si querés agregar soporte para un nuevo launcher de juegos (ej: Battle.net, Ubisoft Connect, EA App):

### Paso 1: Extender App_Discovery_Module

Edita `app_discovery_module.py` y agrega un método de escaneo:

```python
def _scan_battlenet_library(self) -> list:
    """
    Escanea directorios de Battle.net para encontrar juegos instalados.
    
    Returns:
        Lista de aplicaciones encontradas
    """
    applications = []
    
    # Ruta típica de Battle.net
    battlenet_path = os.path.expandvars(r"%PROGRAMFILES(X86)%\Battle.net")
    
    if not os.path.exists(battlenet_path):
        return applications
    
    try:
        # Buscar archivos .agent (Battle.net usa este formato)
        for root, dirs, files in os.walk(battlenet_path):
            for file in files:
                if file.endswith(".agent"):
                    # Parsear el archivo para extraer info del juego
                    agent_file = os.path.join(root, file)
                    game_info = self._parse_battlenet_agent(agent_file)
                    
                    if game_info:
                        applications.append({
                            "name": game_info["name"],
                            "executable_path": game_info["exe_path"],
                            "launcher_type": "battlenet",
                            "install_dir": game_info["install_dir"],
                            "app_id": game_info["product_code"]
                        })
    except Exception as e:
        print(f"Error escaneando Battle.net: {e}")
    
    return applications

def _parse_battlenet_agent(self, agent_file: str) -> Optional[dict]:
    """
    Parsea un archivo .agent de Battle.net para extraer info del juego.
    """
    try:
        with open(agent_file, 'r', encoding='utf-8') as f:
            # Battle.net usa formato JSON en archivos .agent
            import json
            data = json.load(f)
            
            return {
                "name": data.get("product_name", "Unknown"),
                "exe_path": data.get("launch_path", ""),
                "install_dir": os.path.dirname(agent_file),
                "product_code": data.get("product_code", "")
            }
    except Exception as e:
        print(f"Error parseando {agent_file}: {e}")
        return None
```

### Paso 2: Actualizar build_index()

Agrega la llamada al nuevo método de escaneo:

```python
def build_index(self) -> dict:
    """
    Construye el índice completo de aplicaciones.
    """
    applications = []
    
    # Escanear todas las fuentes
    applications.extend(self._scan_steam_library())
    applications.extend(self._scan_epic_library())
    applications.extend(self._scan_gog_library())
    applications.extend(self._scan_battlenet_library())  # NUEVO
    applications.extend(self._scan_windows_apps())
    
    return {
        "applications": applications,
        "last_updated": datetime.now().isoformat(),
        "total_count": len(applications)
    }
```

### Paso 3: Actualizar Game_Launcher_Module

Agrega el comando de lanzamiento para el nuevo launcher:

```python
class GameLauncherModule(ActionModule):
    LAUNCHER_COMMANDS = {
        "steam": "steam://rungameid/{app_id}",
        "epic": "com.epicgames.launcher://apps/{app_id}?action=launch",
        "gog": "{executable_path}",
        "battlenet": "battlenet://{app_id}"  # NUEVO
    }
    
    # ... resto del código
```

---

## Configurar Automatizaciones

Las automatizaciones te permiten crear secuencias de acciones que se ejecutan con un solo comando de voz.

### Estructura de automations.json

```json
{
  "sequences": {
    "nombre_de_la_secuencia": {
      "description": "Descripción de lo que hace",
      "parameters": ["param1", "param2"],  // Opcional
      "actions": [
        // Lista de acciones
      ]
    }
  }
}
```

### Tipos de Acciones Disponibles

#### 1. wait - Esperar

```json
{
  "type": "wait",
  "duration": 2.5  // Segundos
}
```

#### 2. press_key - Presionar Tecla

```json
{
  "type": "press_key",
  "key": "space"  // Tecla individual
}

{
  "type": "press_key",
  "key": "ctrl+c"  // Combinación de teclas
}

{
  "type": "press_key",
  "key": "volumeup",
  "repeat": 5  // Repetir 5 veces
}
```

**Teclas especiales soportadas:**
- `space`, `enter`, `tab`, `esc`, `backspace`, `delete`
- `up`, `down`, `left`, `right`
- `home`, `end`, `pageup`, `pagedown`
- `f1` a `f12`
- `volumeup`, `volumedown`, `volumemute`
- `ctrl`, `alt`, `shift`, `win` (para combinaciones)

#### 3. type_text - Escribir Texto

```json
{
  "type": "type_text",
  "text": "Hola mundo"
}

{
  "type": "type_text",
  "text": "{search_term}",  // Parámetro inyectable
  "interval": 0.1  // Intervalo entre teclas (opcional)
}
```

#### 4. click - Click del Mouse

```json
{
  "type": "click",
  "x": 500,
  "y": 300,
  "button": "left"  // "left", "right", "middle"
}

{
  "type": "click",
  "x": 500,
  "y": 300,
  "clicks": 2  // Doble click
}
```

#### 5. open_app - Abrir Aplicación

```json
{
  "type": "open_app",
  "app": "notepad"  // Usa App_Discovery_Module
}

{
  "type": "open_app",
  "app": "{app_name}"  // Parámetro inyectable
}
```

### Ejemplos Completos

#### Ejemplo 1: Abrir Winamp y Reproducir

```json
{
  "sequences": {
    "reproducir_winamp": {
      "description": "Abre Winamp y presiona play",
      "actions": [
        {
          "type": "open_app",
          "app": "winamp"
        },
        {
          "type": "wait",
          "duration": 2.0
        },
        {
          "type": "press_key",
          "key": "space"
        }
      ]
    }
  }
}
```

**Comando de voz:** "Hey asistente, ejecuta reproducir winamp"

#### Ejemplo 2: Buscar en Navegador

```json
{
  "sequences": {
    "buscar_en_navegador": {
      "description": "Abre el navegador y busca un término",
      "parameters": ["search_term"],
      "actions": [
        {
          "type": "press_key",
          "key": "win+r"
        },
        {
          "type": "wait",
          "duration": 0.5
        },
        {
          "type": "type_text",
          "text": "chrome"
        },
        {
          "type": "press_key",
          "key": "enter"
        },
        {
          "type": "wait",
          "duration": 3.0
        },
        {
          "type": "press_key",
          "key": "ctrl+l"
        },
        {
          "type": "type_text",
          "text": "{search_term}"
        },
        {
          "type": "press_key",
          "key": "enter"
        }
      ]
    }
  }
}
```

**Comando de voz:** "Hey asistente, automatiza buscar en navegador python tutorial"

#### Ejemplo 3: Abrir Juego de Steam

```json
{
  "sequences": {
    "lanzar_re8": {
      "description": "Lanza Resident Evil 8 desde Steam",
      "actions": [
        {
          "type": "open_app",
          "app": "steam"
        },
        {
          "type": "wait",
          "duration": 5.0
        },
        {
          "type": "press_key",
          "key": "ctrl+f"
        },
        {
          "type": "type_text",
          "text": "Resident Evil Village"
        },
        {
          "type": "wait",
          "duration": 1.0
        },
        {
          "type": "press_key",
          "key": "enter"
        },
        {
          "type": "wait",
          "duration": 2.0
        },
        {
          "type": "press_key",
          "key": "enter"
        }
      ]
    }
  }
}
```

**Comando de voz:** "Hey asistente, ejecuta lanzar re8"

#### Ejemplo 4: Control de Volumen

```json
{
  "sequences": {
    "subir_volumen": {
      "description": "Sube el volumen del sistema",
      "actions": [
        {
          "type": "press_key",
          "key": "volumeup",
          "repeat": 10
        }
      ]
    },
    "bajar_volumen": {
      "description": "Baja el volumen del sistema",
      "actions": [
        {
          "type": "press_key",
          "key": "volumedown",
          "repeat": 10
        }
      ]
    },
    "mutear": {
      "description": "Mutea el sistema",
      "actions": [
        {
          "type": "press_key",
          "key": "volumemute"
        }
      ]
    }
  }
}
```

---

## Estructura del Proyecto

```
asistente-voz-local/
├── main.py                      # Orquestador principal
├── config.json                  # Configuración general
├── app_index.json              # Índice de aplicaciones (generado)
├── automations.json            # Secuencias de automatización
├── EXTENSIBILITY_GUIDE.md      # Esta guía
├── README.md                   # Documentación del proyecto
│
├── audio_listener.py           # Captura de audio
├── intent_parser.py            # Clasificación con Gemini
├── dispatcher.py               # Enrutamiento de intents
│
├── app_discovery_module.py     # Descubrimiento de apps
├── fuzzy_matcher.py            # Matching inteligente
├── automation_module.py        # Ejecución de automatizaciones
├── plugin_registry.py          # Gestión de plugins
│
├── actions/                    # Action Modules
│   ├── __init__.py
│   ├── browser_actions.py
│   ├── system_actions.py
│   ├── game_launcher.py
│   ├── app_launcher.py
│   └── automation_actions.py
│
└── plugins/                    # Plugins extensibles
    ├── ejemplo-plugin/
    │   ├── __init__.py
    │   ├── plugin.py
    │   └── config.json
    │
    └── spotify-control/
        ├── __init__.py
        ├── plugin.py
        └── config.json
```

---

## Convenciones y Mejores Prácticas

### Nombres de Archivos

- **Action Modules**: `snake_case.py` (ej: `game_launcher.py`)
- **Plugins**: `kebab-case/` (ej: `spotify-control/`)
- **Clases**: `PascalCase` (ej: `GameLauncherModule`)
- **Funciones**: `snake_case` (ej: `execute_sequence`)

### Manejo de Errores

Siempre captura excepciones y proporciona mensajes claros:

```python
try:
    # Tu código
    pass
except SpecificException as e:
    print(f"Error específico: {e}")
    return False
except Exception as e:
    print(f"Error inesperado: {e}")
    return False
```

### Logging

Usa logging en lugar de print para debugging:

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Información general")
logger.warning("Advertencia")
logger.error("Error")
logger.debug("Debug (solo en modo desarrollo)")
```

### Validación de Entidades

Siempre valida entidades antes de usarlas:

```python
def validate_entities(self, entities: dict) -> bool:
    required = ["entidad_1", "entidad_2"]
    for field in required:
        if entities.get(field) is None:
            print(f"Falta la entidad requerida: {field}")
            return False
    return True
```

### Documentación

Documenta tus funciones con docstrings:

```python
def mi_funcion(param1: str, param2: int) -> bool:
    """
    Descripción breve de la función.
    
    Args:
        param1: Descripción del parámetro 1
        param2: Descripción del parámetro 2
        
    Returns:
        True si la operación fue exitosa, False en caso contrario
        
    Raises:
        ValueError: Si param2 es negativo
    """
    pass
```

### Testing

Crea tests para tus módulos:

```python
# tests/test_mi_modulo.py
import pytest
from actions.mi_modulo import MiModulo

def test_validate_entities():
    module = MiModulo()
    
    # Test con entidades válidas
    valid_entities = {"entidad_1": "valor"}
    assert module.validate_entities(valid_entities) == True
    
    # Test con entidades inválidas
    invalid_entities = {}
    assert module.validate_entities(invalid_entities) == False

def test_execute():
    module = MiModulo()
    entities = {"entidad_1": "test"}
    
    result = module.execute(entities)
    assert result == True
```

---

## Ejemplos de Casos de Uso

### Caso 1: Control de Spotify

Crear un plugin que controle Spotify:

1. Crear `plugins/spotify-control/`
2. Implementar intents: `reproducir_musica`, `pausar_musica`, `siguiente_cancion`
3. Usar la API de Spotify para control
4. Configurar credenciales en `config.json`

### Caso 2: Automatización de Trabajo

Crear secuencias para tareas repetitivas:

```json
{
  "sequences": {
    "abrir_entorno_trabajo": {
      "description": "Abre todas las apps de trabajo",
      "actions": [
        {"type": "open_app", "app": "vscode"},
        {"type": "wait", "duration": 2},
        {"type": "open_app", "app": "chrome"},
        {"type": "wait", "duration": 2},
        {"type": "open_app", "app": "slack"}
      ]
    }
  }
}
```

### Caso 3: Control de Smart Home

Crear un plugin que controle dispositivos smart home:

1. Implementar intents: `encender_luz`, `apagar_luz`, `cambiar_temperatura`
2. Integrar con API de Home Assistant o similar
3. Mapear comandos de voz a acciones de dispositivos

---

## Soporte y Contribuciones

Si tenés dudas o querés contribuir:

1. Revisa la documentación en `README.md`
2. Consulta los ejemplos en `plugins/ejemplo-plugin/`
3. Abre un issue en el repositorio
4. Contribuye con pull requests

---

## Recursos Adicionales

- **PyAutoGUI Documentation**: https://pyautogui.readthedocs.io/
- **Gemini API Documentation**: https://ai.google.dev/docs
- **Speech Recognition Library**: https://pypi.org/project/SpeechRecognition/
- **FuzzyWuzzy**: https://github.com/seatgeek/fuzzywuzzy

---

¡Feliz coding! 🚀
