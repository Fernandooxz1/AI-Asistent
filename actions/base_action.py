from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ActionModule(ABC):
    """
    Interfaz base abstracta que todos los módulos de acción deben implementar.

    Define el contrato que el Dispatcher espera para poder invocar cualquier
    módulo de forma uniforme, independientemente de su lógica interna.

    El constructor acepta un diccionario 'config' que corresponde al contenido
    completo de config.json, permitiendo que cada módulo lea sus propios
    parámetros (whitelist_apps, platform_urls, etc.) sin hardcodearlos.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Inicializa el módulo de acción con la configuración global del sistema.

        Args:
            config: Diccionario de configuración proveniente de config.json.
                    Si no se provee, se usa un dict vacío como valor seguro.
        """
        self.config: Dict[str, Any] = config or {}

    @abstractmethod
    def validate_entities(self, entities: Dict[str, Any]) -> bool:
        """
        Valida que las entidades necesarias para ejecutar la acción estén presentes
        y tengan un formato correcto.

        Args:
            entities: Diccionario de entidades extraídas por el IntentParser.

        Returns:
            True si las entidades son válidas, False en caso contrario.
        """
        pass

    @abstractmethod
    def execute(self, entities: Dict[str, Any]) -> bool:
        """
        Ejecuta la acción del módulo utilizando las entidades provistas.

        Args:
            entities: Diccionario de entidades extraídas por el IntentParser.

        Returns:
            True si la ejecución fue exitosa, False en caso de error.
        """
        pass
