#!/usr/bin/python3
"""LG webOS remote for Linux desktops with an optional AppIndicator tray."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime


def dependencies():
    try:
        import gi
        for name, version in (("Gtk", "3.0"), ("Soup", "3.0"), ("Secret", "1")):
            gi.require_version(name, version)
    except (ImportError, ValueError) as error:
        raise SystemExit("Missing desktop libraries. On Ubuntu/Debian install:\n"
                         "sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-soup-3.0 "
                         "gir1.2-secret-1 gir1.2-ayatanaappindicator3-0.1 glib-networking\n"
                         + str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="Find TVs without connecting or pairing")
    parser.add_argument("--check", action="store_true", help="Check required desktop libraries")
    parser.add_argument("--smoke-test", action="store_true", help="Open the UI for two seconds, without saved settings or network activity")
    parser.add_argument("--screenshot", type=Path, help="Save a window image during --smoke-test")
    parser.add_argument("--preview", choices=("remote", "apps", "macros", "settings"), help="Show sample content during --smoke-test")
    args = parser.parse_args()
    if (args.screenshot or args.preview) and not args.smoke_test:
        parser.error("--screenshot and --preview require --smoke-test")
    dependencies()
    if args.check:
        print("GTK 3, libsoup 3 and Secret Service bindings are available.")
        return 0
    if args.discover:
        from network import discover
        print(json.dumps(discover(), ensure_ascii=False, indent=2))
        return 0

    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk
    import ui
    from network import discover, find_mac, local_host, magic_packet, wake
    from storage import Credentials, Preferences
    from webos import TIMEOUT, WebOS
    from macros import AutoOffEngine, AutoOffRule, MacroStore
    indicator_api = None
    for namespace in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(namespace, "0.1")
            from importlib import import_module
            indicator_api = import_module("gi.repository." + namespace)
            break
        except (ImportError, ValueError):
            pass

    class Remote(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="io.github.lgwebos.Menubar" + (".SmokeTest" if args.smoke_test else ""),
                             flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.window = self.client = self.indicator = None
            self.preferences, self.credentials = Preferences(), Credentials()
            self.devices = []
            self.app_titles = {}
            self.muted = False
            self.poll = 0
            self.macro_timer = 0
            self.macro_engine = None
            self.macro_store = MacroStore()
            self.mac_host = ""
            self.known_macs = {}
            self.standby_candidate = None
            self.ready_client = None
            self.standby = False
            self.wake_timer = 0
            self.wake_until = 0
            self.wake_host = ""
            self.connect("activate", self.activate_app)
            self.connect("shutdown", self.shutdown_app)

        def activate_app(self, application):
            if self.window:
                self.window.present()
                return
            self.hold()
            self.window = Gtk.ApplicationWindow(application=self, title="LG webOS Remote")
            self.window.connect("delete-event", self.hide_window)
            ui.build(self)
            settings_error = None
            try:
                saved = {} if args.smoke_test else self.preferences.load()
                self.known_macs = dict(saved.get("macs", {}))
                self.host.set_text(str(saved.get("host", "")))
                self.mac.set_text(str(saved.get("mac", "")))
            except Exception as error:
                settings_error = str(error)
            try:
                rule = AutoOffRule() if args.smoke_test else self.macro_store.load()
            except Exception as error:
                rule = AutoOffRule()
                self.macro_notice.set_text(str(error))
            self.macro_engine = AutoOffEngine(rule, self.make_macro_client,
                                              self.macro_store.save, self.macro_status_changed)
            self.load_macro_form()
            self.make_indicator()
            self.window.show_all()
            if self.host.get_text():
                self.status.set_text("Your TV is saved. Connect when you're ready.")
            else:
                self.stack.set_visible_child_name("settings")
            if settings_error:
                self.status.set_text(settings_error)
            if args.smoke_test:
                if args.preview:
                    self.show_preview(args.preview)
                GLib.timeout_add_seconds(2, self.finish_smoke)
            else:
                if self.host.get_text() and not settings_error:
                    GLib.idle_add(self.connect_tv, True)
                elif not settings_error:
                    self.search()
                self.macro_engine.tick()
                self.macro_timer = GLib.timeout_add_seconds(2, self.macro_engine.tick)
            self.poll = GLib.timeout_add_seconds(10, self.refresh_state)

        def show_tray_power(self, icon, description):
            if self.indicator:
                self.indicator.set_icon_full(str(icon), description)
                self.indicator.set_title("LG webOS Remote · " + description)

        def show_preview(self, page):
            # Isolated presentation fixture: no settings, credentials or TV connection.
            ui.set_connection(self, "connected")
            self.status.set_text("Connected and ready to use.")
            self.device_name.set_text("LG webOS TV")
            self.controls.set_sensitive(True)
            self.update_volume({"volume": 24, "muted": False})
            self.update_apps({"launchPoints": [
                {"id": ident, "title": ui.CATALOG[ident]["title"]}
                for ident in ("netflix", "youtube.leanback.v4", "amazon", "com.disney.disneyplus-prod",
                              "com.apple.appletv", "spotify-beehive", "com.webos.app.browser", "com.geforcenow.play", "com.webos.app.photovideo")]})
            self.update_foreground({"appId": "netflix"})
            self.update_inputs({"devices": [{"id": "HDMI_1", "label": "HDMI 1"}, {"id": "HDMI_2", "label": "HDMI 2"}]})
            self.stack.set_visible_child_name(page)
            if page == "macros":
                self.macro_status.set_text("Off · Enable and save the rule to start.")

        def make_indicator(self):
            self.tray_available = False
            if indicator_api is None or args.smoke_test:
                return
            self.indicator = indicator_api.Indicator.new(
                "lgwebos-menubar", str(ui.ASSETS / "lgwebos.svg"), indicator_api.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_title("LG webOS Remote")
            self.indicator.set_status(indicator_api.IndicatorStatus.ACTIVE)
            menu = Gtk.Menu()
            for label, callback in (("Open remote", lambda: self.window.present()),
                                    ("Connect", self.connect_tv), ("Disconnect", self.disconnect),
                                    ("Turn TV on", self.wake_tv),
                                    ("Volume up", lambda: self.command("audio/volumeUp")),
                                    ("Volume down", lambda: self.command("audio/volumeDown")),
                                    ("Quit", self.quit)):
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda _, callback=callback: callback())
                menu.append(item)
            self.pause_menu = Gtk.MenuItem(label="Pause macro for today")
            self.pause_menu.connect("activate", lambda _: self.pause_macro_today())
            menu.insert(self.pause_menu, 1)
            menu.show_all()
            self.indicator.set_menu(menu)
            if getattr(self, "power_icon", None):
                self.show_tray_power(ui.ASSETS / ui.POWER_ICONS[self.power_icon], self.power_state.get_text().lstrip("● "))
            self.watcher = Gio.bus_watch_name(
                Gio.BusType.SESSION, "org.kde.StatusNotifierWatcher", Gio.BusNameWatcherFlags.NONE,
                lambda *args: setattr(self, "tray_available", True), self.tray_lost)

        def tray_lost(self, *unused):
            self.tray_available = False
            if self.window:
                self.window.show_all()

        def hide_window(self, *unused):
            if self.tray_available:
                self.window.hide()
            else:
                self.quit()
            return True

        def finish_smoke(self):
            if args.screenshot:
                native = self.window.get_window()
                screenshot = Gdk.pixbuf_get_from_window(native, 0, 0, native.get_width(), native.get_height())
                screenshot.savev(str(args.screenshot), "png", [], [])
            print("GTK smoke test passed: remote window and controls created.")
            self.quit()
            return GLib.SOURCE_REMOVE

        def confirm(self, title, details, accept="Continue"):
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                       message_type=Gtk.MessageType.QUESTION,
                                       buttons=Gtk.ButtonsType.NONE, text=title)
            dialog.format_secondary_text(details)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button(accept, Gtk.ResponseType.OK)
            dialog.set_default_response(Gtk.ResponseType.CANCEL)
            answer = dialog.run()
            dialog.destroy()
            return answer == Gtk.ResponseType.OK

        def approve(self, host, pin):
            return self.confirm("Trust this TV's certificate?",
                                f"Address: {host}\nSHA-256: {pin}\n\n"
                                "Continue only if this is your TV. Then accept the pairing request on the TV.",
                                "Trust and pair")

        def select_device(self, combo):
            if self.client and not self.client.closed:
                return
            index = combo.get_active()
            if 0 <= index < len(self.devices):
                self.host.set_text(self.devices[index]["host"])
                self.device_name.set_text(self.devices[index]["name"])

        def search(self):
            self.search_button.set_sensitive(False)
            self.stack.set_visible_child_name("settings")
            self.status.set_text("Searching the local network…")

            def worker():
                try:
                    devices, error = discover(), None
                except Exception as failure:
                    devices, error = [], str(failure)
                GLib.idle_add(done, devices, error)

            def done(devices, error):
                self.devices = devices
                self.device_choice.remove_all()
                for device in devices:
                    self.device_choice.append_text(f'{device["name"]} ({device["host"]})')
                if not devices:
                    self.device_choice.append_text("No TVs found — enter the address below")
                self.device_choice.set_active(0)
                self.search_button.set_sensitive(not self.client or self.client.closed)
                if not self.client or self.client.closed:
                    self.status.set_text(error or ("TV found. Select Connect TV to continue." if devices else
                                                   "No TV found. Turn it on or enter its IP address in Settings."))
                return GLib.SOURCE_REMOVE

            threading.Thread(target=worker, daemon=True).start()

        def toggle_connection(self):
            if self.standby or (self.client and not self.client.closed):
                self.disconnect()
            else:
                self.connect_tv()

        def connect_tv(self, background=False, keep_wake=False):
            host = self.host.get_text().strip()
            if not local_host(host):
                self.stack.set_visible_child_name("settings")
                self.status.set_text("Find your TV or enter its IP address in Settings.")
                return
            self.disconnect(stop_wake=not keep_wake)
            try:
                mac = self.mac.get_text().strip()
                if mac:
                    magic_packet(mac)
                self.remember_mac(host, mac)
                client = WebOS(host, self.credentials, self.approve,
                               lambda text: self.client_state(client, text))
                self.client = client
                # Connect and the startup connection may wait for an off TV; neither turns the TV on.
                self.standby_candidate = client if not keep_wake else None
                self.connect_button.set_sensitive(False)
                self.host.set_sensitive(False)
                self.device_choice.set_sensitive(False)
                ui.set_connection(self, "connecting")
                client.connect(background=background)
            except Exception as error:
                self.status.set_text(str(error))

        def client_state(self, client, text):
            if client is not self.client:
                return
            if "User rejected pairing" in text:
                text = "Pairing was declined. Connect again, then choose Allow on your TV."
            self.status.set_text(text)
            state = "connected" if client.ready else "error" if client.closed else "pairing" if "Accept the connection" in text else "connecting"
            if self.standby and state in ("connecting", "error"):
                state = "standby"
            ui.set_connection(self, state)
            self.controls.set_sensitive(client.ready)
            self.app_grid.set_sensitive(client.ready)
            self.host.set_sensitive(client.closed)
            self.device_choice.set_sensitive(client.closed)
            self.search_button.set_sensitive(client.closed)
            if client.ready:
                self.cancel_wake()
                self.standby_candidate, self.ready_client = None, client
                self.status.set_text("Connected and ready to use.")
                self.stack.set_visible_child_name("remote")
                self.refresh_state()
                self.command("com.webos.applicationManager/listLaunchPoints", after=self.update_apps)
                self.command("tv/getExternalInputList", after=self.update_inputs)
                self.learn_wake_mac(client.host)
                if self.macro_engine and self.macro_engine.blocked and self.macro_engine.rule.host == client.host:
                    self.macro_engine.configure(self.macro_engine.rule)
            elif client.closed and client is self.ready_client:
                # The TV turned off or left the network; wait for it without waking it.
                self.ready_client = None
                self.enter_standby(client.host)
            elif client.closed and client is self.standby_candidate:
                self.standby_candidate = None
                # At startup the TV may still be off or the network not ready yet, so keep waiting.
                if (client.unreachable or client.background) and client.saved.get("key") \
                        and not client.background_blocked and not client.trust_error:
                    self.enter_standby(client.host)
            elif self.standby:
                self.show_standby()
            elif self.wake_until and client.closed:
                if client.background_blocked:
                    self.cancel_wake()
                else:
                    self.status.set_text("Waiting for the TV to start… Connecting automatically.")

        def disconnect(self, stop_wake=True):
            if stop_wake:
                self.cancel_wake()
            client, self.client = self.client, None
            if client:
                client.close()
            self.controls.set_sensitive(False)
            self.connect_button.set_sensitive(True)
            self.host.set_sensitive(True)
            self.device_choice.set_sensitive(True)
            self.search_button.set_sensitive(True)
            for child in self.app_grid.get_children():
                child.destroy()
            self.app_titles.clear()
            self.app_hint.set_text("Connect your TV to see its installed apps.")
            self.app_search.set_text("")
            self.inputs.remove_all()
            self.now_playing.set_text("Ready when you are")
            self.volume_label.set_text("—")
            self.status.set_text("Connect your TV to start using the remote.")
            ui.set_connection(self, "disconnected")

        def command(self, uri, payload=None, after=None, quiet=False):
            client = self.client
            if not client or not client.ready:
                if not quiet:
                    self.status.set_text("Connect to the TV first.")
                return

            def done(data, error):
                if self.client is not client:
                    return
                if error:
                    if not quiet:
                        self.status.set_text(error)
                elif after:
                    after(data)

            client.request(uri, payload, done)

        def remote_button(self, name):
            if self.client and self.client.ready:
                self.client.button(name, lambda data, error: self.status.set_text(error) if error else None)

        def refresh_state(self, unused=None):
            if self.client and self.client.ready:
                client = self.client
                client.request("com.webos.service.tvpower/power/getPowerState",
                               callback=lambda data, error: self.power_received(client, data, error))
                self.command("audio/getVolume", after=self.update_volume, quiet=True)
                self.command("com.webos.applicationManager/getForegroundAppInfo", after=self.update_foreground, quiet=True)
            return GLib.SOURCE_CONTINUE

        def power_received(self, client, data, error):
            if client is not self.client:
                return
            if error == TIMEOUT:
                client.fail("The TV stopped responding.")
            elif not error:
                self.update_power(data)

        def update_power(self, data):
            state = str(data.get("state", "")).casefold()
            # "Active" is on; "Screen Off" keeps the TV on without picture; other states are standby.
            ui.set_power(self, "on" if state in ("", "active", "screen saver")
                         else "screen-off" if state == "screen off" else "off")

        def update_volume(self, data):
            value = data.get("volumeStatus", data)
            self.muted = bool(value.get("muteStatus", value.get("mute", value.get("muted", False))))
            self.volume_label.set_text(str(value.get("volume", "—")) + (" · Muted" if self.muted else ""))
            context = self.mute_button.get_style_context()
            context.add_class("muted-button") if self.muted else context.remove_class("muted-button")
            content = self.mute_button.get_child()
            children = content.get_children()
            content.remove(children[0])
            icon = ui.image("volume-x" if self.muted else "volume-2")
            content.pack_start(icon, False, False, 0)
            content.reorder_child(icon, 0)
            children[1].set_text("Unmute" if self.muted else "Mute")
            self.mute_button.get_accessible().set_name("Unmute" if self.muted else "Mute")
            self.mute_button.set_tooltip_text("Unmute" if self.muted else "Mute")
            content.show_all()

        def update_foreground(self, data):
            ident = data.get("appId", "")
            title = self.app_titles.get(ident) or ui.CATALOG.get(ident, {}).get("title")
            self.now_playing.set_text(title or ("TV is on" if ident else "Ready when you are"))
            self.now_playing.set_tooltip_text(title or "Current TV activity")

        def update_apps(self, data):
            ui.update_apps(self, data.get("launchPoints", []))

        def update_inputs(self, data):
            self.inputs.remove_all()
            for item in data.get("devices", []):
                if item.get("id"):
                    self.inputs.append(item["id"], item.get("label", item["id"]))
            self.inputs.set_active(0)

        def switch_input(self):
            if self.inputs.get_active_id():
                self.command("tv/switchInput", {"inputId": self.inputs.get_active_id()}, self.refresh_state)

        def power_off(self):
            if self.confirm("Turn off the TV?", "This will end playback on the connected TV.", "Turn off"):
                self.command("system/turnOff", after=lambda data: self.turned_off())

        def turned_off(self):
            # The socket may linger while the TV powers down, so show it off right away.
            if self.client:
                self.client.fail("TV turned off.")

        def toggle_power(self):
            if self.client and self.client.ready and getattr(self, "power_icon", "") in ("on", "screen-off"):
                self.power_off()
            else:
                self.wake_tv()

        def host_changed(self, entry):
            host = entry.get_text().strip()
            if host != self.mac_host and (self.mac_host or host in self.known_macs):
                self.mac.set_text(self.known_macs.get(host, ""))
            self.mac_host = host

        def remember_mac(self, host, mac):
            self.preferences.save(host, mac)
            if mac:
                self.known_macs[host] = mac
            else:
                self.known_macs.pop(host, None)

        def learn_wake_mac(self, host):
            if args.smoke_test or self.mac.get_text().strip():
                return
            def learned(mac):
                if mac and self.host.get_text().strip() == host and not self.mac.get_text().strip():
                    try:
                        self.remember_mac(host, mac)
                        self.mac.set_text(mac)
                    except OSError:
                        pass
                return GLib.SOURCE_REMOVE
            threading.Thread(target=lambda: GLib.idle_add(learned, find_mac(host)), daemon=True).start()

        def cancel_wake(self):
            if self.wake_timer:
                GLib.source_remove(self.wake_timer)
                self.wake_timer = 0
            self.wake_until = 0
            self.wake_host = ""
            self.standby = False

        def enter_standby(self, host):
            # Wait for the TV without sending Wake-on-LAN; only Turn TV on wakes it.
            self.cancel_wake()
            self.standby = True
            self.wake_until = float("inf")
            self.wake_host = host
            self.wake_timer = GLib.timeout_add_seconds(10, self.retry_wake_connection)
            self.show_standby()

        def show_standby(self):
            ui.set_connection(self, "standby")
            self.status.set_text("TV is off. The remote connects when the TV turns on; use Turn TV on to wake it."
                                 if self.mac.get_text().strip() else
                                 "TV is off. The remote connects when the TV turns on. Turn TV on needs its MAC address.")

        def retry_wake_connection(self):
            if not self.wake_until:
                self.wake_timer = 0
                return GLib.SOURCE_REMOVE
            if time.monotonic() >= self.wake_until:
                self.wake_timer = 0
                self.disconnect()
                self.status.set_text("TV did not wake. Check its network standby setting and MAC address, then try again.")
                return GLib.SOURCE_REMOVE
            if self.host.get_text().strip() != self.wake_host:
                self.wake_timer = 0
                self.disconnect()
                return GLib.SOURCE_REMOVE
            if not self.client or self.client.closed:
                self.connect_tv(background=True, keep_wake=True)
            return GLib.SOURCE_CONTINUE if self.wake_until else GLib.SOURCE_REMOVE

        def wake_tv(self):
            if args.smoke_test:
                return
            try:
                host, mac = self.host.get_text().strip(), self.mac.get_text().strip()
                if not local_host(host):
                    raise ValueError("Enter the TV's local IPv4 address in Settings first.")
                mac = mac or find_mac(host)
                if not mac:
                    self.stack.set_visible_child_name("settings")
                    self.mac.grab_focus()
                    self.status.set_text("Wake needs your TV's MAC address. Turn it on once with its remote and Connect TV to learn it, or enter the MAC in Settings.")
                    return
                magic_packet(mac)
                self.remember_mac(host, mac)
                self.mac.set_text(mac)
                rule = self.macro_engine.rule
                if rule.host == host and rule.watching(datetime.now().astimezone()):
                    if not self.confirm("The auto-off macro is active", "The macro would turn this TV off again. Pause it for today and turn the TV on?", "Pause today & turn on"):
                        return
                    rule = replace(rule, paused_on=datetime.now().astimezone().date().isoformat(), warning_window="", warning_due=0)
                    self.macro_store.save(rule)
                    self.macro_engine.configure(rule)
                self.disconnect()
                wake(host, mac)
                self.wake_until = time.monotonic() + 60
                self.wake_host = host
                self.status.set_text("Wake signal sent. Waiting for TV…")
                self.wake_timer = GLib.timeout_add_seconds(3, self.retry_wake_connection)
            except Exception as error:
                self.status.set_text(str(error))

        def forget(self):
            host = self.host.get_text().strip()
            if not local_host(host):
                self.status.set_text("Enter the TV's local IPv4 address first.")
                return
            if self.confirm("Forget this TV's pairing?", "The next connection will require certificate and TV approval.", "Forget pairing"):
                self.disconnect()
                if self.macro_engine.rule.host == host:
                    try:
                        rule = replace(self.macro_engine.rule, enabled=False)
                        self.macro_store.save(rule)
                        self.macro_engine.configure(rule)
                        self.load_macro_form()
                    except Exception:
                        self.status.set_text("Could not disable the TV's macro. Pairing was kept.")
                        return
                try:
                    self.credentials.clear(host)
                    self.status.set_text("Pairing forgotten. Connect to pair again.")
                except Exception:
                    self.status.set_text("Could not clear pairing. Unlock the desktop keyring and try again.")

        def make_macro_client(self, host, callback):
            return WebOS(host, self.credentials, lambda *_: False, callback)

        def load_macro_form(self):
            rule = self.macro_engine.rule
            self.macro_enabled.set_active(rule.enabled)
            self.macro_start.set_text(rule.start)
            self.macro_end.set_text(rule.end)
            self.macro_repeat.set_active(rule.repeat)
            self.macro_warning.set_active(rule.warn_before_off)
            self.macro_target.set_text("Target TV: " + rule.host if rule.host else "Target TV: use the address in Settings when saving.")
            self.macro_status_changed(self.macro_engine.status or "Off · Enable and save the rule to start.")

        def macro_status_changed(self, message):
            self.macro_status.set_text(message)
            if not self.macro_engine:
                return
            rule = self.macro_engine.rule
            paused = rule.paused_on == datetime.now().astimezone().date().isoformat()
            text = "Resume today" if paused else "Pause for today"
            self.macro_pause_label.set_text(text)
            self.macro_pause.get_accessible().set_name(text)
            self.macro_pause.set_sensitive(rule.enabled and not args.smoke_test)
            if hasattr(self, "pause_menu"):
                self.pause_menu.set_label("Resume macro today" if paused else "Pause macro for today")
                self.pause_menu.set_sensitive(rule.enabled)

        def save_macro(self):
            if args.smoke_test:
                return
            try:
                rule = replace(self.macro_engine.rule, enabled=self.macro_enabled.get_active(),
                               host=self.host.get_text().strip(), start=self.macro_start.get_text().strip(),
                               end=self.macro_end.get_text().strip(), repeat=self.macro_repeat.get_active(),
                               warn_before_off=self.macro_warning.get_active()).validate()
                if not rule.enabled:
                    rule = replace(rule, warning_window="", warning_due=0)
                if rule.enabled:
                    saved = self.credentials.load(rule.host)
                    if not saved.get("key") or not saved.get("pin"):
                        raise ValueError("Connect and pair this TV first, then enable the macro.")
                self.macro_store.save(rule)
                self.macro_engine.configure(rule)
                self.load_macro_form()
                self.macro_notice.set_text("Saved. Changes apply immediately.")
            except Exception as error:
                self.macro_notice.set_text(str(error))

        def pause_macro_today(self):
            if args.smoke_test or not self.macro_engine.rule.enabled:
                return
            try:
                today = datetime.now().astimezone().date().isoformat()
                rule = self.macro_engine.rule
                paused = "" if rule.paused_on == today else today
                rule = replace(rule, paused_on=paused, warning_window="", warning_due=0)
                self.macro_store.save(rule)
                self.macro_engine.configure(rule)
                self.macro_notice.set_text("Resumed." if not paused else "Paused until midnight, including after an app restart.")
            except Exception as error:
                self.macro_notice.set_text("Could not save today's pause: " + str(error))

        def shutdown_app(self, unused):
            self.cancel_wake()
            if self.macro_timer:
                GLib.source_remove(self.macro_timer)
            if self.macro_engine:
                self.macro_engine.stop()
            if self.poll:
                GLib.source_remove(self.poll)
            if self.client:
                self.client.close()
            if self.indicator:
                self.indicator.set_status(indicator_api.IndicatorStatus.PASSIVE)
                Gio.bus_unwatch_name(self.watcher)

    return Remote().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
