# Node-RED Dashboard Design (Dashboard 2.0)

This document outlines the UI structure for the Raspbery Pi central dashboard.

## 1. Operator Dashboard (Main Tab)
A high-level interface for convention hall lighting control.

### A. Global Controls
- **Master Toggle**: All PIDs All Off / Global Default.
- **Hall Select**: Tabs or Toggle switch for **Hall 1 (MA)** and **Hall 2 (MB)**.

### B. Targeting Section
- **Target Mode Selector**: Dropdown [Global, Group, Slave, Booth, PID Subset].
- **Dynamic ID Selection**:
  - If Group: Dropdown for Groups 1-8.
  - If Slave: Dropdown of SIDs.
  - If Booth: Input/Dropdown for BIDs.
  - If PID Subset: Multi-select or Checkbox list of PIDs in that hall.

### C. Color/Code Control
- **Color Picker**: Visual wheel.
- **Predefined Presets**: Buttons for [Red, Blue, Green, White, Party Mode].
- **Raw CCode Input**: Text area for manual `ccode` (e.g., `7e00810102030000ef`).
- **Schedule**: Date/Time picker + "Submit Future Command" button.

### D. Real-time Status Grid
- A grid of tiles representing Slaves.
- **Tile Data**: `SID`, `Battery %`, `Last Result (Success/Fail icon)`, `Latency`.
- **RSSI View**: A button to toggle a heatmap visualization of PID signal strength reported by Slaves.

---

## 2. System Configuration Dashboard (Config Tab)
Admin-level setup for the infrastructure.

### A. Hardware Management
- **Master Config**: IP addresses and Health status for MA & MB.
- **Slave Setup**: Map `SID` to Hall (MA or MB).
- **Slave-PID Mapping**: Interface to view which PIDs are assigned to which Slave.

### B. Data Management
- **Firebase Export/Import**: Download current mapping to JSON/CSV.
- **Factory Reset**: Clear all field-provisioned records.

### C. Firmware Updates
- **MCMD Update**: Button to trigger `fwupdate` flow for specific Slaves.

---

## 3. Visual Aesthetic
- **Theme**: Dark Mode (Modern/Premium).
- **Glassmorphism**: Subtle translucency on tiles.
- **Typography**: Inter or Roboto for readability.
- **Micro-animations**: Loading spinners on tiles during `ccode` transmission.
