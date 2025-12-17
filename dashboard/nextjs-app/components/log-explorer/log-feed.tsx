"use client";

import { LogEntry } from "@/lib/api";
import { LogRow } from "./log-row";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import { api, APIError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface LogFeedProps {
    filters?: {
        level?: string;
        service?: string;
        cluster_id?: number;
        is_anomaly?: boolean;
        query?: string;
    };
}

export function LogFeed({ filters = {} }: LogFeedProps) {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [refreshing, setRefreshing] = useState(false);

    const fetchLogs = useCallback(async (showRefreshing = false) => {
        try {
            if (showRefreshing) setRefreshing(true);
            else setLoading(true);
            setError(null);

            const response = await api.searchLogs({
                ...filters,
                limit: 100,
                offset: 0,
            });

            setLogs(response.logs || []);
        } catch (err) {
            let message = "Failed to load logs. Please check your connection.";
            
            if (err instanceof APIError) {
                message = `Failed to load logs: ${err.statusText}`;
                if (err.data?.suggestion) {
                    message += ` ${err.data.suggestion}`;
                }
            } else if (err instanceof Error) {
                if (err.message.includes('API Response Format Error')) {
                    message = "Data format mismatch detected. The backend response format may have changed.";
                } else if (err.message.includes('Network error')) {
                    message = err.message;
                } else {
                    message = `Error: ${err.message}`;
                }
            }
            
            setError(message);
            console.error("Error fetching logs:", err);
            
            // Log additional debug information in development
            if (process.env.NODE_ENV === 'development') {
                console.error("Debug info:", {
                    errorType: err?.constructor?.name,
                    errorMessage: err instanceof Error ? err.message : 'Unknown error',
                    errorData: err instanceof APIError ? err.data : undefined,
                    filters: filters,
                });
            }
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, [filters]);

    useEffect(() => {
        fetchLogs();
    }, [fetchLogs]);

    if (loading) {
        return (
            <div className="flex-1 flex flex-col h-full min-h-0 bg-background">
                <div className="flex items-center px-4 h-10 border-b border-border bg-muted/10 text-xs font-semibold text-muted-foreground">
                    <div className="w-10"></div>
                    <div className="w-32">Time</div>
                    <div className="w-16">Level</div>
                    <div className="w-32 hidden md:block">Service</div>
                    <div className="flex-1">Message</div>
                </div>
                <div className="flex-1 p-4 space-y-2">
                    {Array.from({ length: 10 }).map((_, i) => (
                        <div key={i} className="flex items-center gap-4">
                            <Skeleton className="w-10 h-8" />
                            <Skeleton className="w-32 h-8" />
                            <Skeleton className="w-16 h-8" />
                            <Skeleton className="w-32 h-8 hidden md:block" />
                            <Skeleton className="flex-1 h-8" />
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex-1 flex flex-col h-full min-h-0 bg-background items-center justify-center p-8">
                <div className="flex flex-col items-center gap-4 max-w-md text-center">
                    <AlertCircle className="h-12 w-12 text-destructive" />
                    <div>
                        <h3 className="font-semibold text-lg mb-1">Failed to load logs</h3>
                        <p className="text-sm text-muted-foreground">{error}</p>
                    </div>
                    <Button onClick={() => fetchLogs()} variant="outline">
                        <RefreshCw className="mr-2 h-4 w-4" />
                        Retry
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col h-full min-h-0 bg-background">
            {/* Feed Header */}
            <div className="flex items-center px-4 h-10 border-b border-border bg-muted/10 text-xs font-semibold text-muted-foreground sticky top-0 z-10 backdrop-blur-sm">
                <div className="w-10"></div>
                <div className="w-32">Time</div>
                <div className="w-16">Level</div>
                <div className="w-32 hidden md:block">Service</div>
                <div className="flex-1">Message</div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => fetchLogs(true)}
                    disabled={refreshing}
                    className="h-6 w-6 p-0 ml-auto"
                >
                    <RefreshCw className={refreshing ? "animate-spin" : ""} />
                </Button>
            </div>

            <ScrollArea className="flex-1 h-full">
                {logs.length === 0 ? (
                    <div className="flex items-center justify-center h-full p-8">
                        <div className="text-center max-w-md">
                            <div className="text-4xl mb-4">📋</div>
                            <h3 className="text-lg font-medium text-foreground mb-2">No logs found</h3>
                            <p className="text-sm text-muted-foreground mb-4">
                                {Object.keys(filters).length > 0 
                                    ? "No logs match your current filters. Try adjusting your search criteria."
                                    : "No log data is currently available. This could mean there are no logs in the system or they haven't been processed yet."
                                }
                            </p>
                            <div className="space-y-2 text-xs text-muted-foreground">
                                <p>• Check if your log sources are configured correctly</p>
                                <p>• Verify that logs are being ingested into the system</p>
                                <p>• Try refreshing the page or adjusting your time range</p>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div>
                        {logs.map(log => (
                            <LogRow key={log.id} log={log} />
                        ))}
                    </div>
                )}
            </ScrollArea>
        </div>
    );
}
