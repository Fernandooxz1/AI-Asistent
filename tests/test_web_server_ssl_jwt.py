import os
import shutil
import tempfile
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import jwt

# Cryptography imports for validation
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID

from fastapi import HTTPException
import core.web_server as ws

class TestWebServerSSLAndJWT(IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a temporary directory for certs
        self.tmp_dir = tempfile.mkdtemp()
        self.original_kiro = ws.KIRO_DIR
        self.original_cert = ws.CERT_PATH
        self.original_key = ws.KEY_PATH

        ws.KIRO_DIR = self.tmp_dir
        ws.CERT_PATH = os.path.join(self.tmp_dir, "cert.pem")
        ws.KEY_PATH = os.path.join(self.tmp_dir, "key.pem")

    def tearDown(self):
        # Restore original paths
        ws.KIRO_DIR = self.original_kiro
        ws.CERT_PATH = self.original_cert
        ws.KEY_PATH = self.original_key
        shutil.rmtree(self.tmp_dir)

    @patch("core.web_server.get_lan_ip")
    def test_generate_self_signed_cert_creation(self, mock_get_lan_ip):
        # Case 1: Brand new certificate generation
        mock_get_lan_ip.return_value = "192.168.1.100"
        
        ws.generate_self_signed_cert()
        
        # Verify files were created
        self.assertTrue(os.path.exists(ws.CERT_PATH))
        self.assertTrue(os.path.exists(ws.KEY_PATH))
        ip_txt_path = os.path.join(ws.KIRO_DIR, "cert_ip.txt")
        self.assertTrue(os.path.exists(ip_txt_path))
        
        # Verify IP written is correct
        with open(ip_txt_path, "r") as f:
            self.assertEqual(f.read().strip(), "192.168.1.100")

        # Load and verify certificate details
        with open(ws.CERT_PATH, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)

        # Subject CN validation
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        self.assertEqual(cn, "192.168.1.100")

        # SANs validation
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san_values = san_ext.value
        
        dns_names = [item.value for item in san_values if isinstance(item, x509.DNSName)]
        ip_addresses = [str(item.value) for item in san_values if isinstance(item, x509.IPAddress)]

        self.assertIn("localhost", dns_names)
        self.assertIn("viernes.local", dns_names)
        self.assertIn("192.168.1.100", ip_addresses)

    @patch("core.web_server.get_lan_ip")
    def test_generate_self_signed_cert_no_regeneration_if_same_ip(self, mock_get_lan_ip):
        mock_get_lan_ip.return_value = "192.168.1.100"
        
        ws.generate_self_signed_cert()
        first_mtime = os.path.getmtime(ws.CERT_PATH)
        
        # Call it again with same IP
        ws.generate_self_signed_cert()
        second_mtime = os.path.getmtime(ws.CERT_PATH)
        
        # Should not regenerate (mtime remains exactly the same)
        self.assertEqual(first_mtime, second_mtime)

    @patch("core.web_server.get_lan_ip")
    def test_generate_self_signed_cert_regenerates_on_ip_change(self, mock_get_lan_ip):
        # Generate initially with IP 192.168.1.100
        mock_get_lan_ip.return_value = "192.168.1.100"
        ws.generate_self_signed_cert()
        
        # Change IP to 192.168.1.200
        mock_get_lan_ip.return_value = "192.168.1.200"
        ws.generate_self_signed_cert()
        
        # Verify IP written to cert_ip.txt updated
        ip_txt_path = os.path.join(ws.KIRO_DIR, "cert_ip.txt")
        with open(ip_txt_path, "r") as f:
            self.assertEqual(f.read().strip(), "192.168.1.200")

        # Load cert and verify CN updated
        with open(ws.CERT_PATH, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        self.assertEqual(cn, "192.168.1.200")

    async def test_verify_jwt_token_valid(self):
        # Generate valid token
        payload = {
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "sub": "viernes-remote-client"
        }
        token = jwt.encode(payload, ws.JWT_PRIVATE_KEY, algorithm="RS256")
        
        # Verify token returns the correct payload
        res_payload = await ws.verify_jwt_token(f"Bearer {token}")
        self.assertEqual(res_payload["sub"], "viernes-remote-client")

    async def test_verify_jwt_token_missing_header(self):
        with self.assertRaises(HTTPException) as context:
            await ws.verify_jwt_token(None)
        self.assertEqual(context.exception.status_code, 401)
        self.assertIn("Missing or invalid", context.exception.detail)

    async def test_verify_jwt_token_invalid_format(self):
        with self.assertRaises(HTTPException) as context:
            await ws.verify_jwt_token("InvalidHeaderFormat")
        self.assertEqual(context.exception.status_code, 401)
        self.assertIn("Missing or invalid", context.exception.detail)

    async def test_verify_jwt_token_expired(self):
        # Generate expired token
        payload = {
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            "sub": "viernes-remote-client"
        }
        token = jwt.encode(payload, ws.JWT_PRIVATE_KEY, algorithm="RS256")
        
        with self.assertRaises(HTTPException) as context:
            await ws.verify_jwt_token(f"Bearer {token}")
        self.assertEqual(context.exception.status_code, 401)
        self.assertIn("Signature has expired", context.exception.detail)

    async def test_verify_jwt_token_invalid_signature(self):
        # Generate a token with a different/fake key
        from cryptography.hazmat.primitives.asymmetric import rsa
        fake_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        payload = {
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "sub": "viernes-remote-client"
        }
        token = jwt.encode(payload, fake_private_key, algorithm="RS256")
        
        with self.assertRaises(HTTPException) as context:
            await ws.verify_jwt_token(f"Bearer {token}")
        self.assertEqual(context.exception.status_code, 401)
        self.assertIn("Signature verification failed", context.exception.detail)

if __name__ == "__main__":
    unittest.main()
