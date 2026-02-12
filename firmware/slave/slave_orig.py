import machine
import network
import espnow
import binascii
import json
import time
import asyncio
import aioble
import bluetooth
import gc
import nara_cmd

# --- Configuration ---
CONFIG_FILE = "nslave.json"
SERVICE_UUID = bluetooth.UUID(0xFFF0)
CHAR_UUID = bluetooth.UUID(0xFFF3)

config = {
    "sid": 1,
    "master": "24ec4aca5e20", # Fallback
    "ch": 11,
    "debug": 1
}

# --- Hardware ---
wdt = machine.WDT(timeout=300000)
adc = machine.ADC(machine.Pin(2))
led = machine.Pin(5, machine.Pin.OUT)

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            config.update(json.load(f))
    except: pass

async def send_ble_cmd(mac_hex, cmd_hex, retries=3):
    """Connect and send command to a specific LED pillar."""
    try:
        mac_bytes = binascii.unhexlify(mac_hex.replace(':','').replace('-',''))
        device = aioble.Device(aioble.ADDR_PUBLIC, mac_bytes)
        
        for i in range(retries):
            try:
                print(f"BLE Attempt {i+1} -> {mac_hex}")
                async with await device.connect(timeout_ms=2000) as connection:
                    service = await connection.service(SERVICE_UUID)
                    characteristic = await service.characteristic(CHAR_UUID)
                    
                    # Convert human cmd to hex if needed
                    final_hex = nara_cmd.MELK.get(cmd_hex.upper(), cmd_hex)
                    await characteristic.write(binascii.unhexlify(final_hex))
                    return True
            except Exception as e:
                print(f"BLE Retry {i+1} failed: {e}")
                await asyncio.sleep_ms(200)
    except Exception as ex:
        print("BLE Global Error:", ex)
    return False

class SlaveNode:
    def __init__(self):
        self.esp = espnow.ESPNow()
        self.esp.active(True)
        self.master_mac = binascii.unhexlify(config["master"])
        try:
            self.esp.add_peer(self.master_mac)
        except: pass

    async def handle_msg(self, mac, msg_bytes):
        # Strict Filtering: Only accept from Master
        if mac != self.master_mac:
            return

        try:
            data_str = msg_bytes.decode()
            print(f"Recv: {data_str}")
            
            # target|tid|cmd|pmac
            parts = data_str.split('|')
            if len(parts) < 3: return
            
            target = parts[0].upper()
            tid = parts[1]
            cmd = parts[2]
            pmac = parts[3] if len(parts) > 3 else ""

            # Check if this command is for me or global
            if target == "GLOBAL" or tid == str(config["sid"]) or tid == "all" or target == "PID":
                # If it's a PID command, use the provided PMAC
                # Otherwise, it might be a broadcast Color command (needs default/list PMAC handling)
                target_mac = pmac if pmac else "AA:BB:CC:DD:EE:FF" # Broad marker
                
                success = await send_ble_cmd(target_mac, cmd)
                
                # Report back to master
                status = "OK" if success else "NG"
                resp = f"RESP,{config['sid']},{cmd},{status},{target_mac}"
                self.esp.send(self.master_mac, resp)
                
        except Exception as e:
            print("Msg Error:", e)

    async def run(self):
        print(f"Slave {config['sid']} active on CH {config['ch']}")
        last_hbeat = 0
        while True:
            if self.esp.any():
                mac, msg = self.esp.recv()
                await self.handle_msg(mac, msg)
            
            if time.time() - last_hbeat > 30:
                last_hbeat = time.time()
                wdt.feed()
                bat = adc.read_uv() / 1000000 * 2 # Scale for 2S/Resistive divider
                self.esp.send(self.master_mac, f"STAT,{config['sid']},{bat:.2f}V")
                gc.collect()
                
            await asyncio.sleep(0.1)

async def main():
    load_config()
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    try: sta.config(channel=config["ch"])
    except: pass
    
    node = SlaveNode()
    await node.run()

if __name__ == "__main__":
    asyncio.run(main())
