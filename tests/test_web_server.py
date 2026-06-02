import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
import jwt

# Set environment variable or paths before importing if needed
from core import web_server
from core.web_server import app, JWT_PUBLIC_KEY

class TestWebServerAuth(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        # Mock the assistant instance
        self.mock_assistant = MagicMock()
        self.mock_assistant.pair_token = "super_secret_token"
        self.mock_assistant.pair_pin = "123456"
        web_server.assistant_instance = self.mock_assistant

    def tearDown(self):
        web_server.assistant_instance = None

    def test_auth_pair_missing_param(self):
        # Both parameters are optional in FastAPI signature, but returns 400 if both are missing
        response = self.client.get("/auth/pair")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Missing pairing token or PIN"})

    def test_auth_pair_invalid_token(self):
        response = self.client.get("/auth/pair?pair_token=wrong_token")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid pairing token or PIN"})

    def test_auth_pair_pin_success(self):
        response = self.client.get("/auth/pair?pair_pin=123456")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        token = data["token"]
        decoded = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])
        self.assertEqual(decoded["sub"], "viernes-remote-client")

    def test_auth_pair_success(self):
        response = self.client.get("/auth/pair?pair_token=super_secret_token")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("token", data)
        
        # Verify the token is a valid JWT signed with RS256 and has correct fields
        token = data["token"]
        decoded = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])
        self.assertEqual(decoded["sub"], "viernes-remote-client")
        self.assertIn("exp", decoded)

    def test_ws_connection_no_token(self):
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws") as websocket:
                pass

    def test_ws_connection_invalid_token(self):
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws?token=invalid") as websocket:
                pass

    def test_ws_connection_success(self):
        # Generate a valid token
        response = self.client.get("/auth/pair?pair_token=super_secret_token")
        token = response.json()["token"]
        
        async def fake_connect(websocket):
            await websocket.accept()
            
        with patch.object(web_server.manager, 'connect', fake_connect):
            with self.client.websocket_connect(f"/ws?token={token}") as websocket:
                # If we get here, connection was accepted and verified
                pass

    def test_get_config_unauthorized(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 401)

    def test_get_config_authorized(self):
        # Configure mock config data
        self.mock_assistant.config = {
            "keyboard_macros": {"test_macro": [{"type": "ydotool", "args": ["key", "1:1"]}]},
            "phonetics": {"test_phonetic": "test_macro"},
            "whitelist_apps": ["brave"],
            "games": {"game_name": {"platform": "steam", "id": "123"}}
        }
        # Generate valid token
        token_response = self.client.get("/auth/pair?pair_token=super_secret_token")
        token = token_response.json()["token"]
        
        response = self.client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["keyboard_macros"], self.mock_assistant.config["keyboard_macros"])
        self.assertEqual(data["phonetics"], self.mock_assistant.config["phonetics"])
        self.assertEqual(data["whitelist_apps"], self.mock_assistant.config["whitelist_apps"])
        self.assertEqual(data["games"], self.mock_assistant.config["games"])

    def test_post_config_unauthorized(self):
        response = self.client.post("/api/config", json={})
        self.assertEqual(response.status_code, 401)

    @patch("builtins.open")
    @patch("json.load")
    @patch("json.dump")
    def test_post_config_authorized_success(self, mock_json_dump, mock_json_load, mock_open):
        # Configure mock load data
        mock_json_load.return_value = {
            "model_name": "qwen2.5:3b",
            "keyboard_macros": {},
            "phonetics": {},
            "whitelist_apps": [],
            "games": {}
        }
        self.mock_assistant.config_path = "dummy_config.json"
        
        # Generate valid token
        token_response = self.client.get("/auth/pair?pair_token=super_secret_token")
        token = token_response.json()["token"]
        
        new_data = {
            "keyboard_macros": {"macro1": [{"type": "ydotool", "args": ["key", "1:1"]}]},
            "phonetics": {"variant1": "macro1"},
            "whitelist_apps": ["brave"],
            "games": {"game1": {"platform": "steam", "id": "999"}}
        }
        
        response = self.client.post("/api/config", json=new_data, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})
        
        # Verify JSON dump was called and assistant hot-reloading was triggered
        self.mock_assistant.reload_config.assert_called_once()

if __name__ == '__main__':
    unittest.main()
