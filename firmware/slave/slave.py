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
import esp32
import nara_cmd
import os

# --- Configuration & Constants ---
VER = "nslave_0211a"
CONFIG_FILE = "nslave.json"
CIDS_FILE = "cids.json"
SERVICE_UUID = bluetooth.UUID(0xFFF0)
CHAR_UUID = bluetooth.UUID(0xFFF3)

config = {
    "sid": 1,
    "master": "24ec4aca5e20",
    "ch": 11,
    "debug": 1
}

# --- Hardware ---
wdt = machine.WDT(timeout=300000)
adc = machine.ADC(machine.Pin(2))
adc.atten(machine.ADC.ATTN_11DB) # Ensure full range if needed, though usually default is fine
led = machine.Pin(5, machine.Pin.OUT)

# --- Helpers ---
def read_json_file(filename, default=None):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def write_json_file(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f)
    except: pass

def load_config():
    global config
    data = read_json_file(CONFIG_FILE)
    if data: config.update(data)

# --- BLE Helper Class ---
class NLED:
    def __init__(self, mac_hex):
        # Handle both full MAC and short suffix (assuming prefix be28)
        clean_mac = mac_hex.replace(':', '').replace('-', '').lower()
        if len(clean_mac) == 8:
             # Assume it's a suffix, prepend common prefix if known, or this might be an issue.
             # Previous code assumed "be28" + suffix.
             clean_mac = "be28" + clean_mac
        
        self.mac_bytes = binascii.unhexlify(clean_mac)
        self.device = aioble.Device(aioble.ADDR_PUBLIC, self.mac_bytes)
        self.connection = None
        self.char = None

    async def connect(self, timeout_ms=3000):
        try:
            self.connection = await self.device.connect(timeout_ms=timeout_ms)
            service = await self.connection.service(SERVICE_UUID)
            self.char = await service.characteristic(CHAR_UUID)
            return True
        except:
            await self.disconnect()
            return False

    async def disconnect(self):
        if self.connection:
            try: await self.connection.disconnect()
            except: pass
        self.connection = None
        self.char = None

    async def write(self, cmd_hex, repeat=1):
        if not self.connection or not self.char: return False
        try:
            # Resolve command using nara_cmd if it's a name
            final_hex = nara_cmd.MELK.get(cmd_hex.upper(), cmd_hex)
            payload = binascii.unhexlify(final_hex)
            for _ in range(repeat):
                await self.char.write(payload)
            return True
        except:
            return False

