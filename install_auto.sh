#!/bin/bash

# ----------------------------
# PiMark Auto Installer
# ----------------------------

# Aktuális felhasználó HOME könyvtára
USER_HOME=$(eval echo "~$USER")
DOWNLOADS_DIR="$USER_HOME/Downloads"

# Telepítési könyvtár
INSTALL_DIR="$USER_HOME/PiMark-main"
DESKTOP_FILE="$INSTALL_DIR/PiMark Pro.desktop"
DESKTOP_SHORTCUT="$USER_HOME/Desktop/PiMark Pro.desktop"

# Ha már van korábbi telepítés, töröljük az egész mappát
if [ -d "$INSTALL_DIR" ]; then
    echo "Old PiMark installation found. Removing..."
    rm -rf "$INSTALL_DIR"
fi

# Download előtti ZIP-ek törlése a Downloads mappából
echo "Removing old PiMark zip files from Downloads..."
rm -f "$DOWNLOADS_DIR"/PiMark-Pro*.zip
rm -f "$DOWNLOADS_DIR"/PiMark-Pro*.tar.gz

# Git clone a legfrissebb verzióból
echo "Downloading PiMark from GitHub..."
git clone https://github.com/D4rk926/PiMark-Pro.git "$INSTALL_DIR"

# Ellenőrizzük, hogy sikerült-e a clone
if [ ! -d "$INSTALL_DIR" ]; then
    echo "ERROR: Could not download PiMark from GitHub!"
    exit 1
fi

# →→→ MINDEN fájl törlése, kivéve PiMonitor.py-t ←←←
echo "Cleaning installation folder..."

find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name "PiMark.py" -exec rm -rf {} \;

# Futtathatóvá tesszük a PiMark.py-t
chmod +x "$INSTALL_DIR/PiMark.py"

# .desktop fájl létrehozása
cat <<EOL > "$DESKTOP_FILE"
[Desktop Entry]
Name=PiMark Pro
Comment=Test your Raspberry Pi!
Exec=python3 $INSTALL_DIR/PiMark.py
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Utility;
EOL

# Desktop shortcut létrehozása
cp "$DESKTOP_FILE" "$DESKTOP_SHORTCUT"
chmod +x "$DESKTOP_SHORTCUT"

echo "Download ready! You can now launch PiMark from your Desktop."