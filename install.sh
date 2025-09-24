#!/bin/bash
set -e

echo "[*] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "[*] Installing dependencies..."
sudo apt-get install -y python3 python3-pip chromium-browser

echo "[*] Installing Python requirements..."
pip3 install --break-system-packages -r requirements.txt

echo "[*] Setting up project folder..."
mkdir -p /home/pi/tagtracker
cp myscript.py /home/admin/tagtracker/
cp requirements.txt /home/admin/tagtracker/

# Copy .env if you use one
if [ -f .env ]; then
  cp .env /home/admin/tagtracker/
fi

# Firebase credentials
echo "[*] Configuring Firebase..."
read -p "Enter your Firebase Realtime Database URL: " FIREBASE_DB_BASE_URL
read -p "Enter the full path to your Firebase service account JSON file: " FIREBASE_CREDS_FILE

# Create .env file
cat <<EOF > /home/admin/myproject/.env
FIREBASE_DB_BASE_URL=$FIREBASE_DB_BASE_URL
FIREBASE_CREDS_FILE=$FIREBASE_CREDS_FILE
EOF

echo "[*] Saved credentials to /home/admin/myproject/.env"

# Setup systemd service 
echo "[*] Installing systemd service..."
cat <<EOF | sudo tee /etc/systemd/system/autostart.service > /dev/null
[Unit]
Description=TagTrackerFirebase
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/admin/tagtracker/input_listener.py
Restart=always
User=admin
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/admin/.Xauthority
WorkingDirectory=/home/admin/tagtracker

[Install]
WantedBy=graphical.target
EOF

sudo systemctl enable tagtracker.service

# Open a web browser on boot
echo "[*] Setting up browser boot..."
read -p "Enter the website you want to open on boot (do not include https://): " BOOTWEBSITE
cat <<EOF | sudo tee /etc/systemd/system/browser.service > /dev/null
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

sudo systemctl enable browser.service

echo "[*] Installation complete! Reboot to start the program."
echo "=====> YOU MUST CREATE hardwareIDS.json THAT CONTAINS THE PATH FOR YOUR ARDUINOS FOR THE PROGRAM TO WORK!!! <====="
