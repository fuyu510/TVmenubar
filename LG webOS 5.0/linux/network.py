"""Local-only SSDP discovery and Wake-on-LAN."""
import ipaddress
import json
import re
import socket
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import xml.etree.ElementTree as ET


def local_host(host):
    try:
        ip = ipaddress.IPv4Address(host)
        a, b, _, _ = ip.packed
        return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 169 and b == 254)
    except ipaddress.AddressValueError:
        return False


def pointer_url(url, host):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "wss" and parsed.hostname == host and parsed.port == 3001
                and not parsed.username and not parsed.password and not parsed.fragment)
    except ValueError:
        return False


def description_url(url, sender):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return (local_host(sender) and parsed.scheme == "http" and parsed.hostname == sender
                and not parsed.username and not parsed.password and not parsed.fragment)
    except ValueError:
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def discover(seconds=4):
    message = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n'
               'MAN: "ssdp:discover"\r\nMX: 2\r\n'
               'ST: urn:lge-com:service:webos-second-screen:1\r\n\r\n').encode()
    locations = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.3)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(message, ("239.255.255.250", 1900))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(16384)
            except socket.timeout:
                continue
            for line in data.decode("utf-8", "replace").splitlines():
                key, _, value = line.partition(":")
                if key.lower() == "location" and description_url(value.strip(), sender[0]):
                    locations.add(value.strip())
    opener = build_opener(ProxyHandler({}), NoRedirect())
    devices = {}
    for location in sorted(locations)[:32]:
        try:
            with opener.open(Request(location), timeout=2) as response:
                data = response.read(1048577)
            if len(data) > 1048576:
                continue
            root = ET.fromstring(data)
            values = {e.tag.split("}")[-1]: (e.text or "").strip() for e in root.iter()}
            if "LG" not in values.get("manufacturer", "").upper():
                continue
            host = urlsplit(location).hostname
            devices[host] = {"host": host, "name": values.get("friendlyName", "LG TV"),
                             "model": values.get("modelNumber", "webOS")}
        except (OSError, ValueError, ET.ParseError):
            continue
    return sorted(devices.values(), key=lambda item: item["name"])


def magic_packet(mac):
    if not re.fullmatch(r"[0-9a-fA-F]{2}([:-][0-9a-fA-F]{2}){5}", mac):
        raise ValueError("Enter a MAC address with six pairs of hexadecimal digits.")
    return b"\xff" * 6 + bytes.fromhex(mac.replace(":", "").replace("-", "")) * 16


def find_mac(host):
    """Read only the selected TV's observed LAN neighbour, never guess a MAC."""
    if not local_host(host):
        return None
    try:
        result = subprocess.run(["ip", "-j", "neigh", "show", "to", host],
                                capture_output=True, text=True, timeout=2, check=True)
        records = json.loads(result.stdout)
        candidates = set()
        for record in records:
            if record.get("dst") != host or set(record.get("state", [])) & {"FAILED", "INCOMPLETE"}:
                continue
            mac = record.get("lladdr", "").lower()
            packet = magic_packet(mac)
            address = packet[6:12]
            if address != bytes(6) and not address[0] & 1:
                candidates.add(mac.replace("-", ":"))
        return candidates.pop() if len(candidates) == 1 else None
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return None


def wake(host, mac):
    if not local_host(host):
        raise ValueError("Enter the TV's local IPv4 address.")
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for target in (host, "255.255.255.255"):
            sock.sendto(packet, (target, 9))
