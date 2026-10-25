# LG webOS Remote for Linux

A GTK 3 desktop remote with an AppIndicator menu for Ubuntu/GNOME. The original
SwiftUI app requires macOS; this companion provides the core TV controls on Linux.

The English interface has **Remote**, **Apps**, **Macros** and **Settings** tabs. Remote puts
navigation, playback, volume and input selection together; Apps shows searchable
logo tiles for installed TV apps. Buttons use bundled SVG icons with tooltips and
accessible names. Connection and mute states are indicated with text as well as
color. All artwork is local, so displaying the interface does not fetch images.

## Install and run

From the repository root:

```sh
# Ubuntu/Debian dependencies (already present on many Ubuntu desktops)
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-soup-3.0 \
  gir1.2-secret-1 gir1.2-ayatanaappindicator3-0.1 glib-networking gnome-keyring

python3 'LG webOS 5.0/linux/install.py'
gtk-launch io.github.lgwebos.Menubar
```

You can also run directly from the checkout:

```sh
python3 'LG webOS 5.0/linux/app.py'
```

Installation copies the app into `$XDG_DATA_HOME/lgwebos-menubar` (normally
`~/.local/share/lgwebos-menubar`) and adds **LG webOS Remote** to the applications
menu. Re-run the installer after source changes. No root permissions, Python
package downloads, or Swift toolchain are required to run or install the app once
the desktop libraries are present.

Ubuntu's AppIndicator extension provides the panel icon. Closing the window keeps
the remote in the panel; use **Quit** from the panel menu to exit. On desktops
without a tray host, closing the window exits the app. Only one normal instance
runs per desktop session. Installation does not enable login autostart.

## Pair a TV

1. Turn on the TV and connect it to the same local network as the computer.
2. On first launch the app searches automatically. Select the TV, or enter its
   local IPv4 address in Settings, then click **Connect TV**.
3. Review and approve the TV certificate in the desktop dialog.
4. Accept the connection request on the TV using its physical remote.

The desktop keyring must be available and unlocked. Both the pairing key and
certificate fingerprint are stored together in Secret Service, separately for
each TV address. Settings contain only the TV address and optional wake MAC in
`$XDG_CONFIG_HOME/lgwebos-menubar/settings.json` (normally under `~/.config`).

