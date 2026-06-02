
class MockActionModule:
    def __init__(self, config=None):
        self.config = config
    def execute(self, entities):
        print(f"--- MÓDULO DE PRUEBA EJECUTADO ---")
        print(f"Entidades recibidas: {entities}")
