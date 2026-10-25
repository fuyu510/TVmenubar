"""GTK presentation and bundled artwork for the Linux remote."""
from functools import lru_cache
import json
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, Pango

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
CATALOG_ROOT = ROOT if (ROOT / "app-catalog.json").exists() else ROOT.parent / "Sources/LGwebOSMenubar"
CATALOG = {item["id"]: item for item in json.loads((CATALOG_ROOT / "app-catalog.json").read_text())}


def style(widget, *classes):
    for name in classes:
        widget.get_style_context().add_class(name)
    return widget


def label(text, css=None, **kwargs):
    widget = Gtk.Label(label=text, xalign=0, **kwargs)
    if css:
        style(widget, css)
    return widget


@lru_cache(maxsize=96)
def icon_pixbuf(name, size=24, color="#334155", scale=1):
    svg = (ASSETS / "icons" / f"{name}.svg").read_text().replace("currentColor", color)
    loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
    loader.set_size(size * scale, size * scale)
    loader.write(svg.encode())
    loader.close()
    return loader.get_pixbuf()


def image(name, size=22, color="#334155"):
    widget = Gtk.Image()
    def render(*unused):
        scale = widget.get_scale_factor()
        pixbuf = icon_pixbuf(name, size, color, scale)
        widget.set_from_surface(Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, None))
    widget.connect("notify::scale-factor", render)
    render()
    return widget


def button(text, callback, icon=None, css=None, icon_only=False, vertical=False, color="#334155"):
    widget = Gtk.Button()
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                      spacing=5 if vertical else 8, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    if icon:
        content.pack_start(image(icon, color=color), False, False, 0)
    if not icon_only:
        content.pack_start(Gtk.Label(label=text), False, False, 0)
    widget.add(content)
    widget.get_accessible().set_name(text)
    widget.set_tooltip_text(text)
    widget.connect("clicked", lambda _: callback())
    if css:
        style(widget, css)
    return widget


def card(spacing=12):
    return style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing), "card")


def row(spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)


def app_image(app_id, size=52):
    name = CATALOG.get(app_id, {}).get("icon")
    path = CATALOG_ROOT / "AppAssets" / (name or "")
    if name and path.is_file():
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
        return Gtk.Image.new_from_pixbuf(pixbuf)
    return image("grid-2x2", size, "#738399")


