import network
import espnow
from umqtt.simple import MQTTClient
import json
import time
import binascii
import machine
import esp32
import nara_cmd

# --- Configuration & State ---
CONFIG_FILE = "nmaster.json"
SID_FILE = "msids.json"

config = {
    "mid": "MA",
    "ch": 11,
    "debug": 1,
    "ssid": "nano",
    "password": "@wooam1004",
    "mqtt_broker": "192.168.45.241",
    "mqtt_topic_stat": "nara/master/status"
}

sids = {} # MAC: SID
bcast = b'\xff' * 6

# --- Hardware ---
wdt = machine.WDT(timeout=300000)
led = machine.Pin(5, machine.Pin.OUT)

# --- Helpers ---
def load_config():
    global config, sids
    try:
        with open(CONFIG_FILE, "r") as f:
            config.update(json.load(f))
    except: pass
    try:
        with open(SID_FILE, "r") as f:
            data = json.load(f)
            # Handle nested "sids" key if present
            if "sids" in data:
                sids.update(data["sids"])
            else:
                sids.update(data)
    except: pass

def save_state():
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
        with open(SID_FILE, "w") as f:
            json.dump(sids, f)
    except: pass

def get_mac_by_sid(target_sid):
    for mac, sid in sids.items():
        if str(sid) == str(target_sid):
            return binascii.unhexlify(mac)
    return None

# --- Dispatch Handlers ---
def handle_mdebug(args):
    config['debug'] = int(args[0]) if args else (0 if config['debug'] else 1)
    print(f"DEBUG: {config['debug']}")
    save_state()

def handle_mreset(args):
    machine.reset()

MASTER_DISPATCH = {
    "MDEBUG": handle_mdebug,
    "MRESET": handle_mreset,
    "MREBOOT": handle_mreset
}

# --- MQTT Callback ---
def mqtt_callback(topic, msg):
    try:
        t_str = topic.decode()
        m_str = msg.decode()
        if config['debug']:
            print(f"[{t_str}] {m_str}")
        data = json.loads(m_str)
        
        # Prevent double processing (incomplete message)
        if 'target' not in data and 'id' not in data:
            if config['debug']: print("Ignored: Missing target/id")
            return
        
        target = data.get('target', 'Global').upper()
        
        # Filter: If the message has no 'cmd' and is not a valid structure, ignore.
        if 'cmd' not in data:
            return

        tid = data.get('id', 'all')
        raw_cmd = data.get('cmd', '').upper()

        dst = data.get('dst', 'broadcast')
        pmac = data.get('pmac', '')

        # 1. Check Master Dispatch
        if raw_cmd in MASTER_DISPATCH:
            MASTER_DISPATCH[raw_cmd]([])
            return

        # 2. Routing via nara_cmd
        final_cmd = raw_cmd
        if raw_cmd in nara_cmd.MELK:
            final_cmd = nara_cmd.MELK[raw_cmd]
        
        # 3. Construct Payload
        # data format: target|tid|cmd|pmac
        payload = f"{target}|{tid}|{final_cmd}|{pmac}"
        
        target_mac = bcast
        if dst != "broadcast":
            target_mac = binascii.unhexlify(dst.replace(':','').replace('-',''))
            try: e.add_peer(target_mac)
            except: pass
        
        e.send(target_mac, payload)
        if config['debug']:
            print(f"FWD -> {dst}: {payload}")
            
    except Exception as ex:
        print("MQTT Error:", ex)

# --- ESP-NOW Callbacks ---
def recv_cb(esp):
    while True:
        mac, msg = esp.irecv(0)
        if mac is None: break
        
        mac_hex = mac.hex()
        
        # STRICT FILTERING: Ignore unknown peers
        # Exception: Allow NARAINIT for pairing
        msg_str = msg.decode()
        if "NARAINIT" in msg_str:
            # Pairing Mode
            parts = msg_str.split(',')
            if len(parts) > 1:
                sids[mac_hex] = parts[1]
                save_state()
                # Auto-add peer
                try: e.add_peer(mac)
                except: pass
                print(f"Paired: {parts[1]} ({mac_hex})")
        
        elif mac_hex not in sids:
            if config['debug']: print(f"Ignored unknown peer: {mac_hex}")
            continue

        # Valid Message Processing
        sid_name = sids.get(mac_hex, mac_hex)
        status_payload = {
            "sid": sid_name,
            "mac": mac_hex,
            "msg": msg_str,
            "time": time.time()
        }
        client.publish(config["mqtt_topic_stat"], json.dumps(status_payload))

# --- Initialization ---
load_config()
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(config["ssid"], config["password"])

while not wlan.isconnected():
    time.sleep(0.5)
    print("WiFi...")

# ESP-NOW
e = espnow.ESPNow()
e.active(True)
e.add_peer(bcast)
e.irq(recv_cb)

# MQTT
client = MQTTClient(f"NaraMaster_{config['mid']}", config["mqtt_broker"])
client.set_callback(mqtt_callback)
client.connect()
client.subscribe(b"nara/master/global")
client.subscribe(b"nara/slave/#")
client.subscribe(b"nara/group/#")

print(f"Master {config['mid']} Online")

# --- Main Loop ---
last_hbeat = 0
while True:
    try:
        client.check_msg()
    except:
        try: client.connect()
        except: pass
        
    if time.time() - last_hbeat > 60:
        last_hbeat = time.time()
        wdt.feed()
        client.publish(config["mqtt_topic_stat"], json.dumps({"mid": config['mid'], "status": "online"}))
    
    time.sleep(0.1)
