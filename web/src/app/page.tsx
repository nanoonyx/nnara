"use client";

import { useState, useMemo, useEffect } from "react";
import styles from "./page.module.css";
import PillarTile from "@/components/PillarTile";
import SlaveTile from "@/components/SlaveTile";
import ControlPanel from "@/components/ControlPanel";
import GlassPanel from "@/components/GlassPanel";
import { mqttService } from "@/services/mqttService";

import initialData from "@/data/initialData.json";

export default function Home() {
  const [activeTab, setActiveTab] = useState("Operator");
  const [masterIPs, setMasterIPs] = useState({ H1: "192.168.45.241", H2: "192.168.45.241" });
  const [mqttConfig, setMqttConfig] = useState({ host: "192.168.45.241", port: 9001 });
  const [ipInputs, setIpInputs] = useState({ ...masterIPs });
  const [mqttInputs, setMqttInputs] = useState({ ...mqttConfig });

  const [pillars, setPillars] = useState(initialData.pillars.map(p => ({ ...p, rssiHistory: [(p as any).rssi || -45] })));
  const [slaves, setSlaves] = useState(initialData.slaves);
  const [isMqttConnected, setIsMqttConnected] = useState(false);
  const [history, setHistory] = useState<{ id: string, msg: string, time: string, type: 'status' | 'cmd' }[]>([]);

  // Filtering & Search State
  const [filterHall, setFilterHall] = useState("All");
  const [filterSignal, setFilterSignal] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedPid, setSelectedPid] = useState<string | null>(null);

  const addHistory = (msg: string, type: 'status' | 'cmd') => {
    const entry = {
      id: Math.random().toString(16).slice(2, 8),
      msg,
      time: new Date().toLocaleTimeString(),
      type
    };
    setHistory(prev => [entry, ...prev].slice(0, 20));
  };

  useEffect(() => {
    // Initialize MQTT Connection
    mqttService.connect({
      host: mqttConfig.host,
      port: mqttConfig.port,
      protocol: "ws",
      clientId: `nara_web_${Math.random().toString(16).slice(2, 8)}`
    }, () => {
      setIsMqttConnected(true);
      mqttService.subscribe("nara/status/pid/#");
      mqttService.subscribe("nara/status/slaves/#");
      addHistory("Connected to MQTT Broker", "status");
    });

    mqttService.onMessage((topic, message) => {
      try {
        const data = JSON.parse(message);
        if (topic.startsWith("nara/status/pid/")) {
          const pid = topic.split("/").pop();
          setPillars(prev => prev.map(p => {
            if (p.pid === pid) {
              const newRssi = data.rssi || -45;
              return {
                ...p,
                ...data,
                status: "success",
                lastTime: "Just now",
                rssi: newRssi,
                rssiHistory: [newRssi, ...(p.rssiHistory || [])].slice(0, 10)
              };
            }
            return p;
          }));
          addHistory(`${pid} Status Updated`, 'status');
        }
        if (topic.startsWith("nara/status/slaves/")) {
          const sid = topic.split("/").pop();
          setSlaves(prev => prev.map(s =>
            s.sid === sid ? { ...s, ...data, status: "success", lastComm: "Just now" } : s
          ));
          addHistory(`Slave ${sid} Sync`, 'status');
        }
      } catch (e) {
        console.error("Failed to parse status message", e);
      }
    });

    return () => mqttService.disconnect();
  }, [mqttConfig]);

  // Compute filtered pillars
  const filteredPidList = useMemo(() => {
    return pillars.map(p => {
      const sidNum = parseInt(p.sid.slice(1));
      const pMatchHall = filterHall === "All" || (filterHall === "H1" ? sidNum <= 12 : sidNum > 12);

      const pMatchSearch = searchQuery === "" ||
        p.pid.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.bid.toLowerCase().includes(searchQuery.toLowerCase());

      const rssi = (p as any).rssi || -45;
      const pMatchSignal = filterSignal === "All" ||
        (filterSignal === "Low" && rssi < -70) ||
        (filterSignal === "Good" && rssi >= -70);

      return { ...p, isHidden: !pMatchHall || !pMatchSearch || !pMatchSignal };
    });
  }, [pillars, filterHall, searchQuery, filterSignal]);

  const selectedPillar = useMemo(() =>
    pillars.find(p => p.pid === selectedPid),
    [pillars, selectedPid]);

  // Compute Hierarchy: Group -> Slave -> Pillars
  const nestedGroups = useMemo(() => {
    const groups: Record<string, any> = {};

    // 1. Initialize Groups (GA-GE)
    ["GA", "GB", "GC", "GD", "GE"].forEach(gid => {
      groups[gid] = { gid, slaves: {} };
    });

    // 2. Nest Pillars under Slaves
    pillars.forEach(p => {
      const gid = p.gid || "Unknown";
      if (!groups[gid]) groups[gid] = { gid, slaves: {} };

      if (!groups[gid].slaves[p.sid]) {
        const slaveInfo = slaves.find(s => s.sid === p.sid) || { sid: p.sid, status: 'offline' };
        groups[gid].slaves[p.sid] = { ...slaveInfo, pillars: [] };
      }

      // Check filtering inside nesting
      const sidNum = parseInt(p.sid.slice(1));
      const pMatchHall = filterHall === "All" || (filterHall === "H1" ? sidNum <= 12 : sidNum > 12);
      const pMatchSearch = searchQuery === "" ||
        p.pid.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.bid.toLowerCase().includes(searchQuery.toLowerCase());

      const isHidden = !pMatchHall || !pMatchSearch;
      groups[gid].slaves[p.sid].pillars.push({ ...p, isHidden });
    });

    // 3. Convert to Sorted Arrays
    return Object.values(groups).map((g: any) => ({
      ...g,
      slaves: Object.values(g.slaves).sort((a: any, b: any) => {
        const numA = parseInt(a.sid.slice(1));
        const numB = parseInt(b.sid.slice(1));
        return numA - numB;
      })
    })).sort((a, b) => a.gid.localeCompare(b.gid));
  }, [pillars, slaves, filterHall, searchQuery]);

  const handleCommandPublished = (msg: string) => {
    addHistory(msg, 'cmd');
  };

  const getSignalClass = (rssi: number) => {
    if (rssi >= -60) return styles.sigGood;
    if (rssi >= -75) return styles.sigFair;
    return styles.sigPoor;
  };

  return (
    <main className={styles.container}>
      <header className={styles.header}>
        <div className={styles.titleArea}>
          <h1>NARA CMD ENGINE</h1>
          <nav className={styles.tabs}>
            {["Operator", "Analytics", "Setup"].map((tab) => (
              <button
                key={tab}
                className={`${styles.tabBtn} ${activeTab === tab ? styles.tabActive : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className={styles.layout}>
        {activeTab === "Operator" || activeTab === "Analytics" ? (
          <>
            <section className={styles.sidebar}>
              <ControlPanel
                masterIPs={masterIPs}
                history={history}
                pillars={pillars}
                selectedPid={selectedPid}
                onCmd={handleCommandPublished}
                onClear={() => setHistory([])}
              />
              <GlassPanel title="System Stats" className={styles.stats}>
                {/* ... existing stats ... */}
                <div className={styles.statRow}>
                  <span>Total Pillars</span>
                  <span className={styles.statVal}>{pillars.length}</span>
                </div>
                <div className={styles.statRow}>
                  <span>Online Slaves</span>
                  <span className={styles.statVal}>{slaves.filter(s => s.status === "success").length}/24</span>
                </div>
                <div className={styles.divider} />
                <div className={styles.statRow}>
                  <span>Avg RSSI</span>
                  <span className={styles.statVal}>
                    {Math.round(pillars.reduce((acc, p) => acc + ((p as any).rssi || -45), 0) / pillars.length)} dBm
                  </span>
                </div>
                <div className={styles.statRow}>
                  <span>MQTT Broker</span>
                  <span className={isMqttConnected ? styles.ok : styles.offline}>
                    {isMqttConnected ? "Connected" : "Disconnected"}
                  </span>
                </div>
              </GlassPanel>
            </section>

            <section className={styles.mainContent}>
              <div className={styles.scrollable}>
                {activeTab === "Operator" ? (
                  <div className={styles.hierarchyContainer}>
                    {nestedGroups.map((group) => (
                      <div key={group.gid} className={styles.groupBlock}>
                        <div className={styles.groupHeader}>
                          <h3>{group.gid} GROUP</h3>
                          <span className={styles.subtext}>{group.slaves.length} Slaves Online</span>
                        </div>

                        <div className={styles.nestedSlaveGrid}>
                          {group.slaves.map((slave: any) => (
                            <div key={slave.sid} className={slave.status === 'fail' ? `${styles.slaveNode} ${styles.dangerZone}` : styles.slaveNode}>
                              <div className={styles.slaveHeader}>
                                <div className={styles.slaveId}>{slave.sid} NODE</div>
                                <span className={`${styles.signalTag} ${slave.status === "success" ? styles.ok : styles.offline}`}>
                                  {slave.status === "success" ? "ONLINE" : "OFFLINE"}
                                </span>
                              </div>
                              <div className={styles.statRow} style={{ marginBottom: '1rem', fontSize: '0.7rem' }}>
                                <span>{slave.smac}</span>
                                <span>{slave.battery}% Bat</span>
                              </div>

                              <div className={styles.pillarMiniGrid}>
                                {slave.pillars.map((p: any) => (
                                  <div
                                    key={p.pid}
                                    className={`${styles.miniPillar} ${p.isHidden ? styles.hiddenPillar : ""} ${selectedPid === p.pid ? styles.selectedPillar : ""}`}
                                    title={`${p.pid} | Booth: ${p.bid} | MAC: ${p.pmac}`}
                                    onClick={() => setSelectedPid(p.pid === selectedPid ? null : p.pid)}
                                  >
                                    <div className={`${styles.statusDotSmall} ${p.status === "success" ? styles.online : styles.offline}`} />
                                    <div className={styles.miniColor} style={{ backgroundColor: p.color }} />
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <>
                    <div className={styles.sectionHeader}>
                      <h2>Signal Strength Analytics</h2>
                      <div className={styles.viewActions}>
                        <span className={styles.subtext} style={{ marginRight: "1rem" }}>Filter by Health:</span>
                        {["All", "Good", "Low"].map(sig => (
                          <button
                            key={sig}
                            className={`${styles.miniBtn} ${filterSignal === sig ? styles.filterActive : ""}`}
                            onClick={() => setFilterSignal(sig)}
                          >
                            {sig}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className={styles.analyticsGrid}>
                      {filteredPidList.filter(p => !p.isHidden).slice(0, 12).map(p => (
                        <GlassPanel key={p.pid} title={p.pid} className={styles.stats}>
                          <div className={styles.statRow}>
                            <span>Booth</span>
                            <span className={styles.statVal}>{p.bid}</span>
                          </div>
                          <div className={styles.statRow}>
                            <span>Current RSSI</span>
                            <span className={`${styles.signalTag} ${getSignalClass((p as any).rssi || -45)}`}>
                              {(p as any).rssi || -45} dBm
                            </span>
                          </div>
                          <div className={styles.historyChart}>
                            {((p as any).rssiHistory || []).map((val: number, i: number) => (
                              <div
                                key={i}
                                className={styles.chartBar}
                                style={{ height: `${Math.min(100, Math.max(10, (val + 100)))}%` }}
                              />
                            ))}
                          </div>
                        </GlassPanel>
                      ))}
                    </div>
                    <div className={styles.divider} />
                    <div className={styles.sectionHeader}>
                      <h2>System-Wide Signal Heat Map</h2>
                    </div>
                    <div className={styles.compactGrid}>
                      {pillars.map((p) => (
                        <div
                          key={p.pid}
                          className={`${styles.miniPillar} ${selectedPid === p.pid ? styles.selectedPillar : ""}`}
                          style={{ background: 'rgba(0,0,0,0.4)', padding: '2px' }}
                          onClick={() => setSelectedPid(p.pid)}
                        >
                          <div
                            className={`${styles.miniColor} ${getSignalClass((p as any).rssi || -45)}`}
                            style={{ borderRadius: '2px' }}
                          />
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </section>

            {/* Pillar Detail Panel Overlay */}
            {selectedPillar && (
              <div className={styles.detailOverlay}>
                <div className={styles.detailHeader}>
                  <h3>Pillar Details</h3>
                  <button className={styles.closeBtn} onClick={() => setSelectedPid(null)}>&times;</button>
                </div>
                <div className={styles.detailBody}>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Pillar ID</span>
                    <span className={styles.detailValue}>{selectedPillar.pid}</span>
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Booth ID</span>
                    <span className={styles.detailValue}>{selectedPillar.bid}</span>
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Slave Assignment</span>
                    <span className={styles.detailValue}>{selectedPillar.sid}</span>
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Group Color</span>
                    <div className={styles.miniColor} style={{ backgroundColor: selectedPillar.color, width: "40px", height: "10px", borderRadius: "4px" }} />
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Signal Strength (RSSI)</span>
                    <span className={`${styles.signalTag} ${getSignalClass((selectedPillar as any).rssi || -45)}`}>
                      {(selectedPillar as any).rssi || -45} dBm
                    </span>
                  </div>
                  <div className={styles.historyChart} style={{ height: '60px' }}>
                    {((selectedPillar as any).rssiHistory || []).map((val: number, i: number) => (
                      <div
                        key={i}
                        className={styles.chartBar}
                        style={{ height: `${Math.min(100, Math.max(10, (val + 100)))}%` }}
                      />
                    ))}
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Last Comm</span>
                    <span className={styles.detailValue}>{selectedPillar.lastTime}</span>
                  </div>
                  <GlassPanel title="Direct Action">
                    <p style={{ fontSize: "0.8rem", color: "#a5a6bc", marginBottom: "1rem" }}>
                      Send immediate command to PID {selectedPillar.pid}
                    </p>
                    <button
                      className={styles.primaryBtn}
                      style={{ width: "100%" }}
                      onClick={() => {
                        mqttService.publish("nara/cmd", JSON.stringify({
                          target: "PID",
                          id: selectedPillar.pid,
                          type: "Hex",
                          cmd: "7e0081010000ef" // Example test cmd
                        }));
                        addHistory(`PID ${selectedPillar.pid} Flash`, 'cmd');
                      }}
                    >
                      Trigger Test Flash
                    </button>
                  </GlassPanel>
                </div>
              </div>
            )}
          </>
        ) : (
          <section className={styles.setupView}>
            <div className={styles.grid2col}>
              <GlassPanel title="Master Configuration">
                <div className={styles.formRow}>
                  <label>Master A (H1) IP</label>
                  <input
                    type="text"
                    value={ipInputs.H1}
                    onChange={(e) => setIpInputs({ ...ipInputs, H1: e.target.value })}
                    className={styles.input}
                  />
                </div>
                <div className={styles.formRow}>
                  <label>Master B (H2) IP</label>
                  <input
                    type="text"
                    value={ipInputs.H2}
                    onChange={(e) => setIpInputs({ ...ipInputs, H2: e.target.value })}
                    className={styles.input}
                  />
                </div>
                <button
                  className={styles.primaryBtn}
                  onClick={() => setMasterIPs({ ...ipInputs })}
                >
                  Save Master Setup
                </button>
              </GlassPanel>

              <GlassPanel title="MQTT WebSocket Bridge">
                <div className={styles.formRow}>
                  <label>RPi Broker Host (IP)</label>
                  <input
                    type="text"
                    value={mqttInputs.host}
                    onChange={(e) => setMqttInputs({ ...mqttInputs, host: e.target.value })}
                    className={styles.input}
                  />
                </div>
                <div className={styles.formRow}>
                  <label>WS Port (Default 9001)</label>
                  <input
                    type="number"
                    value={mqttInputs.port}
                    onChange={(e) => setMqttInputs({ ...mqttInputs, port: parseInt(e.target.value) })}
                    className={styles.input}
                  />
                </div>
                <button
                  className={styles.secondaryBtn}
                  onClick={() => setMqttConfig({ ...mqttInputs })}
                >
                  Connect to Broker
                </button>
              </GlassPanel>
            </div>

            <div className={styles.grid2col} style={{ marginTop: "2rem" }}>
              <GlassPanel title="Data Management">
                <p className={styles.helpText}>Factory fixed files (Read-only)</p>
                <div className={styles.fileStatus}>
                  <span>pmacs.csv</span><span className={styles.ok}>Loaded</span>
                </div>
                <div className={styles.fileStatus}>
                  <span>smacs.csv</span><span className={styles.ok}>Loaded</span>
                </div>
                <div className={styles.divider} />
                <button className={styles.secondaryBtn}>Reload Field Data (test_pids.csv)</button>
              </GlassPanel>

              <GlassPanel title="System Factory Reset" className={styles.dangerZone}>
                <p>Warning: This will clear all field-provisioned records and reset PIDs to factory default state.</p>
                <button className={styles.dangerBtn}>Execute Factory Reset</button>
              </GlassPanel>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
