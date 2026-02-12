import React from "react";
import styles from "./PillarTile.module.css";

interface PillarProps {
    pid: string;
    bid: string;
    sid: string;
    lastTime: string;
    lastCmd: string;
    rssi: number;
    status: "success" | "fail";
    color: string;
}

export default function PillarTile({ pid, bid, sid, lastTime, lastCmd, rssi, status, color }: PillarProps) {
    return (
        <div className={`glass-panel ${styles.tile}`}>
            <div className={styles.header}>
                <span className={styles.pid}>{pid}</span>
                <span className={`${styles.statusDot} ${status === "success" ? styles.online : styles.offline}`} />
            </div>
            <div className={styles.data}>
                <div className={styles.row}>
                    <span>Booth</span>
                    <span>{bid}</span>
                </div>
                <div className={styles.row}>
                    <span>Slave</span>
                    <span>{sid}</span>
                </div>
                <div className={styles.row}>
                    <span>Last Comm</span>
                    <span>{lastTime}</span>
                </div>
                <div className={styles.row}>
                    <span>Last Cmd</span>
                    <span className={styles.cmdVal}>{lastCmd}</span>
                </div>
                <div className={styles.row}>
                    <span>Signal</span>
                    <span>{rssi}dBm</span>
                </div>
            </div>
            <div className={styles.footer}>
                <div className={styles.colorIndicator} style={{ backgroundColor: color }} />
            </div>
        </div>
    );
}
