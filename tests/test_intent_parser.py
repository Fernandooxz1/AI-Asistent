import unittest
from unittest.mock import MagicMock, patch
from core.intent_parser import IntentParser

class TestIntentParser(unittest.TestCase):

    def setUp(self):
        self.config = {
            "model_name": "llama3",
            "intents": ["abrir_streaming", "buscar_video", "cerrar_ventana", "abrir_aplicacion"],
            "whitelist_apps": ["steam"],
            "keyboard_macros": {
                "cierra la ventana": [
                    {"type": "ydotool", "args": ["key", "-d", "100", "125:1", "17:1", "17:0", "125:0"]}
                ],
                "pausa": [
                    {"type": "ydotool", "args": ["key", "57:1", "57:0"]}
                ]
            },
            "phonetics": {
                "cerrar la ventana": "cierra la ventana"
            }
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

    def test_macro_exact_match_cortocircuito(self):
        # Exact match command should trigger the cortocircuito instantly
        result = self.parser.parse("cierra la ventana")
        self.assertEqual(result[0]["intent"], "automatizacion_teclado")
        self.assertEqual(result[0]["entities"]["macro"], "cierra la ventana")

    def test_macro_phonetic_match_cortocircuito(self):
        # Phonetic match should also map and trigger the cortocircuito
        result = self.parser.parse("cerrar la ventana")
        self.assertEqual(result[0]["intent"], "automatizacion_teclado")
        self.assertEqual(result[0]["entities"]["macro"], "cierra la ventana")

    @patch('ollama.chat')
    def test_macro_hijack_prevention(self, mock_ollama_chat):
        # Specific window targeting should NOT trigger the generic "cierra la ventana" cortocircuito macro
        mock_response = {
            "message": {
                "content": '{"intent": "cerrar_ventana", "entities": {"ventana_query": "notebooklm"}}'
            }
        }
        mock_ollama_chat.return_value = mock_response

        result = self.parser.parse("cierra la ventana de notebooklm")
        self.assertEqual(result[0]["intent"], "cerrar_ventana")
        self.assertEqual(result[0]["entities"]["ventana_query"], "notebooklm")

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

    @patch('ollama.chat')
    def test_workspace_extraction(self, mock_ollama_chat):
        mock_response = {
            "message": {
                "content": '{"intent": "cerrar_ventana", "entities": {"ventana_query": "notebooklm"}}'
            }
        }
        mock_ollama_chat.return_value = mock_response

        # Number as digit
        result = self.parser.parse("cierra la ventana de notebooklm en el workspace 2")
        self.assertEqual(result[0]["intent"], "cerrar_ventana")
        self.assertEqual(result[0]["entities"]["ventana_query"], "notebooklm")
        self.assertEqual(result[0]["entities"]["workspace"], "2")

        # Number as Spanish word
        result_word = self.parser.parse("cierra la ventana de notebooklm en el escritorio dos")
        self.assertEqual(result_word[0]["entities"]["workspace"], "2")

    def test_abri_template_match(self):
        # abrí steam en el workspace 3 should match local template for abrir_aplicacion and have workspace 3
        result = self.parser.parse("abrí steam en el workspace 3")
        self.assertEqual(result[0]["intent"], "abrir_aplicacion")
        self.assertEqual(result[0]["entities"]["programa"], "steam")
        self.assertEqual(result[0]["entities"]["workspace"], "3")

    @patch("actions.game_launcher_action.find_desktop_file_info")
    def test_local_game_desktop_match(self, mock_find):
        mock_find.return_value = {
            "name": "Baldur's Gate III",
            "exec": "steam steam://rungameid/13747480236176441344",
            "score": 100.0
        }
        result = self.parser.parse("jugar al baldur's gate 3")
        self.assertEqual(result[0]["intent"], "lanzar_juego")
        self.assertEqual(result[0]["entities"]["juego"], "Baldur's Gate III")


if __name__ == '__main__':
    unittest.main()

