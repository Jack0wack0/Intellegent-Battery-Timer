This is the script to install onto a Raspberry pi.

Run:
chmod +x install.sh
./install.sh

Reboot your pi and the script should start automatically. You must have a credentials file from firebase downloaded to the machine before you run the install script. 
You must have your firebase realtime database link ready also. 

After you have ran the install script, plug in your arduinos and run:
ls /dev/serial/by-id/*

copy down the IDs provided and create hardwareIDS.json in the same directory as input_listener.py (usually /pi/tagtracker/*)
paste the IDs into hardwareIDS.json

Arduino code must also be uploaded. Arduino code is located in this repository: https://github.com/Jack0wack0/Intellegent-Battery-Timer-Arduino-Code
