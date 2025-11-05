#!/bin/bash
set -e

CURRENT_USER=$(whoami)
PROJECT_DIR=/home/$CURRENT_USER/Intellegent-Battery-Timer

echo "Please have your firebase credentials handy. You will be prompted to enter them."

echo "[*] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "[*] Installing dependencies..."
#sudo apt-get install -y python3 python3-pip chromium-browser #doesnt exist anymore?

echo "[*] Installing Python requirements..."
pip3 install --break-system-packages -r requirements.txt

echo "[*] Setting up project folder..."
mkdir -p "$PROJECT_DIR"

# Copy .env if it exists locally, but only if not already present in project dir
if [ -f .env ] && [ ! -f "$PROJECT_DIR/.env" ]; then
  cp .env "$PROJECT_DIR/"
  echo "[*] Copied existing .env into $PROJECT_DIR"
fi

# Firebase credentials
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "[*] Configuring Firebase..."
  read -p "Enter your Firebase Realtime Database URL: " FIREBASE_DB_BASE_URL
  read -p "Enter the full path to your Firebase service account JSON file: " FIREBASE_CREDS_FILE

  cat <<EOF > "$PROJECT_DIR/.env"
FIREBASE_DB_BASE_URL=$FIREBASE_DB_BASE_URL
FIREBASE_CREDS_FILE=$FIREBASE_CREDS_FILE
EOF

  echo "[*] Saved credentials to $PROJECT_DIR/.env"
else
  echo "[*] Skipping Firebase setup — $PROJECT_DIR/.env already exists."
fi

# Detect connected Arduino serial devices
# Detect connected Arduino serial devices
HARDWARE_FILE="$PROJECT_DIR/hardwareIDS.json"

if [ ! -f "$HARDWARE_FILE" ]; then
  echo
  echo "[*] Hardware ID setup starting..."

  # Step 1: Detect first Arduino
  echo
  echo "Please plug in ONLY the FIRST Arduino (COM_PORT1), then type 'yes' and press Enter when ready."
  read -r CONTINUE
  if [ "$CONTINUE" != "yes" ]; then
    echo "Aborting hardware ID detection."
    exit 1
  fi

  SERIAL_BEFORE=($(ls /dev/serial/by-id/* 2>/dev/null || true))
  echo "[*] Current connected serial devices:"
  printf ' - %s\n' "${SERIAL_BEFORE[@]}"
  echo
  echo "Now unplug all Arduinos, press Enter when ready."
  read -r

  SERIAL_NONE=($(ls /dev/serial/by-id/* 2>/dev/null || true))
  echo
  echo "[*] Now plug in the FIRST Arduino again, then type 'yes' to detect it."
  read -r CONFIRM1
  if [ "$CONFIRM1" != "yes" ]; then
    echo "Aborting hardware ID detection."
    exit 1
  fi

  SERIAL_AFTER1=($(ls /dev/serial/by-id/* 2>/dev/null || true))
  NEW1=$(comm -13 <(printf "%s\n" "${SERIAL_NONE[@]}" | sort) <(printf "%s\n" "${SERIAL_AFTER1[@]}" | sort))
  if [ -z "$NEW1" ]; then
    echo "[!] Could not detect new serial device for Arduino 1."
    exit 1
  fi
  PORT1="$NEW1"
  echo "COM_PORT1 set to $PORT1"

  # Step 2: Detect second Arduino
  echo
  echo "Now unplug the FIRST Arduino, then plug in ONLY the SECOND Arduino (COM_PORT2)."
  echo "Type 'yes' and press Enter when ready."
  read -r CONFIRM2
  if [ "$CONFIRM2" != "yes" ]; then
    echo "Aborting hardware ID detection."
    exit 1
  fi

  SERIAL_AFTER2=($(ls /dev/serial/by-id/* 2>/dev/null || true))
  NEW2=$(comm -13 <(printf "%s\n" "${SERIAL_NONE[@]}" | sort) <(printf "%s\n" "${SERIAL_AFTER2[@]}" | sort))
  if [ -z "$NEW2" ]; then
    echo "[!] Could not detect new serial device for Arduino 2."
    exit 1
  fi
  PORT2="$NEW2"
  echo "COM_PORT2 set to $PORT2"

  # Save both detected ports
  cat <<EOF > "$HARDWARE_FILE"
{
  "COM_PORT1": "$PORT1",
  "COM_PORT2": "$PORT2"
}
EOF

  echo "[*] Saved hardware IDs to $HARDWARE_FILE"
else
  echo "[*] Skipping hardware ID setup — $HARDWARE_FILE already exists."
fi


# Setup systemd service
SERVICE_FILE=/etc/systemd/system/tagtracker.service
if [ ! -f "$SERVICE_FILE" ]; then
  echo "[*] Installing systemd service..."
  sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=TagTrackerFirebase
After=network.target

[Service]
ExecStart=/usr/bin/python3 $(pwd)/input_listener.py
Restart=always
User=$(whoami)
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$(whoami)/.Xauthority
WorkingDirectory=$(pwd)

[Install]
WantedBy=graphical.target
EOF
else
  echo "[*] Skipping systemd service creation — $SERVICE_FILE already exists."
fi

# Open a web browser on boot
BROWSER_SERVICE=/etc/systemd/system/browser.service
if [ ! -f "$BROWSER_SERVICE" ]; then
  echo "[*] Setting up browser boot..."
  read -p "Enter the website you want to open on boot (do not include https://): " BOOTWEBSITE
  cat <<EOF | sudo tee "$BROWSER_SERVICE" > /dev/null
[Unit]
Description=Open Chromium at $BOOTWEBSITE
After=graphical.target

[Service]
ExecStart=chromium-browser --noerrdialogs --disable-infobars --kiosk https://$BOOTWEBSITE
Restart=always
User=$CURRENT_USER
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$CURRENT_USER/.Xauthority

[Install]
WantedBy=graphical.target
EOF
else
  echo "[*] Skipping browser service creation — $BROWSER_SERVICE already exists."
fi

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable tagtracker.service
sudo systemctl enable browser.service
sudo systemctl restart tagtracker.service
sudo systemctl restart browser.service

echo "[*] Installation complete! Reboot to start the program."