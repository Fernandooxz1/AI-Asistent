import unittest
from unittest.mock import MagicMock, patch
from intent_parser import IntentParser

class TestIntentParser(unittest.TestCase):

    def setUp(self):
        self.api_key = "fake_key"
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                self.parser = IntentParser(self.api_key)

    def test_init_validation(self):
        with self.assertRaises(ValueError):
            IntentParser("")

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

    @patch('google.generativeai.GenerativeModel')
    def test_parse_success(self, mock_model):
        # Configurar el mock para que devuelva un JSON válido
        mock_response = MagicMock()
        mock_response.text = '{"intent": "buscar_video", "entities": {"video_query": "gatos"}}'
        self.parser.model.generate_content.return_value = mock_response

        result = self.parser.parse("busca videos de gatos")
        
        self.assertEqual(result["intent"], "buscar_video")
        self.assertEqual(result["entities"]["video_query"], "gatos")

    @patch('google.generativeai.GenerativeModel')
    def test_parse_fallback_on_invalid_json(self, mock_model):
        # Configurar el mock para que devuelva basura
        mock_response = MagicMock()
        mock_response.text = "Esto no es un JSON"
        self.parser.model.generate_content.return_value = mock_response

        result = self.parser.parse("comando aleatorio")
        
        self.assertEqual(result["intent"], "error")

if __name__ == '__main__':
    unittest.main()