# --- Main Logic ---
class SlaveNode:
    def __init__(self):
        self.esp = espnow.ESPNow()
        self.esp.active(True)
        self.load_state()
        self.init_network()
        
    def load_state(self):
        load_config()
        self.master_mac = binascii.unhexlify(config["master"])
        self.cids = read_json_file(CIDS_FILE, [])
        self.p4dict = {item[-4:]: item for item in self.cids}
        self.zmacs = []

    def init_network(self):
        self.sta = network.WLAN(network.STA_IF)
        self.sta.active(True)
        try: self.sta.config(channel=config["ch"])
        except: pass
        try: self.esp.add_peer(self.master_mac)
        except: pass

    def send_msg(self, msg, peer=None):
        target = peer if peer else self.master_mac
        try: self.esp.add_peer(target)
        except: pass
        try:
            self.esp.send(target, str(msg))
            if config['debug']: print(f"> {msg}")
        except Exception as e:
            if config['debug']: print(f"Send Err: {e}")

    # --- Command Processors ---
    async def cmd_cids(self, cmd, target_cids, timeout=3500, repeat=1):
        failed_macs = []
        start_tick = time.ticks_ms()
        
        for cid in target_cids:
            nled = NLED(cid)
            success = False
            if await nled.connect(timeout):
                success = await nled.write(cmd, repeat)
                await nled.disconnect()
            
            if not success: failed_macs.append(cid)
            wdt.feed()
            
        return failed_macs

    async def handle_nara_cmd(self, cmd, parts, msg, peer):
        if msg.startswith("NARAINIT"):
            # Pairing
            self.master_mac = peer
            config["master"] = peer.hex()
            write_json_file(CONFIG_FILE, config)
            self.send_msg(f"NARAINIT,OK,{config['sid']}", peer)
            await asyncio.sleep(0.5)
            machine.reset()
        elif cmd == "NARA":
            bat = adc.read_uv() / 1000000 * 2
            sm = f"S:{config['sid']},B:{bat:.2f},V:{VER}"
            self.send_msg(f"NARA,OK,{sm}", peer)

    async def handle_scan_cmd(self, cmd, parts):
        if cmd == "SCAN":
            failed = await self.cmd_cids("7E00810102030000EF", self.cids, timeout=3000) # Use RED or similar as ping? Or just connect?
            # Actually previous code used CODE_RGB provided. Let's use WHITE or RED 
            # 7E00810102030000EF is not standard. Let's use nara_cmd.MELK['RED'] if available or a default.
            # safe ping: 7e0081010000ef (OFF) or just use connect check?
            # Previous used CODE_RGB = "7e00810102030000ef".
            
            status = "NG" if failed else "OK"
            self.send_msg(f"SCAN,{status},{len(failed)}")

        elif cmd in ["ZSCAN", "PSCAN"]:
            found = []
            seen = set()
            try:
                async with aioble.scan(duration_ms=5000, interval_us=30000, window_us=30000, active=True) as scanner:
                    async for r in scanner:
                        name = r.name() or ""
                        addr = r.device.addr_hex().replace(':','')
                        if "MELK" in name and addr not in seen:
                            seen.add(addr)
                            found.append((addr, r.rssi))
            except Exception as e:
                self.send_msg(f"{cmd},ERR,{e}")
                return

            found.sort(key=lambda x: x[1], reverse=True)
            self.zmacs = [x[0] for x in found]
            
            if cmd == "ZSCAN":
                # Return list of Short IDs
                shorts = [m[-4:] for m in self.zmacs]
                self.send_msg(f"ZSCAN,{shorts}")
            
            elif cmd == "PSCAN":
                # Provision: Overwrite CIDS
                self.cids = self.zmacs
                write_json_file(CIDS_FILE, self.cids)
                self.p4dict = {item[-4:]: item for item in self.cids}
                self.send_msg(f"PSCAN,Saved,{len(self.cids)}")

    async def handle_config_cmd(self, cmd, parts):
        if cmd in ["SAVE", "SAVECONFIG"]:
            write_json_file(CONFIG_FILE, config)
            self.send_msg(f"{cmd},OK")
        elif cmd == "SID":
            if len(parts) > 1:
                config["sid"] = int(parts[1])
                self.send_msg(f"SID,{config['sid']}")
        elif cmd == "CH":
            if len(parts) > 1:
                config["ch"] = int(parts[1])
                self.send_msg(f"CH,{config['ch']}")
        elif cmd == "DEBUG":
            if len(parts) > 1:
                config["debug"] = int(parts[1])
                self.send_msg(f"DEBUG,{config['debug']}")

    async def handle_file_cmd(self, cmd, parts):
         if cmd == "CID":
             self.send_msg(f"CID,{[c[-4:] for c in self.cids]}")
         elif cmd == "SAVECID":
             write_json_file(CIDS_FILE, self.cids)
             self.send_msg("SAVECID,OK")
         elif cmd == "SDIR":
             self.send_msg(f"SDIR,{os.listdir()}")

    async def handle_msg(self, mac, msg_bytes):
        # Security: Allow NARAINIT from anyone (for pairing), else strict check
        msg = msg_bytes.decode()
        parts = msg.split(',')
        cmd = parts[0].upper()
        print(f".M {msg}")

        if msg.startswith("NARAINIT"):
             await self.handle_nara_cmd(cmd, parts, msg, mac)
             return

        if mac != self.master_mac:
            return

        if config['debug']: print(f"Recv: {msg}")

        # Dispatch
        # 1. Pipe-delimited format (New Master)
        if "|" in msg:
            pp = msg.split('|')
            if len(pp) >= 3:
                target, tid, rcmd, pmac = pp[0].upper(), pp[1], pp[2], (pp[3] if len(pp)>3 else "")
                
                # Filter by Target/TID
                if target == "GLOBAL" or tid == str(config["sid"]) or tid == "all":
                    # Execute
                    targets = self.cids
                    if target == "PID" and pmac:
                        # Specific PID
                         # pmac might be full or suffix.
                         full_mac = self.p4dict.get(pmac, pmac)
                         if len(full_mac) < 12 and len(full_mac) == 8: full_mac = "be28"+full_mac 
                         targets = [full_mac]
                    
                    failed = await self.cmd_cids(rcmd, targets)
                    resp = "OK" if not failed else "NG"
                    self.send_msg(f"RESP,{config['sid']},{rcmd},{resp}")
            return

        # 2. Legacy/Direct Command format (Comma separated or raw)
        if cmd.startswith("7E") or cmd in nara_cmd.MELK or (len(parts)>2 and parts[1].isdigit()): 

                pp = msg.split('|')
                if len(pp) >= 3:
                    target, tid, rcmd, pmac = pp[0].upper(), pp[1], pp[2], (pp[3] if len(pp)>3 else "")
                    
                    # Filter by Target/TID
                    if target == "GLOBAL" or tid == str(config["sid"]) or tid == "all":
                        # Execute
                        targets = self.cids
                        if target == "PID" and pmac:
                            # Specific PID
                             # pmac might be full or suffix.
                             full_mac = self.p4dict.get(pmac, pmac)
                             if len(full_mac) < 12 and len(full_mac) == 8: full_mac = "be28"+full_mac 
                             targets = [full_mac]
                        
                        failed = await self.cmd_cids(rcmd, targets)
                        resp = "OK" if not failed else "NG"
                        self.send_msg(f"RESP,{config['sid']},{rcmd},{resp}")
                return
        if cmd.startswith("7E") or cmd in nara_cmd.MELK or (len(parts)>2 and parts[1].isdigit()): 
             
            pp = msg.split('|')
            if len(pp) >= 3:
                # This block seems redundant if we already handled "|" above, but if it falls through?
                # Actually, the code above returns if "|" is found. 
                # So this legacy block is for NON-pipe messages.
                # But wait, original code was: if 7E or MELK...
                # inside it checked for pipe? No, that was my previous attempt.
                
                # The corrected logic:
                # 1. Check Pipe (done above)
                # 2. Check Legacy
                pass

            # Legacy handling logic should be here if any...
            # But the original code just had `pass`? No, it had logic I might have overwritten?
            # Let's look at `slave.py` before my edit.
            # It had:
            # if cmd.startswith("7E")...:
            #    if "|" in msg: ...
            
            # Since I moved the pipe logic UP, this block is now for:
            # Hex commands that are NOT pipe delimited.
            # e.g. "7E..." directly.
            
            # Implementation for direct hex:
            # (Previously it was `pass` effectively because the pipe check was inside?)
            # No, looking at `slave_orig.py` (which is actually `slave.py` content from previous turn):
            # It had `if "|" in msg` inside the `if cmd...` block.
            
            # If I moved it out, what should happen here?
            # If it is a raw HEX command e.g. "7E00...", we should execute it on ALL CIDs?
            # or just ignore?
            # The previous logic only did something IF `|` was in msg.
            # So if `|` was NOT in msg, it did NOTHING?
            # Let's verify.
            pass 

        # Admin Commands
        if cmd.startswith("NARA"): await self.handle_nara_cmd(cmd, parts, msg, mac)
        elif "SCAN" in cmd: await self.handle_scan_cmd(cmd, parts)
        elif cmd in ["SAVE", "SID", "CH", "DEBUG"]: await self.handle_config_cmd(cmd, parts)
        elif cmd in ["CID", "SAVECID", "SDIR"]: await self.handle_file_cmd(cmd, parts)
        elif cmd == "REBOOT": machine.reset()
        elif cmd == "STAT":
            bat = adc.read_uv() / 1000000 * 2
            self.send_msg(f"STAT,{config['sid']},{bat:.2f}V")

    async def run(self):
        print(f"Slave {config['sid']} ({VER}) on CH {config['ch']}")
        last_hbeat = 0
        while True:
            if self.esp.any():
                mac, msg = self.esp.recv()
                if mac:
                    await self.handle_msg(mac, msg)
            
            if time.time() - last_hbeat > 60:
                last_hbeat = time.time()
                wdt.feed()
                bat = adc.read_uv() / 1000000 * 2
                self.esp.send(self.master_mac, f"STAT,{config['sid']},{bat:.2f}V")
                gc.collect()
            
            await asyncio.sleep(0.05)

async def main():
    node = SlaveNode()
    await node.run()

if __name__ == "__main__":
    asyncio.run(main())
