import React from "react";
import styles from "./GlassPanel.module.css";

interface GlassPanelProps {
    children: React.ReactNode;
    className?: string;
    title?: string;
}

export default function GlassPanel({ children, className, title }: GlassPanelProps) {
    return (
        <div className={`glass-panel ${styles.panel} ${className || ""}`}>
            {title && <h3 className={styles.title}>{title}</h3>}
            {children}
        </div>
    );
}
