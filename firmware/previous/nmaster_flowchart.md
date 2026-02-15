# nmaster.py Operational Flowchart (Refined)

This flowchart visualizes the logic of the Master firmware, corrected for syntax and subgraph structure.

```mermaid
graph TD
    Start([Power On / Reset]) --> Init[init_system]
    
    subgraph Initialization
        Init --> LoadConfig[Load nmaster.json & msids_*.json]
        LoadConfig --> HardwareInit[Setup WDT, LED, GPIO]
        HardwareInit --> WiFiSetup{WiFi Configured?}
        WiFiSetup -- Yes --> ConnectWiFi[Connect to WiFi]
        ConnectWiFi --> MQTTSetup[Setup & Subscribe MQTT]
        MQTTSetup --> ESPNowSetup[Initialize ESP-NOW & Add Peers]
        WiFiSetup -- No --> ESPNowSetup
        ESPNowSetup --> PollerSetup[Setup Serial Poller]
    end
    
    PollerSetup --> StartLoop
    
    subgraph LoopSection["Main Operational Loop"]
        StartLoop[Start Iteration] --> CheckMQTT{MQTT Message?}
        CheckMQTT -- Yes --> HandleMQTT[mqtt_callback -> handle_incoming_command]
        CheckMQTT -- No --> CheckSerial{Serial Data?}
        
        HandleMQTT --> CheckSerial
        
        CheckSerial -- Yes --> HandleSerial[Read Line -> handle_incoming_command]
        CheckSerial -- No --> Maintenance[System Maintenance]
        
        HandleSerial --> Maintenance
        
        Maintenance --> WDTFeed[Feed Watchdog]
        WDTFeed --> GC[Garbage Collection]
        GC --> MQTTCheck{MQTT Connected?}
        MQTTCheck -- No & 1min timeout --> Reboot([Machine Reset])
        MQTTCheck -- Yes --> StartLoop
    end
    
    subgraph CommandDispatch[handle_incoming_command]
        direction TB
        IncomingMsg[Incoming Message] --> Parse[Normalize & Split CSV]
        Parse --> FilterMID{Target matches mid?}
        FilterMID -- No --> Ignore([Ignore Message])
        FilterMID -- Yes --> Dispatch{Is Master Command?}
        
        Dispatch -- Yes --> MasterHandlers[MASTER_DISPATCH<br/>MDEBUG, MSID, MSTAT, etc.]
        Dispatch -- No --> SlaveFilter{SID in Range?}
        
        SlaveFilter -- No --> LogIgnore([Log & Ignore])
        SlaveFilter -- Yes --> SlaveRouter[handle_slave_command_route]
        
        SlaveRouter --> SlaveHandlers[SLAVE_DISPATCH<br/>NARA, FWSEND, etc.]
        SlaveRouter --> GenericForward[scmd_forward]
        
        MasterHandlers --> PrintResp[print_response & mqtt_publish]
        SlaveHandlers --> PrintResp
        GenericForward --> msend[msend via ESP-NOW]
    end
    
    subgraph Background[ESP-NOW IRQ]
        direction TB
        RecvIRQ[recv_cb] --> ProcessRecv[Identify SID from MAC]
        ProcessRecv --> InterceptACK{Firmware ACK?}
        InterceptACK -- Yes --> UpdateAck[Update ack_received]
        InterceptACK -- No --> PrintStatus[Print & Publish Status]
    end
```

## Key Components

- **`init_system`**: Sets up the environment, networking, and protocols.
- **`handle_incoming_command`**: The central routing point for all commands (Serial or MQTT).
- **`MASTER_DISPATCH`**: Handles local configuration and status commands.
- **`SLAVE_DISPATCH`**: Handles commands intended for slave nodes (e.g., scanning, firmware updates).
- **`recv_cb`**: Asynchronous handler for incoming ESP-NOW messages from slaves.
