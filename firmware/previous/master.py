import os
import gc
import sys
import time
import json
import select
import binascii
import machine
import network
import espnow
import esp32
import nara_cmd

try:
    from umqtt.simple import MQTTClient
except ImportError:
    MQTTClient = None

# --- Constants & Configuration ---
VER = "nmaster_0210e"
CONFIG_FILE = "nmaster.json"

# --- Global State ---
mid = "MA"      # Master ID (MA or MB)
ch = 11         # ESP-NOW Channel
DEBUG = False   # Debug mode flag

config_data = {}
sid_data = {}
sids = {}       # SID to MAC mapping
macs_replied = set()
last_tick = time.ticks_ms()
ack_received = -1

# Command Lists
MELK = nara_cmd.MELK
SCMD = nara_cmd.SCMD

# Hardware
wdt = machine.WDT(timeout=300000)
led = machine.Pin(5, machine.Pin.OUT)
mqtt_client = None
esp = None
bcast = b"\xff" * 6


# --- Utility Helpers ---

def log(arg=None):
    """Debug logger with master identification."""
    if DEBUG:
        print(f"{mid},.,{arg if arg is not None else time.ticks_ms()}")


def read_json_file(filename):
    """Reliably read and parse a JSON file."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as err:
        print(f"{mid},NG,Failed to read {filename}: {err}")
        return {}


def get_key_by_value(dictionary, target_value):
    """Find a dictionary key based on its value."""
    return next(
        (key for key, value in dictionary.items() if value == target_value), None
    )


def print_response(prefix, cmd, content):
    """Standardized response printer: {mid},[PREFIX],CMD,CONTENT"""
    # Replace "A" with mid for cleaner answer lines, or prefix others
    p = mid if prefix == "A" else f"{mid},{prefix}"
    line = f"{p},{cmd},{content}"
    print(line)
    mqtt_publish(line)


# --- Network & Transport Logic ---

def connect_wifi():
    """Establish WiFi connection based on config_data."""
    ssid = config_data.get("ssid")
    password = config_data.get("password")
    if not ssid:
        print(f"{mid},NG,WiFi,No SSID in config")
        return False
    
    print(f"{mid},.,WiFi,Connecting to {ssid}...")
    sta.active(True)
    sta.connect(ssid, password)
    
    # Wait for connection
    timeout = 15
    start = time.time()
    while not sta.isconnected():
        if time.time() - start > timeout:
            print(f"{mid},NG,WiFi,Connection timeout")
            return False
        time.sleep(1)
        print(".", end="")
    
    print(f"\n{mid},WiFi,Connected IP:{sta.ifconfig()[0]}")
    return True


def mqtt_publish(msg):
    """Publish a message to the status topic."""
    if mqtt_client:
        try:
            topic = config_data.get("mqtt_topic_stat", "nara/stat")
            mqtt_client.publish(topic, msg)
        except:
            pass


def mqtt_callback(topic, msg):
    """Handle incoming MQTT messages."""
    try:
        line = msg.decode().strip()
        print(f"{mid},.,MQTT,Recv:{line}")
        handle_incoming_command(line)
    except Exception as e:
        print(f"{mid},NG,MQTT,Callback error:{e}")


def recv_cb(esp_obj):
    """ESP-NOW receive callback."""
    while True:
        try:
            mac_addr, payload = esp_obj.irecv(0)
            if mac_addr is None:
                break
            
            mac_hex = mac_addr.hex()
            macs_replied.add(mac_hex)
            
            try:
                decoded_msg = payload.decode()
            except UnicodeError:
                decoded_msg = str(payload)

            # Intercept ACK for blocking functions like scmd_fwsend
            # format: FWUPDATE,ACK,SEQ
            is_fw_ack = False
            if decoded_msg.startswith("FWUPDATE,ACK"):
                is_fw_ack = True
                try:
                    parts = decoded_msg.split(",")
                    ack_seq = int(parts[2])
                    global ack_received
                    ack_received = ack_seq
                except:
                    pass

            # Don't print/publish ACK messages to reduce dashboard clutter
            if is_fw_ack:
                continue

            if mac_hex in sids:
                sid_name = sids[mac_hex]
                msg_line = f"{sid_name},{decoded_msg}"
                if DEBUG:
                    print(msg_line)
                    mqtt_publish(msg_line)
                else:
                    if payload and payload[0] != 46:  # b"." (dot)
                        print(msg_line)
                        mqtt_publish(msg_line)
            else:
                if DEBUG:
                    msg_line = f"{mac_hex},{decoded_msg}"
                    print(msg_line)
                    mqtt_publish(msg_line)

        except Exception as err:
            print(f"{mid},NG,recv_cb error,{err}")


def msend(msg, target_id="a"):
    """Send a message via ESP-NOW to target SIDs or broadcast."""
    log(f"msend({msg},{target_id})")
    try:
        if not msg:
            return False

        target_id_str = str(target_id)

        if target_id_str == "b":
            esp.send(bcast, msg.encode())
            return True
        elif target_id_str == "a":
            try:
                esp.send(msg.encode())  # to registered peers
            except:
                return True
            return True
        elif target_id_str == "0":
            for s in sids:
                try:
                    esp.send(binascii.unhexlify(s), msg.encode())
                except:
                    pass
            return True
        else:
            if target_id_str.lower().startswith("s"):
                target_id = target_id_str[1:]
            
            peer_hex = get_key_by_value(sids, target_id)
            if not peer_hex and isinstance(target_id, str) and target_id.isdigit():
                peer_hex = get_key_by_value(sids, int(target_id))

            if peer_hex:
                try:
                    return esp.send(binascii.unhexlify(peer_hex), msg.encode())
                except:
                    return False
            else:
                log(f"NG,msend,Unknown Target {target_id}.")
                return False
    except:
        return False


# --- Master Command Handlers ---

def handle_mdebug(parts):
    """Handle MDEBUG command to set/get debug level."""
    global DEBUG
    # Arguments: [CMD, (MID), VAL]
    val_idx = 2 if len(parts) > 1 and str(parts[1]).upper() == mid.upper() else 1
    
    if len(parts) > val_idx:
        try:
            DEBUG = int(parts[val_idx])
        except ValueError:
            pass
    print_response("A", "MDEBUG", DEBUG)


def handle_mpeer(parts):
    """List connected ESP-NOW peers."""
    try:
        if len(esp.peers_table) > 0:
            peers = {
                sids.get(p.hex(), "?"): [esp.peers_table[p], p.hex()[-4:]]
                for p in esp.peers_table
            }
            print_response("A", "MPEER", peers)
        else:
            print_response("NG", "MPEER", "No peers yet")
    except Exception as e:
        print_response("NG", "MPEER", f"Error: {e}")


def handle_msid(parts):
    """Manage SID to MAC mappings: List, Add, Update, or Delete."""
    sns = ""
    # Arguments: [CMD, (MID), VAL, (MAC)]
    args = parts[1:]
    if args and str(args[0]).upper() == mid.upper():
        args = args[1:]
    
    # Handle optional split artifacts from handle_incoming_command commas
    flat_args = []
    for a in args:
        if isinstance(a, str) and "," in a:
            flat_args.extend(a.split(","))
        else:
            flat_args.append(a)

    if not flat_args:
        sns = f"{sorted(sids.values())}"
    else:
        try:
            sid_val = flat_args[0]
            try:
                sid_val = int(sid_val)
            except ValueError:
                pass

            if sid_val == 0:
                sns = f"{sorted(sids.values())}"
            elif isinstance(sid_val, int) and sid_val < 0:
                key = get_key_by_value(sids, abs(sid_val))
                if key: sids.pop(key)
                sns = f"{sorted(sids.values())}"
            elif len(flat_args) >= 2:
                mac_to_add = flat_args[1]
                sids[mac_to_add] = sid_val
                sns = f"{sorted(sids.values())}"
            else:
                key = get_key_by_value(sids, sid_val)
                sns = f"{sid_val}:{key}"
        except Exception as e:
            sns = f"Error: {e}"

    if sns:
        print_response("A", "MSID", sns)


def handle_mconfig(parts):
    """Report current master configuration."""
    print_response("A", "MCONFIG", config_data)


def handle_mstat(parts):
    """Report master status and temperature."""
    print_response("A", "MSTAT", f"{{{sm},T:{esp32.mcu_temperature()}}}")


def handle_msave(parts):
    """Save current configuration and resetting."""
    config_data["mid"] = mid
    config_data["channel"] = ch
    config_data["debug"] = DEBUG
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f)
        
        # Save master-specific msids file
        msids_file = f"msids_{mid.lower()}.json"
        sid_data["sids"] = sids
        with open(msids_file, "w") as f:
            json.dump(sid_data, f)
            
        print_response("A", "MSAVE", "Saved. Resetting...")
        time.sleep(1)
        machine.reset()
    except Exception as e:
        print_response("NG", "MSAVE", f"Write failed: {e}")


def handle_mreset(parts):
    log("Reset")
    time.sleep(1)
    machine.reset()


def handle_mdir(parts):
    try:
        files = os.listdir()
        print_response("A", "MDIR", files)
    except Exception as e:
        print_response("NG", "MDIR", f"Error: {e}")


def handle_mhelp(parts):
    m_list = sorted(list(MASTER_DISPATCH.keys()))
    s_list = sorted(list(SLAVE_DISPATCH.keys()))
    print_response("A", "MHELP", f"{m_list},{s_list}")

def handle_shelp(parts):
    print_response("A", "SHELP", f"{SCMD},{list(MELK.keys())}")

MASTER_DISPATCH = {
    "MDEBUG": handle_mdebug,
    "MPEER": handle_mpeer,
    "MPEERS": handle_mpeer,
    "MSID": handle_msid,
    "MSIDS": handle_msid,
    "MCONFIG": handle_mconfig,
    "MSTAT": handle_mstat,
    "MSTATUS": handle_mstat,
    "MSAVE": handle_msave,
    "MRESET": handle_mreset,
    "MREBOOT": handle_mreset,
    "MDIR": handle_mdir,
    "MHELP": handle_mhelp,
    "SHELP": handle_shelp,
    "?": handle_mhelp,
}


# --- Slave Command Handlers ---

def scmd_scan(cmd, parts, sid, line):
    """Scan for responding slave nodes."""
    global macs_replied
    macs_replied = set()
    if msend("NARA", sid):
        time.sleep(1.5)
        replied_snames = [sids.get(m, m) for m in macs_replied]
        print_response("A", cmd, replied_snames)
    else:
        print_response("NG", cmd, "msend failed")


def scmd_forward(cmd, parts, sid, line):
    """Default forwarder for SCMD and Color codes."""
    msg_to_send = ""
    val = ("," + parts[2]) if len(parts) > 2 else ""
    
    if cmd in MELK:
        msg_to_send = MELK.get(cmd, cmd) + val
    else:
        msg_to_send = cmd + val

    if not msend(msg_to_send, sid):
        print_response("NG", "msend", line)


def scmd_set_master(cmd, parts, sid, line):
    """Set the slave's master address to this device's MAC."""
    msend(f"{cmd},{mac.hex()}", sid)


def scmd_fwsend(cmd, parts, sid, line):
    """Firmware update handler: Sends a file to a slave via chunks."""
    if len(parts) < 3:
        print_response("NG", cmd, "Missing filename arg")
        return
    
    args = parts[2].split(",")
    filename = args[0]

    try:
        with open(filename, "rb") as f:
            content = f.read()
    except:
        print_response("NG", cmd, f"Failed to read {filename}")
        return

    size = len(content)
    checksum = sum(content) & 0xFFFFFFFF
    basename = args[1] if len(args) > 1 else filename.replace("\\", "/").split("/")[-1]

    log(f"Start Update {filename} as {basename} to {sid}, size={size}")

    # 1. Start Phase
    if not msend(f"FWUPDATE,START,{size},{checksum},{basename}", sid):
        print_response("NG", cmd, "Start failed")
        return

    time.sleep(0.5)

    # 2. Data Phase
    chunk_size = 90
    total_chunks = (size + chunk_size - 1) // chunk_size

    for i in range(total_chunks):
        chunk = content[i * chunk_size : (i + 1) * chunk_size]
        msg = f"FWUPDATE,DATA,{i},{binascii.hexlify(chunk).decode()}"

        if not msend(msg, sid):
            print(f"{mid},NG,Chunk {i} send failed")

        if i % 5 == 0:
            retries, success = 0, False
            global ack_received
            while retries < 5:
                ack_received = -1
                wait_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), wait_start) < 2000:
                    time.sleep(0.01)
                    if ack_received == i:
                        success = True
                        break
                if success: break
                
                retries += 1
                print(f"{mid},.,Retry {i} ({retries}/5)")
                msend(msg, sid)

            if not success:
                print_response("NG", cmd, f"Failed at chunk {i} after 5 retries")
                return

            print(f"{mid},.,Progress {i}/{total_chunks}")

    # 3. End Phase
    time.sleep(0.5)
    msend("FWUPDATE,END", sid)
    print_response("A", cmd, "Update Sent")


SLAVE_DISPATCH = {
    "NARA": scmd_scan,
    "SSCAN": scmd_scan,
    "MSCAN": scmd_scan,
    "SETMASTER": scmd_set_master,
    "FWSEND": scmd_fwsend,
    # Default fallback for MELK and SCMD is scmd_forward
}


def handle_slave_command_route(cmd, parts, sid, line):
    """Route slave commands to specific handlers or forwarders."""
    if cmd in SLAVE_DISPATCH:
        SLAVE_DISPATCH[cmd](cmd, parts, sid, line)
    else:
        scmd_forward(cmd, parts, sid, line)


def handle_incoming_command(line):
    """Parse, filter, and dispatch incoming commands from MQTT or Serial."""
    if not line: return
    
    global last_tick
    wdt.feed()
    last_tick = time.ticks_ms()
    
    # Normalize and split: [CMD, TARGET, VALUE/REST]
    normalized_line = line.replace(" ", ",")
    parts = normalized_line.split(",", 2)
    cmd = parts[0].upper()

    # Determine SID (Target)
    sid = "a"
    if len(parts) > 1:
        input_sid = parts[1]
        try:
            sid = int(input_sid)
        except ValueError:
            sid = input_sid

    # Master ID Filtering: Ignore commands for other masters
    if isinstance(sid, str) and sid.upper() in ["MA", "MB"]:
        if sid.upper() != mid.upper():
            log(f"Ignore, Target {sid} is not this master {mid}")
            return
    
    # Dispatch Logic
    if cmd in MASTER_DISPATCH:
        MASTER_DISPATCH[cmd](parts)
    else:
        # Slave command filtering logic
        sid_min = config_data.get("sid_min", 1)
        sid_max = config_data.get("sid_max", 30)
        should_process = False
        
        if isinstance(sid, str):
            if sid.lower() in ["a", "b", "0"]:
                should_process = True
            elif sid.lower().startswith("s"):
                try:
                    sid_num = int(sid[1:])
                    should_process = (sid_min <= sid_num <= sid_max)
                except:
                    pass
        elif isinstance(sid, int):
            should_process = (sid_min <= sid <= sid_max)
        
        if should_process:
            handle_slave_command_route(cmd, parts, sid, line)
        else:
            log(f"Ignore, SID {sid} not in range {sid_min}-{sid_max}")


# --- Initialization ---

# --- Initial Global Setup ---
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()

def init_system():
    """Load configuration and initialize hardware and networking."""
    global mid, ch, DEBUG, config_data, sids, sid_data, mqtt_client, esp, poller, sm

    # 1. Load Configuration
    try:
        config_data = read_json_file(CONFIG_FILE)
        mid = config_data.get("mid", mid)
        ch = config_data.get("ch", 11)
        DEBUG = config_data.get("debug", 0)
        
        # Load SID mapping
        msids_file = f"msids_{mid.lower()}.json"
        sid_data = read_json_file(msids_file)
        sids = sid_data.get("sids", {})
    except Exception as err:
        print(f"{mid},NG,Init,Config load error: {err}")

    # 2. Hardware Intro
    sm = f"S:{mid},M:{sta.config('mac').hex()},C:{ch},T:{esp32.mcu_temperature()},V:{VER}"
    print(f"{mid},ON,{sm}")
    log(f"sids: {sorted(sids.values())}")

    # 3. WiFi & MQTT Setup
    if connect_wifi():
        broker = config_data.get("mqtt_broker")
        topic = config_data.get("mqtt_topic", "nara/cmd")
        if broker and MQTTClient:
            try:
                client_id = f"nara_master_{mid}"
                mqtt_client = MQTTClient(client_id, broker)
                mqtt_client.set_callback(mqtt_callback)
                mqtt_client.connect()
                mqtt_client.subscribe(topic)
                print(f"{mid},MQTT,Subscribed to {topic} at {broker}")
            except Exception as e:
                print(f"{mid},NG,MQTT,Setup failed: {e}")
                mqtt_client = None

    # 4. ESP-NOW Setup
    esp = espnow.ESPNow()
    esp.config(rxbuf=1024)
    esp.active(True)
    esp.irq(recv_cb)

    # Add SID Peers
    for s in sids:
        try:
            esp.add_peer(binascii.unhexlify(s))
        except:
            pass

    # Add Broadcast Peer
    try:
        esp.add_peer(bcast)
    except:
        pass

    # 5. Poller Setup
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    led.value(1)

# Run initialization
init_system()


# --- Main Operational Loop ---

while True:
    # 1. Process MQTT
    if config_data.get("wifi_flag", 1) and mqtt_client:
        try:
            mqtt_client.check_msg()
        except Exception as e:
            if config_data.get("wifi_flag", 1):
                print(f"{mid},NG,MQTT,Check failed: {e}")

    # 2. Process Serial
    events = poller.poll(1)
    if events:
        line = sys.stdin.readline().strip()
        if line:
            handle_incoming_command(line)

    # 3. System Maintenance
    if time.ticks_diff(time.ticks_ms(), last_tick) > 60000:
        wdt.feed()
        gc.collect()
        last_tick = time.ticks_ms()
        if config_data.get("wifi_flag", 1) and not mqtt_client:
            print(f"{mid},NG,No mqtt_client for 1 minute, restarting...")
            machine.reset()

