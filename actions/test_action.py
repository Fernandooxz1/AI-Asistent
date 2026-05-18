
class MockActionModule:
    def execute(self, entities):
        print(f"--- MÓDULO DE PRUEBA EJECUTADO ---")
        print(f"Entidades recibidas: {entities}")
