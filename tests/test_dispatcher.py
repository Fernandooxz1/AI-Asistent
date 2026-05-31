import os
import json
from core.dispatcher import Dispatcher

# 1. Crear un módulo de prueba en actions/
actions_dir = "actions"
if not os.path.exists(actions_dir):
    os.makedirs(actions_dir)

test_module_content = """
class MockActionModule:
    def __init__(self, config=None):
        self.config = config
    def execute(self, entities):
        print(f"--- MÓDULO DE PRUEBA EJECUTADO ---")
        print(f"Entidades recibidas: {entities}")
"""

with open(os.path.join(actions_dir, "test_action.py"), "w") as f:
    f.write(test_module_content)

# 2. Configuración de prueba
config = {
    "intent_mapping": {
        "prueba_intent": "MockActionModule"
    }
}

# 3. Inicializar Dispatcher
print("🚀 Iniciando Dispatcher...")
dispatcher = Dispatcher(actions_dir=actions_dir, config=config)

# 4. Simular un intent detectado
intent_json = {
    "intent": "prueba_intent",
    "entities": {
        "busqueda": "test",
        "accion": "ejecutar"
    }
}

print(f"\nDespachando intent: {intent_json['intent']}")
dispatcher.dispatch(intent_json)

# Limpieza (opcional)
# os.remove(os.path.join(actions_dir, "test_action.py"))
