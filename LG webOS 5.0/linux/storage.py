"""Desktop preferences and per-TV credentials; never stored in the source tree."""
import json
import os
from pathlib import Path
import tempfile

import gi

gi.require_version("Secret", "1")
from gi.repository import Secret


class Preferences:
    def __init__(self, directory=None):
        self.directory = Path(directory or Path(os.environ.get(
            "XDG_CONFIG_HOME", Path.home() / ".config")) / "lgwebos-menubar")
        self.path = self.directory / "settings.json"

    def load(self):
        try:
            value = json.loads(self.path.read_text())
            if not isinstance(value, dict):
                return {}
            # Older settings held one host and MAC; keep that MAC remembered for its host.
            macs = value.get("macs")
            if not isinstance(macs, dict):
                macs = {value["host"]: value["mac"]} if value.get("host") and value.get("mac") else {}
            value["macs"] = {str(host): str(mac) for host, mac in macs.items() if host and mac}
            return value
        except FileNotFoundError:
            return {}
        except (ValueError, OSError) as error:
            raise RuntimeError("Cannot read TV settings. Check settings.json in the app configuration directory.") from error

    def save(self, host, mac):
        """Save the current TV and remember each TV's wake MAC by address."""
        try:
            macs = self.load().get("macs", {})
        except RuntimeError:
            macs = {}
        if mac:
            macs[host] = mac
        else:
            macs.pop(host, None)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".settings-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"host": host, "mac": mac, "macs": macs}, stream)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


class Credentials:
    schema = Secret.Schema.new("io.github.lgwebos.Menubar", Secret.SchemaFlags.NONE,
                               {"host": Secret.SchemaAttributeType.STRING})

    def load(self, host):
        value = Secret.password_lookup_sync(self.schema, {"host": host}, None)
        if not value:
            return {}
        record = json.loads(value)
        if not isinstance(record, dict) or not all(isinstance(record.get(k), str)
                                                   and record[k] for k in ("key", "pin")):
            raise RuntimeError("Invalid pairing record. Use Forget pairing and reconnect.")
        return record

    def save(self, host, key, pin):
        if not Secret.password_store_sync(
                self.schema, {"host": host}, Secret.COLLECTION_DEFAULT,
                "LG webOS TV pairing", json.dumps({"key": key, "pin": pin}), None):
            raise RuntimeError("Could not save pairing in the desktop keyring.")

    def clear(self, host):
        Secret.password_clear_sync(self.schema, {"host": host}, None)
