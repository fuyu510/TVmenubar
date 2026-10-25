"""Asynchronous SSAP client using the desktop's libsoup WebSocket implementation."""
import hashlib
import json
from pathlib import Path
import uuid

import gi

gi.require_version("Soup", "3.0")
from gi.repository import Gio, GLib, Soup

from network import local_host, pointer_url

TIMEOUT = "The TV took too long to respond."
MANIFEST = Path(__file__).resolve().parent / "registration.json"
if not MANIFEST.exists():
    MANIFEST = Path(__file__).resolve().parents[1] / "Sources/LGwebOSMenubar/registration.json"


def fingerprint(certificate):
    return hashlib.sha256(bytes(certificate.props.certificate)).hexdigest()


class WebOS:
    def __init__(self, host, credentials, approve, state):
        if not local_host(host):
            raise ValueError("Enter the TV's local IPv4 address.")
        self.host, self.credentials, self.approve, self.state = host, credentials, approve, state
        self.session = Soup.Session(timeout=15, user_agent="LGwebOS-menubar/Linux")
        self.session.set_proxy_resolver(Gio.SimpleProxyResolver.new(None, None))
        self.cancel = Gio.Cancellable()
        self.socket = self.pointer = None
        self.pending = {}
        self.closed = False
        self.ready = False
        self.pin = None
        self.saved = {}
        self.trust_error = None
        self.pointer_waiting = []
        self.background = False
        self.background_blocked = False
        self.unreachable = False

    def connect(self, background=False):
        self.background = background
        try:
            self.saved = self.credentials.load(self.host)
            self.pin = self.saved.get("pin")
            if background and not (self.pin and self.saved.get("key")):
                self.background_blocked = True
                raise RuntimeError("Pair this TV once using Connect TV before automatic connections can run.")
            self.state("Connecting…")
            self._open(f"wss://{self.host}:3001/", self._register)
        except Exception as error:
            if background and not self.pin:
                self.background_blocked = True
            self.fail(str(error))

    def _trust(self, certificate):
        digest = fingerprint(certificate)
        if self.pin:
            accepted = self.pin == digest
            if not accepted:
                self.background_blocked = True
                self.trust_error = "The TV certificate changed. Verify the TV before using Forget pairing."
            return accepted
        if not self.background and self.approve(self.host, digest) and not self.closed:
            self.pin = digest
            return True
        self.trust_error = "The TV certificate was not approved."
        return False

    def _open(self, url, callback):
        message = Soup.Message.new("GET", url)
        message.set_flags(Soup.MessageFlags.NO_REDIRECT)
        message.connect("accept-certificate", lambda msg, cert, errors: self._trust(cert))

        def opened(session, result):
            try:
                connection = session.websocket_connect_finish(result)
                if self.closed:
                    connection.close(1000, None)
                    return
                # Also check pins when a certificate is accepted by the system trust store.
                cert = message.get_tls_peer_certificate()
                if cert is None or not self._trust(cert):
                    connection.close(1000, None)
                    raise RuntimeError(self.trust_error or "Missing TV certificate.")
                connection.set_max_incoming_payload_size(2 * 1024 * 1024)
                connection.set_keepalive_interval(20)
                # A TV that powers off often vanishes without closing; notice it within seconds.
                connection.set_keepalive_pong_timeout(15)
                callback(connection)
            except Exception as error:
                if not self.closed:
                    # A network failure before pairing usually means the TV is off.
                    self.unreachable = not self.ready and not self.trust_error and isinstance(error, GLib.Error)
                    self.fail(self.trust_error or f"Connection failed: {error}")

        self.session.websocket_connect_async(message, None, None, GLib.PRIORITY_DEFAULT,
                                             self.cancel, opened)

    def _register(self, connection):
        self.socket = connection
        connection.connect("message", self._message)
        connection.connect("closed", lambda ws: self.fail("Disconnected. Turn on the TV and reconnect."))
        connection.connect("error", lambda ws, error: self.fail("The TV connection was interrupted."))
        payload = json.loads(MANIFEST.read_text())
        if self.saved.get("key"):
            payload["client-key"] = self.saved["key"]
        self._exchange({"type": "register", "id": "register", "payload": payload}, self._registered, 90)

    def _registered(self, payload, error):
        if error:
            if self.background and any(word in error.lower() for word in ("denied", "rejected", "401", "403")):
                self.background_blocked = True
            self.fail(error)
            return
        key = payload.get("client-key") or self.saved.get("key")
        if not isinstance(key, str) or not key or not self.pin:
            self.fail("The TV did not provide a pairing key.")
            return
        try:
            if key != self.saved.get("key") or self.pin != self.saved.get("pin"):
                self.credentials.save(self.host, key, self.pin)
        except Exception:
            self.fail("Could not save pairing. Unlock the desktop keyring and reconnect.")
            return
        self.ready = True
        self.state("Connected")

    def _exchange(self, message, callback, timeout=12):
        ident = message["id"]
        if self.closed or not self.socket or self.socket.get_state() != Soup.WebsocketState.OPEN:
            callback({}, "Connect to the TV first.")
            return

        def expired():
            pending = self.pending.pop(ident, None)
            if pending:
                pending[0]({}, "Pairing timed out. Accept the request on the TV and reconnect."
                           if ident == "register" else TIMEOUT)
            return GLib.SOURCE_REMOVE

        timer = GLib.timeout_add_seconds(timeout, expired)
        self.pending[ident] = (callback, timer)
        self.socket.send_text(json.dumps(message))

    def _message(self, connection, kind, data):
        try:
            message = json.loads(bytes(data.get_data()))
            if not isinstance(message, dict):
                raise ValueError()
            ident = message.get("id")
            if not isinstance(ident, str) or ident not in self.pending:
                return
            if message.get("type") not in ("registered", "response", "error"):
                return
            payload = message.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError()
            if ident == "register" and message.get("type") == "response" and payload.get("returnValue") is not False:
                if self.background:
                    self.background_blocked = True
                    self.fail("The TV needs pairing approval. Use Connect TV to pair manually.")
                    return
                self.state("Accept the connection request on your TV…")
                return
            callback, timer = self.pending.pop(ident)
            GLib.source_remove(timer)
            error = None
            if message.get("type") == "error":
                error = str(message.get("error", "The TV rejected the command."))
            elif payload.get("returnValue") is False:
                error = str(payload.get("errorText", "This command is unavailable on this TV."))
            callback(payload, error)
        except (ValueError, TypeError, UnicodeError):
            self.fail("The TV sent an invalid response.")

    def request(self, uri, payload=None, callback=None):
        callback = callback or (lambda data, error: None)
        if not self.ready:
            callback({}, "Connect to the TV first.")
            return
        self._exchange({"type": "request", "id": str(uuid.uuid4()),
                        "uri": "ssap://" + uri, "payload": payload or {}}, callback)

    def button(self, name, callback):
        if name not in {"UP", "DOWN", "LEFT", "RIGHT", "ENTER", "BACK", "HOME", "MENU",
                        "PLAY", "PAUSE", "STOP", "REWIND", "FASTFORWARD"}:
            callback({}, "Unknown remote button.")
            return
        if self.pointer and self.pointer.get_state() == Soup.WebsocketState.OPEN:
            self.pointer.send_text(f"type:button\nname:{name}\n\n")
            callback({}, None)
            return
        self.pointer_waiting.append((name, callback))
        if len(self.pointer_waiting) > 1:
            return

        def received(payload, error):
            if error or not pointer_url(payload.get("socketPath", ""), self.host):
                self._finish_buttons(error or "The TV returned an unsafe navigation address.")
                return
            self._open(payload["socketPath"], opened)

        def opened(connection):
            self.pointer = connection
            connection.connect("error", lambda ws, err: ws.close(1000, None)
                               if ws.get_state() == Soup.WebsocketState.OPEN else None)
            waiting, self.pointer_waiting = self.pointer_waiting, []
            for button, done in waiting:
                self.button(button, done)

        self.request("com.webos.service.networkinput/getPointerInputSocket", callback=received)

    def _finish_buttons(self, error):
        waiting, self.pointer_waiting = self.pointer_waiting, []
        for _, callback in waiting:
            callback({}, error)

    def fail(self, message):
        if self.closed:
            return
        self.close()
        self.state(message)

    def close(self):
        if self.closed:
            return
        self.closed, self.ready = True, False
        self.cancel.cancel()
        pending, self.pending = self.pending, {}
        for callback, timer in pending.values():
            GLib.source_remove(timer)
            callback({}, "Disconnected.")
        self._finish_buttons("Disconnected.")
        for connection in (self.pointer, self.socket):
            if connection and connection.get_state() == Soup.WebsocketState.OPEN:
                connection.close(1000, None)
        self.session.abort()
