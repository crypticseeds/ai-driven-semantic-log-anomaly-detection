"use client";

import { LogEntry } from "@/lib/api";
import { cn } from "@/lib/utils";
import { AlertTriangle, ChevronRight, Info, AlertCircle, Bug, Shield } from "lucide-react";
import { useState } from "react";

interface LogRowProps {
    log: LogEntry;
}

const LEVEL_ICONS: Record<string, any> = {
    INFO: Info,
    WARN: AlertTriangle,
    ERROR: AlertCircle,
    DEBUG: Bug,
};

const LEVEL_COLORS: Record<string, string> = {
    INFO: "text-blue-500",
    WARN: "text-yellow-500",
    ERROR: "text-red-500",
    DEBUG: "text-gray-500",
};

const LEVEL_BG: Record<string, string> = {
    INFO: "bg-blue-500/10",
    WARN: "bg-yellow-500/10",
    ERROR: "bg-red-500/10",
    DEBUG: "bg-gray-500/10",
}

export function LogRow({ log }: LogRowProps) {
    const [expanded, setExpanded] = useState(false);
    const Icon = LEVEL_ICONS[log.level] || Info;
    const colorClass = LEVEL_COLORS[log.level] || "text-gray-500";
    const bgClass = LEVEL_BG[log.level] || "bg-gray-500/10";

    const hasPII = log.pii_entities && Object.keys(log.pii_entities).length > 0;
    const displayMessage = log.redacted_message || log.message;

    return (
        <div className={cn(
            "border-b border-border hover:bg-muted/50 transition-all duration-150 font-mono text-sm group",
            log.is_anomaly && "bg-destructive/5 hover:bg-destructive/10",
            expanded && "bg-muted/30"
        )}>
            <div
                className="flex items-center gap-x-4 py-2.5 px-4 cursor-pointer"
                onClick={() => setExpanded(!expanded)}
            >
                <ChevronRight className={cn(
                    "w-4 h-4 text-muted-foreground transition-transform duration-200 shrink-0",
                    expanded && "rotate-90"
                )} />

                <div className="w-24 shrink-0 text-muted-foreground text-xs font-mono hidden lg:block" title={log.id}>
                    {log.id.slice(0, 8)}...
                </div>

                <div className="w-32 shrink-0 text-muted-foreground text-xs">
                    {new Date(log.timestamp).toLocaleTimeString()}
                </div>

                <div className={cn("w-16 shrink-0 font-bold flex items-center gap-1", colorClass)}>
                    <Icon className={cn("h-3.5 w-3.5", colorClass)} />
                    {log.level}
                </div>

                <div className="w-32 shrink-0 text-foreground truncate hidden md:block" title={log.service}>
                    {log.service}
                </div>

                <div className="flex-1 truncate text-foreground/90 flex items-center gap-2">
                    {log.is_anomaly && (
                        <span className="inline-flex items-center rounded-sm bg-destructive/20 px-1.5 py-0.5 text-xs font-medium text-destructive ring-1 ring-inset ring-destructive/30 shrink-0">
                            ANOMALY
                        </span>
                    )}
                    {hasPII && (
                        <span className="inline-flex items-center gap-1 rounded-sm bg-blue-500/20 px-1.5 py-0.5 text-xs font-medium text-blue-600 dark:text-blue-400 ring-1 ring-inset ring-blue-500/30 shrink-0">
                            <Shield className="h-3 w-3" />
                            PII
                        </span>
                    )}
                    <span className="truncate">{displayMessage}</span>
                </div>
            </div>

            {expanded && (
                <div className="px-10 py-4 bg-muted/20 border-t border-border/50 text-xs space-y-3 animate-in slide-in-from-top-2 duration-200">
                    <div className="grid grid-cols-[120px_1fr] gap-3">
                        <span className="text-muted-foreground font-semibold">ID:</span>
                        <span 
                            className="text-foreground font-mono cursor-pointer hover:bg-muted/50 px-1 py-0.5 rounded transition-colors select-all" 
                            title="Click to select full ID"
                            onClick={(e) => {
                                e.stopPropagation();
                                const selection = window.getSelection();
                                const range = document.createRange();
                                range.selectNodeContents(e.currentTarget);
                                selection?.removeAllRanges();
                                selection?.addRange(range);
                            }}
                        >
                            {log.id}
                        </span>

                        <span className="text-muted-foreground font-semibold">Timestamp:</span>
                        <span className="text-foreground font-mono">{new Date(log.timestamp).toLocaleString()}</span>

                        <span className="text-muted-foreground font-semibold">Service:</span>
                        <span className="text-foreground">{log.service}</span>

                        <span className="text-muted-foreground font-semibold">Level:</span>
                        <span className={cn("font-bold", colorClass)}>{log.level}</span>

                        <span className="text-muted-foreground font-semibold">Message:</span>
                        <span className="text-foreground whitespace-pre-wrap break-words">{displayMessage}</span>

                        {log.redacted_message && log.message !== log.redacted_message && (
                            <>
                                <span className="text-muted-foreground font-semibold">Original:</span>
                                <span className="text-foreground/70 whitespace-pre-wrap break-words italic">
                                    {log.message}
                                </span>
                            </>
                        )}

                        {log.cluster_id !== undefined && (
                            <>
                                <span className="text-muted-foreground font-semibold">Cluster ID:</span>
                                <span className="text-foreground">{log.cluster_id === -1 ? "Outlier (Noise)" : log.cluster_id}</span>
                            </>
                        )}

                        {log.anomaly_score !== undefined && (
                            <>
                                <span className="text-muted-foreground font-semibold">Anomaly Score:</span>
                                <span className="text-foreground">{log.anomaly_score.toFixed(4)}</span>
                            </>
                        )}

                        {hasPII && (
                            <>
                                <span className="text-muted-foreground font-semibold">PII Detected:</span>
                                <div className="flex flex-wrap gap-1">
                                    {Object.entries(log.pii_entities || {}).map(([type, count]) => (
                                        <span key={type} className="inline-flex items-center rounded px-2 py-0.5 bg-blue-500/20 text-blue-600 dark:text-blue-400 text-xs">
                                            {type}: {count}
                                        </span>
                                    ))}
                                </div>
                            </>
                        )}

                        {log.metadata && Object.keys(log.metadata).length > 0 && (
                            <>
                                <span className="text-muted-foreground font-semibold">Metadata:</span>
                                <code className="text-muted-foreground bg-muted p-2 rounded block w-full overflow-x-auto text-xs">
                                    {JSON.stringify(log.metadata, null, 2)}
                                </code>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
