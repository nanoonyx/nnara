import os
import machine
import network
import espnow
import esp32
import binascii
import json
import time
import asyncio
import bluetooth
import aioble
import gc
import nara_cmd

# Constants
VER = "nslave_0210e"
CONFIG_FILE = "nslave.json"
CIDS_FILE = "cids.json"
SERVICE_UUID = bluetooth.UUID(0xFFF0)
CHAR_UUID = bluetooth.UUID(0xFFF3)
CODE_RGB = "7e00810102030000ef"

# Global Hardware Resources
wdt = machine.WDT(timeout=300000)
adc = machine.ADC(machine.Pin(2))
led = machine.Pin(5, machine.Pin.OUT)


def read_json_file(filename, default=None):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_json_file(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


class NLED:
    def __init__(self, mac):
        self.mac = mac
        self.device = aioble.Device(aioble.ADDR_PUBLIC, mac)
        self.connection = None
        self.char = None

    async def connect(self, timeout_ms=2900):
        try:
            self.connection = await self.device.connect(timeout_ms=timeout_ms)
            service = await self.connection.service(SERVICE_UUID)
            self.char = await service.characteristic(CHAR_UUID)
            return True
        except Exception:
            self.connection = None
            self.char = None
            return False

    async def disconnect(self):
        if self.connection:
            try:
                await self.connection.disconnect()
            except Exception:
                pass
            finally:
                self.connection = None
                self.char = None

    async def write(self, code, repeat=1):
        if not self.connection or not self.char:
            return False
        payload = binascii.unhexlify(code)
        try:
            for _ in range(repeat):
                await self.char.write(payload)
            return True
        except Exception:
            return False


class SlaveNode:
    def __init__(self):
        self.mymac = machine.unique_id().hex()
        self.boot_tick = time.ticks_ms()
        self.sos = ""

        # Load Config
        self.config = read_json_file(CONFIG_FILE, {})
        self.ch = int(self.config.get("ch", 11))
        self.sid = int(self.config.get("sid", 99))
        self.master_hex = self.config.get("master", "24ec4aca5e20")
        self.debug_mode = self.config.get("debug", False)

        try:
            self.mmac = binascii.unhexlify(self.master_hex)
        except Exception:
            self.mmac = b"\x24\xec\x4a\xca\x5e\x20"

        # State
        self.cids = []
        self.lmacs = []
        self.zmacs = []
        self.p4dict = {}

        try:
            self.cids = read_json_file(CIDS_FILE, {})
            self.p4dict = {item[-4:]: item for item in self.cids}
            self.lmacs = list(self.cids)
        except Exception as err:
            self.sos = f"{CIDS_FILE}, {err}"

        # FW Update State
        self.fw_last_seq = -1
        self.fw_target_file = "main.py"

        # Network Setup
        self.sta = network.WLAN(network.STA_IF)


        self.ap = network.WLAN(network.AP_IF)
        self.esp = None
        self.init_network()

    def init_network(self):
        self.sta.active(True)
        self.sta.config(pm=0)
        self.ap.active(True)
        self.ap.disconnect()
        try:
            self.sta.config(channel=self.ch)
        except Exception:
            pass

        self.esp = espnow.ESPNow()
        self.esp.config(rxbuf=1024)
        self.esp.active(True)

    def log(self, arg=None):
        if self.debug_mode:
            print(f".,{arg if arg is not None else time.ticks_ms()}")

    def send_msg(self, msg, peer=None):
        target = peer if peer else self.mmac
        try:
            self.esp.add_peer(target)
        except Exception:
            pass
        try:
            data = msg.encode() if isinstance(msg, str) else msg
            # Append bat voltage if short message? or generic status?
            # Keeping close to original logic but refactored
            if len(data) > 250:
                 self.esp.send(target, data[:250])
            else:
                 # original appended voltage, keeping it for compatibility
                 self.esp.send(target, data + f",{adc.read_uv()/500000:.2f}".encode())
            
            self.log(f"> {msg}")
        except Exception as e:
            if self.debug_mode:
                 print(f"Send Error: {e}")

    async def cmd_cids(self, code, target_cids, timeout=3500, repeat=1):
        start_tick = time.ticks_ms()
        failed_macs = []
        wdt.feed()
        for p in target_cids:
            nled = NLED(binascii.unhexlify("be28" + p))
            success = False
            last_tick = time.ticks_ms()
            try:
                if await nled.connect(timeout):
                    success = await nled.write(code, repeat=repeat)
                    await nled.disconnect()
                else:
                    if nled.connection:
                        await nled.disconnect() # Ensure cleanup
            except Exception as err:
                self.send_msg(f"cmd_cids Exception {p[-4:]}: {err}")

            if not success:
                failed_macs.append(p)

            self.log(
                f"nled,{p[-4:]},{success},{time.ticks_diff(time.ticks_ms(), last_tick)}"
            )

        self.log(
            f"N={len(target_cids)},F={len(failed_macs)},T={time.ticks_diff(time.ticks_ms(), start_tick)}"
        )
        return failed_macs

    # --- Command Handlers ---

    async def handle_nara_cmd(self, cmd, parts, msg, peer):
        status_summary = f"S:{self.sid},B:{adc.read_uv()/500000:.2f},T:{esp32.mcu_temperature()},V:{VER}"
        if msg.startswith("NARAINIT"):
            self.mmac = peer
            self.master_hex = self.mmac.hex()
            self.config["master"] = self.master_hex
            write_json_file(CONFIG_FILE, self.config)
            self.send_msg(f"{cmd},{self.config}", peer)
            machine.reset()
        else:
            self.send_msg(f"{cmd},{{{status_summary}}}", peer)

    async def handle_hex_cmd(self, cmd, parts, msg, last_tick):
        if len(cmd) != 14:
             self.send_msg(f"NG,{parts} MELK length={len(cmd)} should be 14.")
             return

        code = msg[0:14] + "00EF"
        
        # Determine targets
        target_list = []
        p4_list = []
        
        if len(parts) > 1 and parts[1]: # valid target list provided
            p4_list = list(parts[1].split(","))
            target_list = [self.p4dict[p] for p in p4_list if p in self.p4dict]
            
            if not target_list:
                 self.send_msg(f"NG,No valid targets found in {parts[1]}")
                 return

            failed = await self.cmd_cids(code, target_list, timeout=5000)
            if failed:
                # Retry once for specific targets
                failed = await self.cmd_cids(code, failed, timeout=5000)
                self.send_msg(f"NG,{[f[-4:] for f in failed]},{time.ticks_diff(time.ticks_ms(), last_tick)}")
            else:
                self.send_msg(f"OK,{p4_list},{time.ticks_diff(time.ticks_ms(), last_tick)}")
        
        else: # Broadcast to all cids
            failed = await self.cmd_cids(code, self.cids, timeout=3000)
            retry_count = 0
            while failed and retry_count < 2:
                retry_count += 1
                # self.send_msg(f"NG,{[d[-4:] for d in failed]},Retry:{retry_count}")
                failed = await self.cmd_cids(code, failed, timeout=3500)
            
            if failed:
                self.send_msg(f"NG,{[d[-4:] for d in failed]}")
            else:
                self.send_msg(f"{cmd},OK,D:{time.ticks_diff(time.ticks_ms(), last_tick)}")

    async def handle_scan_cmd(self, cmd, parts, last_tick):
        if cmd == "SCAN":
            target_list = list(self.cids)
            failed = await self.cmd_cids(CODE_RGB, target_list, timeout=3000)
            status = "NG" if failed else "OK"
            failed_str = str([l[-4:] for l in failed]) if failed else ""
            self.send_msg(f"{cmd},{status},{failed_str},D:{time.ticks_diff(time.ticks_ms(), last_tick)}")

        elif cmd == "ZSCAN" or cmd == "PSCAN":
            devices = []
            seen_addrs = set()
            try:
                async with aioble.scan(duration_ms=5000, interval_us=30000, window_us=30000, active=True) as scanner:
                    async for r in scanner:
                        name = r.name() or ""
                        addr = r.device
                        if "MELK-OC21" in name or "MELK" in name:
                             if addr not in seen_addrs:
                                seen_addrs.add(addr)
                                devices.append(r)
            except Exception as err:
                 self.log(f"NG,{cmd},{err}")

            found_macs = [d.device.addr_hex().replace(":", "")[-8:] for d in devices]
            
            if cmd == "ZSCAN":
                found_rssi = [d.rssi for d in devices] # just list rssi separately or combined?
                # Original logic sorted by RSSI
                combined = sorted(zip(found_macs, found_rssi), key=lambda x: x[1], reverse=True)
                sorted_macs = [x[0] for x in combined]
                sorted_rssi = [x[1] for x in combined]
                
                self.zmacs = sorted_macs
                self.send_msg(f"{cmd},{[m[-4:] for m in sorted_macs]},{sorted_rssi}")
            
            elif cmd == "PSCAN":
                self.zmacs = found_macs
                write_json_file(CIDS_FILE, found_macs)
                await asyncio.sleep(0.1)
                self.cids = read_json_file(CIDS_FILE, {})
                self.lmacs = list(self.cids)
                self.p4dict = {item[-4:]: item for item in self.cids} # Update dict
                self.send_msg(f"{cmd},{[p[-4:] for p in self.cids]},D:{time.ticks_diff(time.ticks_ms(), last_tick)}")

    async def handle_config_cmd(self, cmd, parts):
        if cmd in ["SAVE", "SAVECONFIG"]:
            write_json_file(CONFIG_FILE, self.config)
            if self.debug_mode:
                self.send_msg(f"{cmd},OK,{self.config}")
        
        elif cmd in ["CON", "CONFIG"]:
            try:
                new_json = json.loads(parts[1])
                write_json_file(CONFIG_FILE, new_json)
                self.send_msg(f"{cmd}, {new_json}, Resetting...")
                await asyncio.sleep(0.1)
                machine.reset()
            except Exception:
                 self.send_msg(f"{cmd},{self.config}")

        elif cmd in ["SID", "SETSID"]:
            try:
                self.sid = int(parts[1])
                self.config["sid"] = self.sid
                self.send_msg(f"{cmd},{self.sid}")
            except Exception:
                self.send_msg(f"{cmd},{self.sid}")

        elif cmd in ["CH", "CHANNEL"]:
            try:
                self.ch = int(parts[1])
                self.config["ch"] = self.ch
                self.send_msg(f"{cmd},{self.ch}")
            except Exception:
                self.send_msg(f"{cmd},{self.ch}")
                
        elif cmd in ["MASTER", "SETMASTER"]:
            try:
                self.master_hex = parts[1]
                self.config["master"] = self.master_hex
                self.send_msg(f"{cmd},{self.master_hex}")
            except Exception:
                self.send_msg(f"{cmd},{self.master_hex}")
                
        elif cmd in ["DEBUG", "SETDEBUG"]:
            if len(parts) > 1:
                try:
                    self.debug_mode = int(parts[1])
                    self.config["debug"] = self.debug_mode
                except ValueError:
                    pass
            self.send_msg(f"{cmd},{self.debug_mode}")

    async def handle_mac_file_cmd(self, cmd, parts):
        # CIDS, ZMACS, LMACS management
        if cmd in ["CID", "CIDS"]:
             self.send_msg(f"{cmd},{[p[-4:] for p in self.cids]}")
        
        elif cmd in ["ZMAC", "ZMACS"]:
             self.send_msg(f"{cmd},{[p[-4:] for p in self.zmacs]}")
             
        elif cmd in ["LMAC", "LMACS"]:
             self.send_msg(f"{cmd},{[p[-4:] for p in self.lmacs]}")
        
        elif cmd in ["SAVECIDS", "SAVECID", "CSAVE", "SAVELMAC", "LSAVE", "SAVEZMAC", "ZSAVE"]:
             # Determine source
             data = self.cids
             if "LMAC" in cmd or "LSAVE" in cmd: data = self.lmacs
             elif "ZMAC" in cmd or "ZSAVE" in cmd: data = self.zmacs
             
             write_json_file(CIDS_FILE, data)
             if self.debug_mode:
                  self.send_msg(f"{cmd},{[p[-4:] for p in data]}")

    async def handle_fw_update(self, cmd, parts):
        # parts = ["FWUPDATE", SUB_CMD, ARGS...]
        if len(parts) < 2: return
        sub = parts[1]
        
        # Default to whatever we set in START, or main.py if not set
        target_temp = "next_" + self.fw_target_file
        
        try:
            if sub == "START":
                # FWUPDATE,START,SIZE,CHECKSUM,FILENAME
                try:
                    # Parse Filename if present
                    if len(parts) > 4:
                        self.fw_target_file = parts[4]
                        target_temp = "next_" + self.fw_target_file
                    
                    with open(target_temp, "wb") as f:
                        f.write(b"") # Clear file binary
                    self.fw_last_seq = -1
                    self.send_msg(f"{cmd},START,OK")
                except Exception as e:
                     self.send_msg(f"{cmd},START,NG,{e}")

            elif sub == "DATA":
                # FWUPDATE,DATA,SEQ,HEX_CONTENT
                if len(parts) < 4: return
                try:
                    seq = int(parts[2])
                    hex_content = parts[3]
                    
                    if seq <= self.fw_last_seq:
                        # Duplicate packet received (ack lost?). 
                        # Do not write to file, just re-send ACK.
                        self.send_msg(f"{cmd},ACK,{seq}")
                        return

                    if seq != self.fw_last_seq + 1:
                        self.send_msg(f"{cmd},ERR,OutOfOrder,{seq},{self.fw_last_seq}")
                        return

                    content = binascii.unhexlify(hex_content)
                    with open(target_temp, "ab") as f:
                        f.write(content)
                    
                    self.fw_last_seq = seq
                    # Send ACK only every 5 packets to reduce network overhead
                    if seq % 5 == 0:
                        self.send_msg(f"{cmd},ACK,{seq}")
                except Exception as e:
                     pass

            elif sub == "END":
                # FWUPDATE,END
                try:
                    # Rename
                    import os
                    final_file = self.fw_target_file
                    try:
                        os.remove(final_file + ".bak")
                    except: pass
                    try:
                        os.rename(final_file, final_file + ".bak")
                    except: pass
                    try:
                        os.remove(final_file)
                    except: pass 
                    os.rename(target_temp, final_file)
                    
                    self.send_msg(f"{cmd},END,OK,Rebooting")
                    await asyncio.sleep(1)
                    machine.reset()
                except Exception as e:
                    self.send_msg(f"{cmd},END,NG,{e}")
                    
        except Exception as e:
            self.send_msg(f"{cmd},ERR,{e}")


    async def handle_system_cmd(self, cmd, parts, last_tick):
        if cmd in ["VERSION", "VER", "V"]:
            self.send_msg(f"{cmd},{VER}")
            
        elif cmd == "BLINK":
            r = 3
            if len(parts) > 1:
                try: r = int(parts[1])
                except ValueError: pass
            
            for _ in range(r):
                led.value(0)
                await asyncio.sleep_ms(500)
                led.value(1)
                await asyncio.sleep_ms(500)
            if self.debug_mode:
                 self.send_msg(f"{cmd},S:{self.sid},D:{time.ticks_diff(time.ticks_ms(), last_tick)}")
                 
        elif cmd in ["STAT", "STATUS"]:
             sm = f"S:{self.sid},B:{adc.read_uv()/500000:.2f},T:{esp32.mcu_temperature()},V:{VER}"
             self.send_msg(f"{cmd},{sm}")
             
        elif cmd == "SLEEP":
             sec = 10
             if len(parts) > 1:
                 try: sec = int(parts[1])
                 except ValueError: pass
             self.send_msg(f"{cmd},{sec},Bye")
             # Cleanup
             led.value(0)
             machine.lightsleep(sec * 1000)
             machine.reset()
             
        elif cmd == "SDIR":
             try:
                 files = os.listdir()
                 self.send_msg(f"{cmd},{files}")
             except Exception as e:
                 self.send_msg(f"{cmd},NG,{e}")

        elif cmd in ["BOOT", "REBOOT", "RESET"]:
            await asyncio.sleep(0.1)
            machine.reset()
            
    async def process_msg(self, peer, msg, last_tick):
        self.log(f"< {peer.hex()},{msg}")
        parts = msg.split(",")
        cmd = parts[0].upper()

        if msg.startswith("NARA"):
            await self.handle_nara_cmd(cmd, parts, msg, peer)
            return

        # Security check: only accept commands from Master
        if peer != self.mmac:
            return

        if cmd.startswith("7E"):
            await self.handle_hex_cmd(cmd, parts, msg, last_tick)
            return
        
        # Dispatcher for textual commands
        if cmd == "FWUPDATE":
             await self.handle_fw_update(cmd, parts)
        elif cmd in ["SCAN", "ZSCAN", "PSCAN"]:
            await self.handle_scan_cmd(cmd, parts, last_tick)
        elif cmd in ["SAVE", "SAVECONFIG", "CON", "CONFIG", "SID", "SETSID", "CH", "CHANNEL", "MASTER", "SETMASTER", "DEBUG", "SETDEBUG"]:
             await self.handle_config_cmd(cmd, parts)
        elif any(x in cmd for x in ["CID", "ZMAC", "LMAC", "CSAVE", "LSAVE", "ZSAVE"]):
             await self.handle_mac_file_cmd(cmd, parts)
        elif cmd in ["VERSION", "VER", "V", "BLINK", "STAT", "STATUS", "SLEEP", "BOOT", "REBOOT", "RESET", "SDIR"]:
             await self.handle_system_cmd(cmd, parts, last_tick)
        else:
             if self.debug_mode:
                 self.send_msg(f"NG,{msg},Unknown Cmd")

    async def run(self):
        # Startup actions
        if self.sos:
            self.send_msg(f"{self.sos}")

        # Check low battery
        if adc.read_uv() / 500000 < 3.7:
             self.send_msg(f"SOS,LowBat,{adc.read_uv()/500000:.2f}")

        led.value(1)  # ON
        sm = f"S:{self.sid},M:{self.mymac},B:{adc.read_uv()/500000:.2f},T:{esp32.mcu_temperature()},V:{VER},C:{self.sta.config('channel')}"
        
        print(f"ON,{sm}")
        self.send_msg(f"ON,{sm}")
        self.log(f"config,{self.config}")
        
        last_tick = time.ticks_ms()

        while True:
            if self.esp and self.esp.any():
                try:
                    peer, msg_bytes = self.esp.recv()
                    wdt.feed()
                    last_tick = time.ticks_ms()
                    try:
                        msg = msg_bytes.decode()
                        await self.process_msg(peer, msg, last_tick)
                    except Exception:
                        pass
                except Exception as e:
                    # self.log(f"ESP Recv Error: {e}")
                    pass
                last_tick = time.ticks_ms()

            await asyncio.sleep(0.1)

            if time.ticks_diff(time.ticks_ms(), last_tick) > 30000:
                wdt.feed()
                last_tick = time.ticks_ms()
                gc.collect()


async def main():
    node = SlaveNode()
    await node.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Main Loop Crash: {e}")
    finally:
        led.value(0)
