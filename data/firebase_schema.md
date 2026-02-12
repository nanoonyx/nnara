# Firebase Data Structure Definition

## Collections / Documents

### `pillars` (Collection)
Each document represents one LED Pillar (PID).
- **ID**: `pid` (e.g., `P001`)
- **Fields**:
  - `pmac`: String (MAC address)
  - `bid`: String (Booth ID)
  - `sid`: String (Slave ID)
  - `gid`: Number (Group ID, 1-8)
  - `hall`: String (`H1` or `H2`)
  - `status`: String (`success` / `fail`)
  - `battery`: Number (Voltage)
  - `rssi`: Number (dBm)
  - `last_update`: Timestamp

### `system_config` (Collection)
- **masters**:
  - `ma`: `{ "ip": "...", "status": "online" }`
  - `mb`: `{ "ip": "...", "status": "online" }`
- **groups**:
  - `g1`...`g8`: `{ "name": "...", "color": "..." }`

### `schedules` (Collection)
- **ID**: auto-generated.
- **Fields**:
  - `timestamp`: Timestamp (Execution time)
  - `target_type`: String (`all`, `group`, `slave`, `subset`)
  - `target_id`: String (Value of the ID)
  - `ccode`: String (Hex command)
  - `executed`: Boolean