def build(remote):
    provider = Gtk.CssProvider()
    provider.load_from_path(str(ASSETS / "style.css"))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window = remote.window
    window.set_name("lg-remote")
    window.set_default_size(460, 800)
    window.set_size_request(400, 600)
    window.set_icon_from_file(str(ASSETS / "lgwebos.svg"))
    titlebar = Gtk.HeaderBar(title="TV Remote", show_close_button=True)
    window.set_titlebar(titlebar)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=20)
    window.add(root)
    header = row(12)
    brand = style(Gtk.Box(margin_end=2), "brand-mark")
    brand.pack_start(image("tv-minimal", 26, "#ffffff"), True, True, 0)
    header.pack_start(brand, False, False, 0)
    titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    titles.pack_start(label("LG webOS", "title"), False, False, 0)
    titles.pack_start(label("Your TV, within reach.", "muted"), False, False, 0)
    header.pack_start(titles, True, True, 0)
    header.pack_end(button("Connection settings", lambda: remote.stack.set_visible_child_name("settings"),
                           "settings-2", "quiet", True), False, False, 0)
    root.pack_start(header, False, False, 0)

    connection = card(10)
    heading = row(12)
    remote.power_tile = style(Gtk.Box(valign=Gtk.Align.CENTER), "power-tile")
    remote.power_tile.pack_start(image("tv-minimal", 22, "#ffffff"), True, True, 0)
    heading.pack_start(remote.power_tile, False, False, 0)
    names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
    remote.device_name = label("LG webOS TV", "section-title", ellipsize=Pango.EllipsizeMode.END)
    names.pack_start(remote.device_name, False, False, 0)
    remote.power_state = label("TV status unknown", "power-state")
    names.pack_start(remote.power_state, False, False, 0)
    heading.pack_start(names, True, True, 0)
    remote.badge = style(Gtk.Label(label="Offline"), "badge")
    heading.pack_end(remote.badge, False, False, 0)
    connection.pack_start(heading, False, False, 0)
    remote.status = label("Choose your TV in Settings to get started.", "muted", wrap=True)
    remote.status.set_max_width_chars(40)
    connection.pack_start(remote.status, False, False, 0)
    actions = row()
    # The remote connects automatically, so power is the main action and Connect stays small.
    remote.power_button = button("Turn TV on", remote.toggle_power, "power", "power", color="#ffffff")
    remote.connect_button = button("Connect TV", remote.toggle_connection, "plug", "connect-mini", True)
    actions.pack_start(remote.power_button, True, True, 0)
    actions.pack_end(remote.connect_button, False, False, 0)
    connection.pack_start(actions, False, False, 0)
    root.pack_start(connection, False, False, 0)

    remote.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=140)
    remote.stack.set_hhomogeneous(False)
    remote.stack.set_vhomogeneous(False)
    def switch_page(stack, unused):
        macros_visible = stack.get_visible_child_name() == "macros"
        connection.set_no_show_all(macros_visible)
        connection.set_visible(not macros_visible)
    remote.stack.connect("notify::visible-child-name", switch_page)
    tabs = style(Gtk.StackSwitcher(stack=remote.stack, halign=Gtk.Align.FILL, homogeneous=True), "tabs")
    root.pack_start(tabs, False, False, 0)
    root.pack_start(remote.stack, True, True, 0)

    remote.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    remote.controls.set_sensitive(False)
    remote_page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    remote_page.add(remote.controls)
    remote.stack.add_titled(remote_page, "remote", "Remote")

    navigation = style(card(6), "navigation")
    top = row()
    for title, command, icon in (("Home", "HOME", "house"), ("Back", "BACK", "arrow-left"), ("Menu", "MENU", "menu")):
        top.pack_start(button(title, lambda command=command: remote.remote_button(command), icon, "shortcut", vertical=True), True, True, 0)
    navigation.pack_start(top, False, False, 0)
    pad = style(Gtk.Grid(column_spacing=4, row_spacing=4, halign=Gtk.Align.CENTER), "direction-pad")
    for title, command, icon, x, y in (("Up", "UP", "chevron-up", 1, 0),
                                      ("Left", "LEFT", "chevron-left", 0, 1),
                                      ("Right", "RIGHT", "chevron-right", 2, 1),
                                      ("Down", "DOWN", "chevron-down", 1, 2)):
        key = button(title, lambda command=command: remote.remote_button(command), icon, "direction", True)
        key.set_size_request(48, 38)
        pad.attach(key, x, y, 1, 1)
    ok = button("OK", lambda: remote.remote_button("ENTER"), css="confirm-key")
    ok.set_size_request(52, 52)
    pad.attach(ok, 1, 1, 1, 1)
    navigation.pack_start(pad, False, False, 0)
    playback = row()
    remote.now_playing = label("Ready when you are", "muted", ellipsize=Pango.EllipsizeMode.END)
    remote.now_playing.set_max_width_chars(23)
    playback.pack_start(remote.now_playing, True, True, 0)
    playback.pack_end(button("Pause", lambda: remote.remote_button("PAUSE"), "pause", "quiet", True), False, False, 0)
    playback.pack_end(button("Play", lambda: remote.remote_button("PLAY"), "play", "quiet", True), False, False, 0)
    navigation.pack_start(playback, False, False, 0)
    remote.controls.pack_start(navigation, False, False, 0)

    audio = card(8)
    audio_heading = row()
    audio_heading.pack_start(label("Volume", "section-title"), True, True, 0)
    remote.volume_label = label("—", "volume-value")
    audio_heading.pack_end(remote.volume_label, False, False, 0)
    audio.pack_start(audio_heading, False, False, 0)
    volume = row()
    volume.pack_start(button("Volume down", lambda: remote.command("audio/volumeDown", after=remote.refresh_state), "minus", icon_only=True), True, True, 0)
    remote.mute_button = button("Mute", lambda: remote.command("audio/setMute", {"mute": not remote.muted}, remote.refresh_state), "volume-2")
    volume.pack_start(remote.mute_button, True, True, 0)
    volume.pack_start(button("Volume up", lambda: remote.command("audio/volumeUp", after=remote.refresh_state), "plus", icon_only=True), True, True, 0)
    audio.pack_start(volume, False, False, 0)
    remote.controls.pack_start(audio, False, False, 0)

    inputs = row()
    inputs.pack_start(image("monitor-up", 20), False, False, 0)
    remote.inputs = Gtk.ComboBoxText(hexpand=True)
    remote.inputs.set_tooltip_text("Select a TV input")
    remote.inputs.get_accessible().set_name("TV input")
    inputs.pack_start(remote.inputs, True, True, 0)
    inputs.pack_end(button("Switch", remote.switch_input), False, False, 0)
    remote.controls.pack_start(inputs, False, False, 0)

    apps_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    remote.app_search = Gtk.SearchEntry(placeholder_text="Find an app…")
    remote.app_search.get_accessible().set_name("Find an app")
    apps_page.pack_start(remote.app_search, False, False, 0)
    remote.app_hint = label("Connect your TV to see its installed apps.", "muted", wrap=True)
    apps_page.pack_start(remote.app_hint, False, False, 0)
    scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    remote.app_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                  min_children_per_line=3, max_children_per_line=3,
                                  column_spacing=10, row_spacing=10, valign=Gtk.Align.START)
    remote.app_grid.set_filter_func(lambda child: remote.app_search.get_text().casefold() in child.get_child().search_text)
    remote.app_search.connect("search-changed", lambda _: remote.app_grid.invalidate_filter())
    scroll.add(remote.app_grid)
    apps_page.pack_start(scroll, True, True, 0)
    remote.stack.add_titled(apps_page, "apps", "Apps")

    macro_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    macro_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    macro_shell.pack_start(macro_scroll, True, True, 0)
    macro_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    macro_scroll.add(macro_page)
    remote.stack.add_titled(macro_shell, "macros", "Macros")
    rule = card()
    heading = row()
    heading.pack_start(label("Nightly TV off", "section-title"), True, True, 0)
    remote.macro_enabled = Gtk.Switch(valign=Gtk.Align.CENTER)
    remote.macro_enabled.get_accessible().set_name("Enable nightly TV off")
    heading.pack_end(remote.macro_enabled, False, False, 0)
    rule.pack_start(heading, False, False, 0)
    rule.pack_start(label("If the TV is on during this time window,\nautomatically turn it off.", "muted", wrap=True), False, False, 0)
    times = row(12)
    for title, attribute, value in (("From", "macro_start", "21:00"), ("Until", "macro_end", "24:00")):
        field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        field.pack_start(label(title, "field-label"), False, False, 0)
        entry = Gtk.Entry(text=value, width_chars=6, max_length=5, hexpand=True)
        entry.get_accessible().set_name("Macro " + title.lower())
        setattr(remote, attribute, entry)
        field.pack_start(entry, False, False, 0)
        times.pack_start(field, True, True, 0)
    rule.pack_start(times, False, False, 0)
    rule.pack_start(label("Every day · Computer local time · 24:00 = midnight", "muted", wrap=True), False, False, 0)
    remote.macro_repeat = Gtk.CheckButton(label="Turn off again if TV is switched back on")
    remote.macro_repeat.set_active(True)
    rule.pack_start(remote.macro_repeat, False, False, 0)
    rule.pack_start(label("Unchecked: send power-off only once per time window.", "muted", wrap=True), False, False, 0)
    remote.macro_warning = Gtk.CheckButton(label="Warn on TV 1 minute before the first power-off")
    remote.macro_warning.set_active(True)
    rule.pack_start(remote.macro_warning, False, False, 0)
    rule.pack_start(label("Repeat power-offs have no warning or extra delay.", "muted", wrap=True), False, False, 0)
    remote.macro_target = label("", "muted", wrap=True)
    rule.pack_start(remote.macro_target, False, False, 0)
    macro_shell.pack_start(button("Save macro", remote.save_macro, "check", "primary", color="#ffffff"), False, False, 0)
    remote.macro_notice = label("Changes apply when you save.", "muted", wrap=True)
    remote.macro_notice.set_max_width_chars(42)
    macro_shell.pack_start(remote.macro_notice, False, False, 0)
    macro_page.pack_start(rule, False, False, 0)
    state = card()
    remote.macro_status = label("Off · Enable and save the rule to start.", "section-title", wrap=True)
    remote.macro_status.set_max_width_chars(38)
    state.pack_start(remote.macro_status, False, False, 0)
    remote.macro_pause = button("Pause for today", remote.pause_macro_today, "pause")
    remote.macro_pause_label = remote.macro_pause.get_child().get_children()[1]
    state.pack_start(remote.macro_pause, False, False, 0)
    state.pack_start(label("Today's pause survives app restarts and clears\nautomatically at the next local midnight.", "muted", wrap=True), False, False, 0)
    macro_page.pack_start(state, False, False, 0)
    macro_page.reorder_child(state, 0)
    macro_page.pack_start(label("Keep this computer awake and the app running.\nThe macro checks every 10 seconds and reconnects\nwhen the TV comes back online. Disconnecting the\nremote does not pause the macro.", "muted", wrap=True), False, False, 0)

    settings_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    settings_scroll.add(settings)
    remote.stack.add_titled(settings_scroll, "settings", "Settings")
    setup = card()
    setup.pack_start(label("Connect your TV", "section-title"), False, False, 0)
    setup.pack_start(label("Turn on your TV and use the same network.\nAccept the first connection on the TV screen.", "muted", wrap=True), False, False, 0)
    remote.search_button = button("Find TVs on my network", remote.search, "search")
    setup.pack_start(remote.search_button, False, False, 0)
    remote.device_choice = Gtk.ComboBoxText()
    remote.device_choice.append_text("Search for available TVs")
    remote.device_choice.set_active(0)
    remote.device_choice.connect("changed", remote.select_device)
    remote.device_choice.get_accessible().set_name("Available TVs")
    setup.pack_start(remote.device_choice, False, False, 0)
    setup.pack_start(label("TV IP address", "field-label"), False, False, 0)
    remote.host = Gtk.Entry(placeholder_text="Enter the address from your TV settings")
    remote.host.get_accessible().set_name("TV IP address")
    remote.host.connect("activate", lambda _: remote.connect_tv())
    setup.pack_start(remote.host, False, False, 0)
    settings.pack_start(setup, False, False, 0)
    wake = card()
    wake.pack_start(label("Wake your TV", "section-title"), False, False, 0)
    wake.pack_start(label("Works while disconnected. Requires TV network standby.\nThe MAC address is learned after a successful connection.\nConnecting never turns the TV on.", "muted", wrap=True), False, False, 0)
    remote.mac = Gtk.Entry(placeholder_text="TV MAC address")
    remote.host.connect("changed", remote.host_changed)
    remote.mac.get_accessible().set_name("TV MAC address")
    wake.pack_start(remote.mac, False, False, 0)
    wake.pack_start(button("Turn TV on & connect", remote.wake_tv, "power"), False, False, 0)
    settings.pack_start(wake, False, False, 0)
    settings.pack_start(button("Forget pairing…", remote.forget, "rotate-ccw", "quiet"), False, False, 0)
    footer = label("LOCAL CONNECTION  ·  NO CLOUD ACCOUNT", "footer")
    footer.set_halign(Gtk.Align.CENTER)
    root.pack_start(footer, False, False, 0)


