# nslave.py Operational Flowchart

This flowchart visualizes the logic of the Slave firmware used in the LED control system.

```mermaid
graph TD
    Start([Power On / Reset]) --> SlaveInit[SlaveNode Initialization]
    
    subgraph Initialization
        SlaveInit --> LoadConfig[Load nslave.json & cids.json]
        LoadConfig --> NetworkInit[init_network: WiFi STA/AP & ESP-NOW]
        NetworkInit --> HardwareInit[Setup WDT, ADC, LED]
    end
    
    HardwareInit --> RunNode[SlaveNode.run]
    
    subgraph MainAsyncLoop["Main Async Loop"]
        RunNode --> StartupNotify[Send ON Status to Master]
        StartupNotify --> BattCheck{Battery Low?}
        BattCheck -- Yes --> SOS[Send SOS to Master]
        BattCheck -- No --> WaitMsg[Wait for ESP-NOW Message]
        
        SOS --> WaitMsg
        
        WaitMsg -- Message Received --> FeedWDT1[Feed WDT]
        FeedWDT1 --> ProcessMsg[process_msg]
        
        WaitMsg -- Timeout/Sleep --> Maintenance{30s Elapsed?}
        ProcessMsg --> Maintenance
        
        Maintenance -- Yes --> FeedWDT2[Feed WDT & gc.collect]
        Maintenance -- No --> LoopSleep[asyncio.sleep 0.1s]
        
        FeedWDT2 --> StartIteration[Next Iteration]
        LoopSleep --> StartIteration
        StartIteration --> WaitMsg
    end
    
    subgraph CommandProcessing[process_msg]
        direction TB
        IncomingMsg[Incoming MSG] --> NaraCheck{Is NARA/NARAINIT?}
        
        NaraCheck -- Yes --> NaraHandler[handle_nara_cmd<br/>Reply Status or Init Master]
        NaraCheck -- No --> SecurityCheck{Peer matches mmac?}
        
        SecurityCheck -- No --> IgnoreMsg([Ignore Message])
        SecurityCheck -- Yes --> CmdDispatch{Command Type?}
        
        CmdDispatch -- "7E..." --> HexCmd[handle_hex_cmd<br/>BLE Color Control]
        CmdDispatch -- "FWUPDATE" --> FWCmd[handle_fw_update<br/>OTA Update Logic]
        CmdDispatch -- "SCAN/ZSCAN" --> ScanCmd[handle_scan_cmd<br/>BLE Device Discovery]
        CmdDispatch -- "CONFIG/SID" --> ConfigCmd[handle_config_cmd<br/>Settings Update]
        CmdDispatch -- "STAT/BOOT" --> SysCmd[handle_system_cmd<br/>System Maintenance]
        
        HexCmd --> BLEAction[Connect -> Write -> Disconnect]
        ScanCmd --> BLEScan[aioble.scan]
        
        NaraHandler --> ReplyExp[send_msg to Master]
        HexCmd --> ReplyExp
        FWCmd --> ReplyExp
        ScanCmd --> ReplyExp
        ConfigCmd --> ReplyExp
        SysCmd --> ReplyExp
    end
```

## Key Components

- **`SlaveNode`**: The central controller class managing state and communications.
- **`NLED`**: A helper class for managing BLE connections and writes to LED controllers.
- **`process_msg`**: Dispatches commands received via ESP-NOW to specialized handlers.
- **`handle_hex_cmd`**: The core function for forwarding color commands from the Master to controllers.
- **`handle_fw_update`**: Manages the piecewise reception and application of firmware updates.
