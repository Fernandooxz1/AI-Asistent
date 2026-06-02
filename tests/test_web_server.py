import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
import jwt
import asyncio
import logging


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

class TestWebServerIntegrations(IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset the globals to None before each test
        web_server.fft_processor = None
        web_server.telemetry_task = None
        web_server.log_handler = None
        web_server.download_watcher = None
        web_server.clipboard_watcher = None
        web_server.last_clipboard_value = None
        self.original_broadcast = web_server.manager.broadcast
        web_server.manager.broadcast = MagicMock()

    def tearDown(self):
        web_server.manager.broadcast = self.original_broadcast

    @patch("core.web_server.start_fft_processor")
    @patch("core.web_server.start_telemetry_loop")
    @patch("core.web_server.start_logging_stream")
    @patch("core.web_server.start_download_watcher")
    @patch("core.web_server.start_clipboard_watcher")
    async def test_connect_starts_services_on_first_client(
        self, mock_start_clip, mock_start_dl, mock_start_log, mock_start_telem, mock_start_fft
    ):
        mock_websocket = AsyncMock()
        manager = web_server.ConnectionManager()
        
        # Connect first client
        await manager.connect(mock_websocket)
        self.assertEqual(len(manager.active_connections), 1)
        mock_start_fft.assert_called_once()
        mock_start_telem.assert_called_once()
        mock_start_log.assert_called_once()
        mock_start_dl.assert_called_once()
        mock_start_clip.assert_called_once()

        # Connect second client - shouldn't start them again
        mock_websocket2 = AsyncMock()
        await manager.connect(mock_websocket2)
        self.assertEqual(len(manager.active_connections), 2)
        mock_start_fft.assert_called_once()  # still called only once

    @patch("core.web_server.stop_fft_processor")
    @patch("core.web_server.stop_telemetry_loop")
    @patch("core.web_server.stop_logging_stream")
    @patch("core.web_server.stop_download_watcher")
    @patch("core.web_server.stop_clipboard_watcher")
    async def test_disconnect_stops_services_on_last_client(
        self, mock_stop_clip, mock_stop_dl, mock_stop_log, mock_stop_telem, mock_stop_fft
    ):
        mock_websocket = AsyncMock()
        mock_websocket2 = AsyncMock()
        manager = web_server.ConnectionManager()
        manager.active_connections = [mock_websocket, mock_websocket2]

        # Disconnect first client - shouldn't stop services yet
        manager.disconnect(mock_websocket)
        self.assertEqual(len(manager.active_connections), 1)
        mock_stop_fft.assert_not_called()

        # Disconnect last client - should stop all services
        manager.disconnect(mock_websocket2)
        self.assertEqual(len(manager.active_connections), 0)
        mock_stop_fft.assert_called_once()
        mock_stop_telem.assert_called_once()
        mock_stop_log.assert_called_once()
        mock_stop_dl.assert_called_once()
        mock_stop_clip.assert_called_once()

    @patch("core.web_server.manager.broadcast", new_callable=AsyncMock)
    @patch("core.telemetry.get_system_telemetry")
    async def test_telemetry_loop(self, mock_get_telemetry, mock_broadcast):
        mock_get_telemetry.return_value = {"cpu": {"usage_percent": 10}}
        
        task = asyncio.create_task(web_server.telemetry_loop())
        await asyncio.sleep(0.1)
        task.cancel()
        
        mock_get_telemetry.assert_called()
        mock_broadcast.assert_called_with({"type": "telemetry", "data": mock_get_telemetry.return_value})

    @patch("asyncio.run_coroutine_threadsafe")
    def test_log_handler_broadcasts(self, mock_run_coroutine):
        mock_loop = MagicMock()
        web_server.uvicorn_loop = mock_loop
        
        handler = web_server.WebSocketLogHandler()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test_path",
            lineno=10,
            msg="Hello, world!",
            args=None,
            exc_info=None
        )
        handler.emit(record)
        mock_run_coroutine.assert_called_once()
        args, kwargs = mock_run_coroutine.call_args
        self.assertEqual(args[1], mock_loop)

    @patch("asyncio.run_coroutine_threadsafe")
    def test_download_callback(self, mock_run_coroutine):
        mock_loop = MagicMock()
        web_server.uvicorn_loop = mock_loop
        
        web_server.download_callback("/home/user/Downloads/test_file.zip")
        mock_run_coroutine.assert_called_once()
        args, kwargs = mock_run_coroutine.call_args
        self.assertEqual(args[1], mock_loop)

    @patch("pyperclip.copy")
    def test_clipboard_set_local(self, mock_pyperclip_copy):
        web_server.set_local_clipboard("hello world")
        self.assertEqual(web_server.last_clipboard_value, "hello world")
        mock_pyperclip_copy.assert_called_once_with("hello world")

    @patch("asyncio.run_coroutine_threadsafe")
    def test_handle_clipboard_change_broadcasts(self, mock_run_coroutine):
        mock_loop = MagicMock()
        web_server.uvicorn_loop = mock_loop
        
        # Test change
        web_server.last_clipboard_value = "old"
        web_server.handle_clipboard_change("new")
        self.assertEqual(web_server.last_clipboard_value, "new")
        mock_run_coroutine.assert_called_once()
        args, kwargs = mock_run_coroutine.call_args
        self.assertEqual(args[1], mock_loop)
        
        # Test no change (should be ignored)
        mock_run_coroutine.reset_mock()
        web_server.handle_clipboard_change("new")
        mock_run_coroutine.assert_not_called()

    @patch("pyperclip.paste")
    def test_get_local_clipboard(self, mock_pyperclip_paste):
        mock_pyperclip_paste.return_value = "hello clipboard"
        val = web_server.get_local_clipboard()
        self.assertEqual(val, "hello clipboard")
        mock_pyperclip_paste.assert_called_once()

if __name__ == '__main__':
    unittest.main()
