"""Protocol tests use an isolated TLS mock TV, never a real device or keyring."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version("Soup", "3.0")
from gi.repository import Gio, GLib, Soup
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from network import description_url, local_host, magic_packet, pointer_url
from storage import Preferences
from webos import TIMEOUT, WebOS, fingerprint


def wait_until(predicate, seconds=4):
    context = GLib.MainContext.default()
    end = time.monotonic() + seconds
    while not predicate() and time.monotonic() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.002)
    if not predicate():
        raise AssertionError("Mock TV operation timed out")


class MemoryCredentials:
    def __init__(self, record=None):
        self.record = record or {}
        self.writes = []

    def load(self, host):
        return self.record

    def save(self, host, key, pin):
        self.record = {"key": key, "pin": pin}
        self.writes.append((host, key, pin))


class LocalRulesTest(unittest.TestCase):
    def test_local_addresses_only(self):
        for host in ("127.0.0.1", "8.8.8.8", "192.0.2.1", "::1", "example.com", "0.0.0.0", "192.168.001.1"):
            self.assertFalse(local_host(host), host)
        for octets in ((10, 1, 2, 3), (172, 16, 0, 2), (192, 168, 0, 2), (169, 254, 1, 2)):
            self.assertTrue(local_host(".".join(map(str, octets))))

    def test_pointer_cannot_escape_selected_tv(self):
        host = "192.0.2.1"
        self.assertTrue(pointer_url(f"wss://{host}:3001/pointer", host))
        for url in (f"ws://{host}:3001/pointer", "wss://example.com:3001/",
                    f"wss://{host}:443/", f"wss://user@{host}:3001/", f"wss://{host}:bad/"):
            self.assertFalse(pointer_url(url, host), url)

    def test_discovery_source_validation(self):
        host = ".".join(map(str, (10, 1, 2, 3)))
        self.assertTrue(description_url(f"http://{host}:1234/device.xml", host))
        self.assertFalse(description_url("http://example.com/device.xml", host))
        self.assertFalse(description_url(f"http://user@{host}/device.xml", host))
        self.assertFalse(description_url("http://127.0.0.1/", "127.0.0.1"))

    def test_wake_packet_and_invalid_mac(self):
        packet = magic_packet("00:11:22:33:44:55")
        self.assertEqual(packet, b"\xff" * 6 + bytes.fromhex("001122334455") * 16)
        with self.assertRaises(ValueError):
            magic_packet("not-a-mac")

    def test_preferences_no_credentials_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory) / "config")
            self.assertEqual(preferences.load(), {})
            preferences.save("192.0.2.1", "")
            self.assertEqual(preferences.load(), {"host": "192.0.2.1", "mac": "", "macs": {}})
            mac = ":".join(["00", "11", "22", "33", "44", "55"])
            preferences.save("192.0.2.1", mac)
            preferences.save("192.0.2.2", "")
            self.assertEqual(preferences.load()["macs"], {"192.0.2.1": mac})
            preferences.path.write_text(json.dumps({"host": "192.0.2.3", "mac": mac}))
            self.assertEqual(preferences.load()["macs"], {"192.0.2.3": mac})
            self.assertEqual(preferences.path.stat().st_mode & 0o777, 0o600)
            preferences.path.write_text("invalid")
            with self.assertRaises(RuntimeError):
                preferences.load()

    def test_install_into_isolated_xdg_directory(self):
        with tempfile.TemporaryDirectory(prefix="lg remote ") as directory:
            source = Path(__file__).resolve().parents[1]
            result = subprocess.run([sys.executable, str(source / "install.py")],
                                    env={**os.environ, "XDG_DATA_HOME": directory}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            desktop = Path(directory) / "applications/io.github.lgwebos.Menubar.desktop"
            self.assertIn('Exec=/usr/bin/python3 "', desktop.read_text())
            self.assertTrue((Path(directory) / "lgwebos-menubar/registration.json").is_file())
            subprocess.run(["desktop-file-validate", str(desktop)], check=True)


class ProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Mock TV")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
        pem = cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        cls.certificate = Gio.TlsCertificate.new_from_pem(pem.decode(), -1)

    def setUp(self):
        # Ubuntu's PyGObject still uses Python 3.14's deprecated event-loop policy API.
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"gi\.events")
        self.server = Soup.Server()
        self.server.set_tls_certificate(self.certificate)
        self.server.add_websocket_handler(None, None, None, self.accept)
        self.server.listen_local(0, Soup.ServerListenOptions.HTTPS | Soup.ServerListenOptions.IPV4_ONLY)
        self.port = self.server.get_uris()[0].get_port()
        self.connections, self.requests, self.buttons, self.states = [], [], [], []
        self.credentials = MemoryCredentials()
        self.approvals = []
        self.accept_trust = True
        self.reject_pairing = False
        self.silent = False
        self.bad_pointer = False
        self.force_pairing_prompt = False
        self.client = None
        self.host_patch = patch("webos.local_host", return_value=True)
        self.host_patch.start()

    def tearDown(self):
        if self.client:
            self.client.close()
        for connection in self.connections:
            if connection.get_state() == Soup.WebsocketState.OPEN:
                connection.close(1000, None)
        self.server.disconnect()
        self.host_patch.stop()
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def accept(self, server, message, path, connection, *unused):
        self.connections.append(connection)
        connection.connect("message", lambda ws, kind, data: self.receive(ws, path, bytes(data.get_data())))

    def receive(self, connection, path, raw):
        if path == "/pointer":
            self.buttons.append(raw.decode())
            return
        message = json.loads(raw)
        self.requests.append(message)
        if self.silent:
            return
        ident = message["id"]
        kind, payload = "response", {"returnValue": True}
        if message["type"] == "register":
            if self.reject_pairing:
                connection.send_text(json.dumps({"id": ident, "type": "error", "error": "Pairing rejected"}))
                return
            if not message["payload"].get("client-key") or self.force_pairing_prompt:
                connection.send_text(json.dumps({"id": ident, "type": "response", "payload": {"pairingType": "PROMPT"}}))
            mock_key = "mock-credential"
            kind, payload = "registered", {"client-key": mock_key}
        elif message["uri"].endswith("getPointerInputSocket"):
            payload["socketPath"] = "wss://example.com:3001/" if self.bad_pointer else "wss://127.0.0.1:3001/pointer"
        elif message["uri"].endswith("getVolume"):
            payload.update(volume=25, muted=False)
        elif message["uri"].endswith("getPowerState"):
            payload.update(state="Active")
        elif message["uri"].endswith("denied"):
            payload = {"returnValue": False, "errorText": "Permission denied"}
        connection.send_text(json.dumps({"id": ident, "type": kind, "payload": payload}))

    def connect_client(self, background=False):
        def approve(host, pin):
            self.approvals.append(pin)
            return self.accept_trust

        self.client = WebOS("127.0.0.1", self.credentials, approve, self.states.append)
        original_open = self.client._open
        self.client._open = lambda url, done: original_open(url.replace(":3001/", f":{self.port}/"), done)
        self.client.connect(background=background)
        wait_until(lambda: self.client.ready or self.client.closed)

    def test_pairing_and_volume(self):
        self.connect_client()
        self.assertTrue(self.client.ready, self.states)
        self.assertEqual(self.client.socket.get_keepalive_pong_timeout(), 15)
        self.assertEqual(self.approvals, [fingerprint(self.certificate)])
        self.assertEqual(len(self.credentials.writes), 1)
        self.assertIn("Accept the connection request on your TV…", self.states)
        replies = []
        self.client.request("audio/getVolume", callback=lambda data, error: replies.append((data, error)))
        wait_until(lambda: replies)
        self.assertEqual(replies[0][0]["volume"], 25)
        self.assertIsNone(replies[0][1])

    def test_background_connection_requires_existing_pairing(self):
        self.connect_client(background=True)
        self.assertTrue(self.client.closed)
        self.assertTrue(self.client.background_blocked)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.approvals, [])

    def test_background_connection_uses_saved_credentials_without_prompt(self):
        self.credentials.record = {"key": "saved-mock", "pin": fingerprint(self.certificate)}
        self.connect_client(background=True)
        self.assertTrue(self.client.ready, self.states)
        self.assertEqual(self.approvals, [])

    def test_background_pairing_prompt_is_cancelled(self):
        self.force_pairing_prompt = True
        self.credentials.record = {"key": "saved-mock", "pin": fingerprint(self.certificate)}
        self.connect_client(background=True)
        self.assertTrue(self.client.closed)
        self.assertTrue(self.client.background_blocked)
        self.assertEqual(self.approvals, [])

    def test_macro_reads_power_and_sends_off_over_tls_once(self):
        from macros import AutoOffEngine, AutoOffRule
        self.credentials.record = {"key": "saved-mock", "pin": fingerprint(self.certificate)}
        saved = []
        def factory(host, state):
            self.client = WebOS("127.0.0.1", self.credentials, lambda *_: False, state)
            original_open = self.client._open
            self.client._open = lambda url, done: original_open(url.replace(":3001/", f":{self.port}/"), done)
            return self.client
        rule = AutoOffRule(enabled=True, repeat=False, warn_before_off=False, host=".".join(map(str, (10, 0, 0, 2))))
        engine = AutoOffEngine(rule, factory, saved.append, lambda text: None,
                              now=lambda: datetime(2026, 10, 25, 21, 30))
        try:
            engine.tick()
            wait_until(lambda: any(item.get("uri") == "ssap://system/turnOff" for item in self.requests))
            engine.tick()
            self.assertEqual(len([item for item in self.requests if item.get("uri") == "ssap://system/turnOff"]), 1)
            self.assertEqual(len(saved), 1)
            self.assertFalse(saved[0].repeat)
        finally:
            engine.stop()

    def test_saved_pin_and_key_reconnect_without_prompt(self):
        self.credentials.record = {"key": "saved-mock", "pin": fingerprint(self.certificate)}
        self.connect_client()
        self.assertTrue(self.client.ready, self.states)
        self.assertEqual(self.approvals, [])
        self.assertEqual(self.requests[0]["payload"]["client-key"], "saved-mock")

    def test_changed_certificate_rejected_before_registration(self):
        self.credentials.record = {"key": "saved-mock", "pin": "0" * 64}
        self.connect_client()
        self.assertFalse(self.client.ready)
        self.assertIn("certificate changed", self.states[-1])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.approvals, [])

    def test_powered_off_tv_is_unreachable_for_wake_fallback(self):
        import socket
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.connect_client()
        self.assertTrue(self.client.closed)
        self.assertTrue(self.client.unreachable, self.states)

    def test_declining_trust_does_not_send_pairing(self):
        self.accept_trust = False
        self.connect_client()
        self.assertFalse(self.client.ready)
        self.assertFalse(self.client.unreachable)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.credentials.writes, [])

    def test_pairing_rejected_does_not_persist_trust(self):
        self.reject_pairing = True
        self.connect_client()
        self.assertFalse(self.client.ready)
        self.assertEqual(self.credentials.writes, [])

    def test_pointer_buttons_share_one_secure_channel(self):
        self.connect_client()
        replies = []
        for button in ("UP", "ENTER"):
            self.client.button(button, lambda data, error: replies.append(error))
        wait_until(lambda: len(self.buttons) == 2)
        self.assertEqual(self.buttons, ["type:button\nname:UP\n\n", "type:button\nname:ENTER\n\n"])
        self.assertEqual(replies, [None, None])
        self.assertEqual(len(self.connections), 2)

    def test_foreign_pointer_rejected(self):
        self.bad_pointer = True
        self.connect_client()
        replies = []
        self.client.button("UP", lambda data, error: replies.append(error))
        wait_until(lambda: replies)
        self.assertIn("unsafe", replies[0])
        self.assertEqual(self.buttons, [])

    def test_command_rejection_reported(self):
        self.connect_client()
        replies = []
        self.client.request("test/denied", callback=lambda data, error: replies.append(error))
        wait_until(lambda: replies)
        self.assertEqual(replies, ["Permission denied"])

    def test_disconnect_cancels_pending_requests(self):
        self.connect_client()
        self.silent = True
        replies = []
        self.client.request("audio/getVolume", callback=lambda data, error: replies.append(error))
        self.client.close()
        self.assertEqual(replies, ["Disconnected."])
        self.assertFalse(self.client.pending)

    def test_request_timeout(self):
        self.connect_client()
        self.silent = True
        replies = []
        self.client._exchange({"id": "timeout", "type": "request", "uri": "ssap://audio/getVolume"},
                              lambda data, error: replies.append(error), timeout=1)
        wait_until(lambda: replies)
        self.assertEqual(replies[0], TIMEOUT)
        self.assertFalse(self.client.pending)


if __name__ == "__main__":
    unittest.main()
