import unittest
from unittest.mock import MagicMock, patch
from core.intent_parser import IntentParser

class TestIntentParser(unittest.TestCase):

    def setUp(self):
        self.config = {
            "model_name": "llama3",
            "intents": ["abrir_streaming", "buscar_video"]
        }
        self.parser = IntentParser(self.config)

    def test_validate_intent_json_success(self):
        valid_json = {
            "intent": "abrir_streaming",
            "entities": {"stream_name": "ibai"}
        }
        self.assertTrue(self.parser._validate_intent_json(valid_json))

    def test_validate_intent_json_invalid_intent(self):
        invalid_json = {
            "intent": "borrar_disco_duro",
            "entities": {}
        }
        self.assertFalse(self.parser._validate_intent_json(invalid_json))

    def test_validate_intent_json_missing_keys(self):
        invalid_json = {"only_intent": "abrir_streaming"}
        self.assertFalse(self.parser._validate_intent_json(invalid_json))

    @patch('ollama.chat')
    def test_parse_success(self, mock_ollama_chat):
        # Configurar el mock para que devuelva un JSON válido
        mock_response = {
            "message": {
                "content": '{"intent": "buscar_video", "entities": {"video_query": "gatos"}}'
            }
        }
        mock_ollama_chat.return_value = mock_response

        result = self.parser.parse("busca videos de gatos")
        
        self.assertEqual(result[0]["intent"], "buscar_video")
        self.assertEqual(result[0]["entities"]["video_query"], "gatos")

    @patch('ollama.chat')
    def test_parse_fallback_on_invalid_json(self, mock_ollama_chat):
        # Configurar el mock para que devuelva basura
        mock_response = {
            "message": {
                "content": "Esto no es un JSON"
            }
        }
        mock_ollama_chat.return_value = mock_response

        result = self.parser.parse("comando aleatorio")
        
        self.assertEqual(result[0]["intent"], "desconocido")

if __name__ == '__main__':
    unittest.main()