def set_connection(remote, state):
    for css in ("online", "busy", "error"):
        remote.badge.get_style_context().remove_class(css)
    text, css = {"connected": ("Connected", "online"), "connecting": ("Connecting", "busy"),
                 "pairing": ("Check your TV", "busy"), "standby": ("Waiting", "busy"),
                 "error": ("Not connected", "error")}.get(state, ("Offline", ""))
    remote.badge.set_text(text)
    if css:
        style(remote.badge, css)
    remote.power_button.set_sensitive(True)
    active = state in ("connected", "connecting", "pairing", "standby")
    text = "Disconnect" if state in ("connected", "standby") else "Cancel connection" if active else "Connect TV"
    remote.connect_button.get_child().destroy()
    content = row()
    content.set_halign(Gtk.Align.CENTER)
    content.pack_start(image("unplug" if active else "plug", 18, "#69778a"), False, False, 0)
    remote.connect_button.add(content)
    remote.connect_button.get_accessible().set_name(text)
    remote.connect_button.set_tooltip_text(text)
    remote.connect_button.set_sensitive(True)
    content.show_all()
    set_power(remote, "on" if state == "connected" else "off" if state == "standby" else "unknown")


POWER_STATES = {"on": ("● TV is on", "power-on"), "screen-off": ("● Screen off · TV is on", "power-dim"),
                "off": ("● TV is off", ""), "unknown": ("TV status unknown", "")}
