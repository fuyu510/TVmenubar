# TVmenubar-MacOS

Native macOS menu bar remotes for TVs on your local network. Choose the app for your TV's **operating system**; each app has its own Swift package, build script, and setup guide.

| TV operating system | What it can do | Project |
| --- | --- | --- |
| **LG webOS 5.0** | Pair with the TV, control navigation and volume, launch apps, switch HDMI inputs, view local usage, and send supported media | [LG webOS 5.0](LG%20webOS%205.0/README.md) |
| **Roku OS 15.3.4** | Discover the TV, control navigation and playback, launch channels, switch inputs, and use the TV's channel icons | [Roku OS 15.3.4](Roku%20OS%2015.3.4/README.md) |

Both apps require **macOS 14 or later**, Xcode Command Line Tools, and a TV on the same local network as the Mac. They are community projects, independent of LG and Roku.

**Using Linux?** The LG project also includes a [GTK desktop and system tray companion](LG%20webOS%205.0/linux/README.md) for Ubuntu/GNOME. It supports discovery, secure pairing, navigation, volume, apps, inputs and Wake-on-LAN without macOS or Swift.

## Build and open

Clone the repository, then run **one** of these from its root:

```sh
# LG webOS
cd "LG webOS 5.0"
bash scripts/build.sh
open dist/LGwebOS-menubar.app
```

```sh
# Roku OS
cd "Roku OS 15.3.4"
bash scripts/build.sh
open dist/Roku-menubar.app
```

Each app opens from the menu bar. Its settings can discover compatible TVs or accept a local IPv4 address. See the linked project guide for pairing, TV settings, compatibility notes, and diagnostics.

## Previews

| LG webOS | Roku OS |
| :---: | :---: |
| <img src="LG%20webOS%205.0/docs/media/overview-ps5-v2.png" alt="LG webOS remote overview" width="300"> | <img src="Roku%20OS%2015.3.4/docs/media/overview.png" alt="Roku OS remote overview" width="300"> |

The webOS app also has a [short demo](LG%20webOS%205.0/docs/media/demo-v2.gif). Its preview shows an earlier Portuguese build; the current interface is in English. The Roku app uses a separate purple theme and loads channel icons from the connected TV. Public Roku previews use a generic TV name.

## Privacy and compatibility

TV commands stay on your local network. Neither app needs an account or analytics service. TV addresses and preferences are saved on the Mac, not in this repository. The webOS app stores pairing credentials in Keychain. Do not post diagnostic reports, IP or MAC addresses, serial numbers, or pairing keys in issues.

The versions in the folder names are the versions tested so far, not a guarantee that other versions cannot work. Please include your TV operating-system version and a redacted error message when reporting a compatibility result.

## License

MIT; see [LICENSE](LICENSE). Brand assets and other third-party material are covered by the notices in each project folder.
