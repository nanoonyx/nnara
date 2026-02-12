import React from "react";
import styles from "./SlaveTile.module.css";

interface SlaveProps {
    sid: string;
    battery: number;
    lastComm: string;
    status: "success" | "fail";
    hall: string;
    rssi?: number;
    smac?: string;
}

export default function SlaveTile({ sid, battery, lastComm, status, hall, rssi, smac }: SlaveProps) {
    return (
        <div className={`glass-panel ${styles.tile}`}>
            <div className={styles.header}>
                <div className={styles.sidInfo}>
                    <span className={styles.sid}>{sid}</span>
                    <span className={styles.hallTag}>{hall}</span>
                </div>
                <span className={`${styles.statusDot} ${status === "success" ? styles.online : styles.offline}`} />
            </div>
            <div className={styles.body}>
                <div className={styles.stat}>
                    <span className={styles.label}>Battery</span>
                    <span className={`${styles.value} ${battery < 20 ? styles.low : ""}`}>{battery}%</span>
                </div>
                <div className={styles.stat}>
                    <span className={styles.label}>Signal</span>
                    <span className={styles.value}>{rssi || -40} dBm</span>
                </div>
            </div>
            {smac && <div className={styles.footer} style={{ fontSize: '10px', opacity: 0.5, marginTop: '8px', textAlign: 'center' }}>MAC: {smac}</div>}
        </div>
    );
}