POWER_ICONS = {"on": "lgwebos-on.svg", "screen-off": "lgwebos-dim.svg", "off": "lgwebos-off.svg", "unknown": "lgwebos.svg"}


def set_power(remote, state):
    """Show the TV's power apart from the connection, so an on TV stands out."""
    text, css = POWER_STATES[state]
    for widget in (remote.power_tile, remote.power_state):
        for name in ("power-on", "power-dim"):
            widget.get_style_context().remove_class(name)
        if css:
            style(widget, css)
    remote.power_state.set_text(text)
    remote.power_tile.set_tooltip_text(text.lstrip("● "))
    remote.power_tile.get_accessible().set_name(text.lstrip("● "))
    if getattr(remote, "power_icon", None) != state:
        remote.power_icon = state
        icon = ASSETS / POWER_ICONS[state]
        remote.window.set_icon_from_file(str(icon))
        remote.show_tray_power(icon, text.lstrip("● "))
    on = state in ("on", "screen-off")
    action = "Turn TV off" if on else "Turn TV on"
    context = remote.power_button.get_style_context()
    context.add_class("power-active") if on else context.remove_class("power-active")
    remote.power_button.get_child().get_children()[1].set_text(action)
    remote.power_button.get_accessible().set_name(action)
    remote.power_button.set_tooltip_text(action)


