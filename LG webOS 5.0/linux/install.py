#!/usr/bin/python3
"""Install a self-contained copy and application launcher for the current user."""
import os
from pathlib import Path
import shutil
import subprocess


def desktop_quote(value):
    # Desktop Entry Exec quoting is different from shell quoting. Percent is a field code.
    quoted = ''.join('\\' + char if char in '\\"`$' else char for char in str(value))
    return '"' + quoted.replace('\\', '\\\\').replace('%', '%%') + '"'


def main():
    source = Path(__file__).resolve().parent
    subprocess.run(["/usr/bin/python3", str(source / "app.py"), "--check"], check=True)
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    target = data / "lgwebos-menubar"
    applications = data / "applications"
    target.mkdir(parents=True, exist_ok=True)
    applications.mkdir(parents=True, exist_ok=True)
    for name in ("app.py", "webos.py", "network.py", "storage.py", "ui.py", "macros.py"):
        shutil.copy2(source / name, target / name)
    shutil.copytree(source / "assets", target / "assets", dirs_exist_ok=True)
    resources = source.parent / "Sources/LGwebOSMenubar"
    shutil.copy2(resources / "app-catalog.json", target / "app-catalog.json")
    shutil.copytree(resources / "AppAssets", target / "AppAssets", dirs_exist_ok=True)
    shutil.copy2(source.parent / "THIRD_PARTY_NOTICES.md", target / "THIRD_PARTY_NOTICES.md")
    shutil.copy2(source.parent.parent / "LICENSE", target / "LICENSE")
    icons = data / "icons/hicolor/scalable/apps"
    icons.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "assets/lgwebos.svg", icons / "io.github.lgwebos.Menubar.svg")
    shutil.copy2(source.parent / "Sources/LGwebOSMenubar/registration.json", target / "registration.json")
    desktop = applications / "io.github.lgwebos.Menubar.desktop"
    desktop.write_text("[Desktop Entry]\nType=Application\nName=LG webOS Remote\n"
                       "Comment=Control an LG webOS TV on your local network\n"
                       "Exec=/usr/bin/python3 " + desktop_quote(target / "app.py") + "\n"
                       "Icon=io.github.lgwebos.Menubar\nTerminal=false\nCategories=AudioVideo;\n"
                       "StartupNotify=true\nStartupWMClass=app.py\n")
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(applications)], check=True)
    if shutil.which("gtk-update-icon-cache") and (data / "icons/hicolor/index.theme").exists():
        subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(data / "icons/hicolor")], check=True)
    print(f"Installed LG webOS Remote: {desktop}")
    print("Launch it from the applications menu, or: gtk-launch io.github.lgwebos.Menubar")


if __name__ == "__main__":
    main()
