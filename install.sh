#!/bin/bash
set -e

echo "[*] Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "[*] Installing dependencies..."
sudo apt-get install -y python3 python3-pip chromium-browser

echo "[*] Installing Python requirements..."
pip3 install -r requirements.txt

echo "[*] Setting up project folder..."
mkdir -p /home/pi/tagtracker
cp myscript.py /home/pi/tagtracker/
cp requirements.txt /home/pi/tagtracker/

# Copy .env if you use one
if [ -f .env ]; then
  cp .env /home/pi/tagtracker/
fi

# --- Setup systemd service ---
echo "[*] Installing systemd service..."
cat <<EOF | sudo tee /etc/systemd/system/autostart.service > /dev/null
[Unit]
Description=TagTrackerFirebase
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/tagtracker/input_listener.py
Restart=always
User=pi
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
WorkingDirectory=/home/pi/tagtracker

[Install]
WantedBy=graphical.target
EOF

sudo systemctl enable tagtracker.service

echo "[*] Installation complete! Reboot to start the program."
