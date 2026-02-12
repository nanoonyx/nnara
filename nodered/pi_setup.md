# Raspberry Pi Node-RED Setup Guide

This guide details how to configure the Raspberry Pi as the central management hub for the LED control system.

## 1. Operating System & Prerequisites
- Install **Raspberry Pi OS Lite** (64-bit recommended).
- Ensure the Pi is connected to the same WiFi router as the Master ESP32s.
- Install Node.js (v18+) and npm.

## 2. Install Node-RED
```bash
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
```

## 3. Required Node-RED Nodes
Install these via the Palette Manager:
- `node-red-contrib-firebase-realtime` (or `node-red-contrib-firestore`)
- `@flowfuse/node-red-dashboard` (Dashboard 2.0)
- `node-red-contrib-mqtt-broker` (Aedes) - Or use a standalone Mosquitto broker on the Pi.

## 4. MQTT Broker Setup
- Install Mosquitto: `sudo apt install mosquitto mosquitto-clients`
- Enable on boot: `sudo systemctl enable mosquitto`

## 5. Firebase Integration
- Project: `nara-led-control` (or similar).
- Service Account: Generate a JSON key for the Node-RED Firebase nodes.
- Document Root: `/pillars/` and `/system/config/`.

## 6. Local Workspace
The Node-RED flow file should be synced/saved to:
`g:/My Drive/Proj/nara/nodered/flows.json`
