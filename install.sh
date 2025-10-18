#!/bin/bash
set -e

PROJECT_DIR=/home/admin/tagtracker
echo "Please have your firebase credentials handy. You will be prompted to enter them."

echo "[*] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "[*] Installing dependencies..."
#sudo apt-get install -y python3 python3-pip chromium-browser

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

# Setup systemd service
SERVICE_FILE=/etc/systemd/system/tagtracker.service
if [ ! -f "$SERVICE_FILE" ]; then
  echo "[*] Installing systemd service..."
  cat <<EOF | sudo tee "$SERVICE_FILE" > /dev/null
[Unit]
Description=TagTrackerFirebase
After=network.target

[Service]
ExecStart=/usr/bin/python3 $PROJECT_DIR/input_listener.py
Restart=always
User=admin
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/admin/.Xauthority
WorkingDirectory=$PROJECT_DIR

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
User=admin
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/admin/.Xauthority

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
echo "=====> YOU MUST CREATE hardwareIDS.json IN $PROJECT_DIR THAT CONTAINS THE PATH FOR YOUR ARDUINOS FOR THE PROGRAM TO WORK!!! <====="