Connections use encrypted WebSockets on port 3001. Certificate changes are
rejected; after verifying the device, use **Forget pairing** to pair again.
Discovery and remote traffic bypass HTTP proxies and stay on the local network.
The client uses [libsoup's WebSocket API](https://libsoup.gnome.org/libsoup-3.0/method.Session.websocket_connect_async.html)
and [certificate validation callback](https://libsoup.gnome.org/libsoup-3.0/signal.Message.accept-certificate.html).

Once paired, the app automatically connects to the saved TV on startup. Automatic
connections use existing credentials and certificate pins; they do not approve
new certificates or initiate repeated pairing prompts. If pairing needs attention,
use **Connect TV** to pair manually.

If discovery finds nothing, check device isolation/guest Wi-Fi and enter the TV
address manually. After the first successful connection the app remembers the TV's
MAC address for that TV address. Connecting never turns the TV on: if a paired TV
is off, **Connect** waits in a "TV off" state and connects automatically when the TV
turns on. Use **Turn TV on** to wake it with Wake-on-LAN (enable network standby /
"Turn on via Wi-Fi" on the TV). The app does not repeatedly retry pairing requests.

## Daily power-off macro

Open **Macros** to create a nightly auto-off rule. The initial preset is
**21:00–24:00**, with repeated power-off and a first-off warning selected. The rule is disabled until you
enable its switch and click **Save macro**. Pair the target TV first; saving binds
the rule to the TV address currently shown in Settings. Saving time or option
changes applies them immediately.

- The start is inclusive and the end is exclusive, using the computer's local
  time. `24:00` means midnight. Windows across midnight, such as `22:00–02:00`,
  are also supported.
- When **Turn off again if TV is switched back on** is checked, the app checks
  power approximately every 10 seconds while in the window. It reconnects when
  the TV returns and sends power-off whenever the TV reports `Active`.
- When unchecked, the app sends power-off once per time window. It persists the
  dispatch before sending so restarting the app or a lost TV acknowledgement
  cannot trigger a second power-off that night. An explicit TV rejection is shown
  as an error; save the rule again after resolving it. Switching from repeat to
  once respects any power-off already sent in that window.
- **Warn on TV 1 minute before the first power-off** sends an on-screen message
  and waits at least 60 seconds before the first power-off of that time window.
  For the default rule it starts watching at 20:59, so a TV already on can be
  warned before 21:00. If first detected later, it is warned then and given a
  full minute. The next power check after that minute sends power-off (normally
  within another 10 seconds). Repeated power-offs after the first **do not warn
  or wait again**. A first warning is skipped if a full minute would extend past
  the window's end; commands never run outside the configured time window.
  The countdown survives app restarts, and today's pause cancels it. If the TV
  rejects notifications, the macro reports the error and does not silently turn
  the TV off; disable the warning or resolve the error and save again.
- **Pause for today** immediately stops further macro commands until the next
  local midnight. It survives an app restart. Use **Resume today** to remove the
  pause early. Resuming does not reset a once-only rule that already ran.
  The panel menu also has this pause/resume action. A command already sent to the
  TV cannot be recalled by pausing.

The macro uses its own connection, so disconnecting the interactive remote does
not disable it. Pause or disable the macro to stop it. It never wakes the TV and
does not assume the TV is on if a power-state query fails. The computer must be
awake, logged in, on the same network, and running this app. Closing the window to
the panel keeps it active; quitting the app or suspending the computer stops
monitoring. On resume, the current time window is evaluated again.

Rules, today's pause, the warning countdown and the last handled window are saved privately in
`$XDG_CONFIG_HOME/lgwebos-menubar/macros.json`. No TV credentials are stored there.

TV messages use the same `system.notifications/createToast` request documented
by [PyWebOSTV's system controls](https://github.com/supersaiyanmode/PyWebOSTV#system-controls).

## Available controls and limits

- Navigation, Home, Back, Menu, Play and Pause.
- Volume up/down, mute, current volume and foreground app.
- Installed app launcher and external input selector.
- TV power off with confirmation; Wake-on-LAN with a supplied MAC address.
- Discovery, per-TV pairing, certificate pinning and a system tray menu.

The Linux companion does not yet include the macOS touchpad, media casting,
picture settings, favorites or usage history. Wake support depends on TV network
standby settings. Model and firmware support still require testing on the actual
TV; a successful mock test does not establish hardware compatibility.

## Checks

```sh
python3 'LG webOS 5.0/linux/app.py' --check
python3 'LG webOS 5.0/linux/app.py' --smoke-test
python3 'LG webOS 5.0/linux/app.py' --discover

# Tests additionally need python3-cryptography and desktop-file-utils.
python3 -m unittest discover -s 'LG webOS 5.0/linux/tests' -v
python3 'LG webOS 5.0/scripts/privacy-check.py'
```

The smoke test creates the UI and exits without reading saved settings, connecting
to a TV, or modifying the keyring. The tests use an ephemeral TLS mock server on
loopback and a temporary install directory. They exercise certificate approval
and rejection, pairing, stored credentials, requests, pointer buttons, errors,
timeouts, cancellation, installation and settings. They never contact a real TV.
`--discover` is a read-only network search; its output contains private device
details and should not be published.

For an offline visual check, add `--preview remote` (or `apps` / `macros` / `settings`) and
`--screenshot /tmp/lgwebos-preview.png` to `--smoke-test`. Preview data is fictional;
it does not pair or send commands to a TV. The installer copies the UI assets and
app catalog along with the executable scripts.

To uninstall, remove the installed `lgwebos-menubar` directory and
`applications/io.github.lgwebos.Menubar.desktop` from your data directory. Use
**Forget pairing** first if you also want to remove the selected TV's credentials.
