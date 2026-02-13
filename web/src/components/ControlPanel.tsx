import React, { useState } from "react";
import GlassPanel from "./GlassPanel";
import styles from "./ControlPanel.module.css";
import { mqttService } from "@/services/mqttService";

interface HistoryItem {
    id: string;
    msg: string;
    time: string;
    type: 'status' | 'cmd';
}

export default function ControlPanel({
    masterIPs,
    history = [],
    pillars = [],
    selectedPid = null,
    onCmd,
    onClear
}: {
    masterIPs: { H1: string, H2: string },
    history?: HistoryItem[],
    pillars?: any[],
    selectedPid?: string | null,
    onCmd?: (msg: string) => void,
    onClear?: () => void
}) {
    const [targetMode, setTargetMode] = useState("All");
    const [cmdType, setCmdType] = useState("Hex");
    const [ccode, setCcode] = useState("");
    const [selection, setSelection] = useState("All Halls");
    const [statusText, setStatusText] = useState("");

    // Sync from grid selection
    React.useEffect(() => {
        if (selectedPid) {
            setTargetMode("PID");
            setSelection(selectedPid);
        }
    }, [selectedPid]);

    // Compute unique booths
    const booths = React.useMemo(() => {
        const unique = new Set(pillars.map(p => p.bid));
        return Array.from(unique).sort();
    }, [pillars]);

    const pids = React.useMemo(() => {
        return pillars.map(p => p.pid).sort((a, b) => {
            const numA = parseInt(a.slice(1));
            const numB = parseInt(b.slice(1));
            return numA - numB;
        });
    }, [pillars]);

    const handleExecute = () => {
        setStatusText("Publishing...");

        const payload = {
            target: targetMode,
            type: cmdType,
            id: selection,
            cmd: ccode,
        };

        try {
            mqttService.publish("nara/cmd", JSON.stringify(payload));
            setStatusText("Sent!");
            if (onCmd) {
                onCmd(`${targetMode}: ${ccode || selection}`);
            }
            setTimeout(() => setStatusText(""), 2000);
        } catch (err) {
            setStatusText("No Connect");
            setTimeout(() => setStatusText(""), 2000);
        }
    };

    return (
        <GlassPanel title="Execution Control" className={styles.container}>
            <div className={styles.section}>
                <label className={styles.label}>Targeting Mode</label>
                <div className={styles.modeGrid}>
                    {["All", "Group", "Slave", "Booth", "PID", "Subset"].map((mode) => (
                        <button
                            key={mode}
                            className={`${styles.modeBtn} ${targetMode === mode ? styles.active : ""}`}
                            onClick={() => {
                                setTargetMode(mode);
                                if (mode === "All") {
                                    setCmdType("MCMD");
                                    setSelection("All Halls");
                                }
                                if (mode === "Slave") {
                                    setCmdType("SCMD");
                                    setSelection("S1");
                                }
                            }}
                        >
                            {mode}
                        </button>
                    ))}
                </div>
            </div>

            <div className={styles.section}>
                <label className={styles.label}>Command Type</label>
                <div className={styles.typeGrid}>
                    {["MCMD", "SCMD", "Hex"].map((type) => (
                        <button
                            key={type}
                            className={`${styles.typeBtn} ${cmdType === type ? styles.active : ""}`}
                            onClick={() => setCmdType(type)}
                        >
                            {type}
                        </button>
                    ))}
                </div>
            </div>

            <div className={styles.section}>
                <label className={styles.label}>Selection</label>
                <select
                    className={styles.select}
                    value={selection}
                    onChange={(e) => setSelection(e.target.value)}
                >
                    {targetMode === "All" && ["All","MA", "MB"].map(h => <option key={h} value={h}>{h}</option>)}
                    {/* {>All Halls</option>} */}
                    {targetMode === "Group" && ["GA", "GB", "GC", "GD", "GE"].map(g => <option key={g} value={g}>{g}</option>)}
                    {targetMode === "Slave" && [1, 2, 3, 4, 10, 15, 24].map(s => <option key={`S${s}`} value={`S${s}`}>S{s}</option>)}
                    {targetMode === "Booth" && booths.map(b => <option key={b} value={b}>{b}</option>)}
                    {targetMode === "PID" && pids.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
            </div>

            <div className={styles.section}>
                <label className={styles.label}>{cmdType} Input</label>
                <div className={styles.inputGroup}>
                    <input
                        type="text"
                        className={styles.input}
                        placeholder={cmdType === "Hex" ? "7e0081...ef" : `Enter ${cmdType} parameter...`}
                        value={ccode}
                        onChange={(e) => setCcode(e.target.value)}
                    />
                    <button
                        className={styles.sendBtn}
                        onClick={handleExecute}
                    >
                        {statusText || "Execute"}
                    </button>
                </div>
            </div>

            <div className={styles.section}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label className={styles.label}>History</label>
                    {onClear && (
                        <button
                            onClick={onClear}
                            style={{
                                background: 'transparent',
                                border: 'none',
                                color: '#a5a6bc',
                                fontSize: '0.7rem',
                                cursor: 'pointer',
                                padding: '0',
                                textDecoration: 'underline',
                                opacity: 0.7
                            }}
                            title="Clear History"
                        >
                            Clear
                        </button>
                    )}
                </div>
                <div className={styles.history}>
                    {history.length > 0 ? history.map((item) => (
                        <div key={item.id} className={styles.historyItem}>
                            <span style={{ color: item.type === 'cmd' ? 'var(--primary)' : '#a5a6bc' }}>
                                {item.msg}
                            </span>
                            <span className={styles.time}>{item.time}</span>
                        </div>
                    )) : (
                        <div className={styles.historyItem}>
                            <span style={{ color: '#6a6b82' }}>No recent activity.</span>
                        </div>
                    )}
                </div>
            </div>
        </GlassPanel>
    );
}