def update_apps(remote, apps):
    for child in remote.app_grid.get_children():
        child.destroy()
    remote.app_titles = {}
    for item in sorted(apps, key=lambda app: app.get("title", "").casefold()):
        ident = item.get("id")
        if not ident or ident in remote.app_titles:
            continue
        title = item.get("title") or CATALOG.get(ident, {}).get("title", ident)
        remote.app_titles[ident] = title
        tile = style(Gtk.Button(), "app-tile")
        tile.search_text = title.casefold()
        tile.get_accessible().set_name("Launch " + title)
        tile.set_tooltip_text("Launch " + title)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER)
        artwork = style(Gtk.Box(halign=Gtk.Align.CENTER), "app-artwork")
        artwork.pack_start(app_image(ident, 44), False, False, 0)
        content.pack_start(artwork, False, False, 0)
        title_label = Gtk.Label(label=title, ellipsize=Pango.EllipsizeMode.END, max_width_chars=14)
        content.pack_start(title_label, False, False, 0)
        tile.add(content)
        tile.connect("clicked", lambda _, ident=ident: remote.command("system.launcher/launch", {"id": ident}, remote.refresh_state))
        remote.app_grid.add(tile)
    count = len(remote.app_titles)
    remote.app_hint.set_text(f"{count} apps · Select an app to open it on your TV." if count else "No apps were returned by this TV.")
    remote.app_grid.show_all()
