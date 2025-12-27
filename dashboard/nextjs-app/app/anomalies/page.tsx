"use client";

import { useState, useEffect, useCallback } from "react";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { Loading } from "@/components/ui/loading";
import { AlertCircle, RefreshCw } from "lucide-react";
import { api, LogEntry, APIError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LogRow } from "@/components/log-explorer/log-row";
import { ScrollArea } from "@/components/ui/scroll-area";

export default function AnomaliesPage() {
    const [anomalies, setAnomalies] = useState<LogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [detecting, setDetecting] = useState(false);

    const fetchAnomalies = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const response = await api.searchLogs({
                is_anomaly: true,
                limit: 100,
            });
            setAnomalies(response.logs || []);
        } catch (err) {
            const message = err instanceof APIError
                ? `Failed to load anomalies: ${err.statusText}`
                : "Failed to load anomalies. Please check your connection.";
            setError(message);
            console.error("Error fetching anomalies:", err);
        } finally {
            setLoading(false);
        }
    }, []);

    const runDetection = async () => {
        try {
            setDetecting(true);
            setError(null);
            await api.detectAnomaliesIsolationForest();
            // Refresh anomalies after detection
            await fetchAnomalies();
        } catch (err) {
            const message = err instanceof APIError
                ? `Failed to run detection: ${err.statusText}`
                : "Failed to run anomaly detection.";
            setError(message);
            console.error("Error running detection:", err);
        } finally {
            setDetecting(false);
        }
    };

    useEffect(() => {
        fetchAnomalies();
    }, [fetchAnomalies]);

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Loading text="Loading anomalies..." />
            </div>
        );
    }

    if (error && anomalies.length === 0) {
        return (
            <div className="flex items-center justify-center min-h-[400px] p-6">
                <Card className="max-w-md w-full">
                    <CardHeader>
                        <div className="flex items-center gap-2">
                            <AlertCircle className="h-5 w-5 text-destructive" />
                            <CardTitle>Error</CardTitle>
                        </div>
                        <CardDescription>{error}</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button onClick={fetchAnomalies} variant="outline" className="w-full">
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Retry
                        </Button>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <ErrorBoundary>
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold">Anomalies</h2>
                        <p className="text-muted-foreground mt-1">
                            Detected anomalous log entries requiring attention
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button
                            onClick={runDetection}
                            disabled={detecting}
                            variant="outline"
                        >
                            {detecting ? (
                                <>
                                    <Loading className="mr-2" size="sm" />
                                    Detecting...
                                </>
                            ) : (
                                <>
                                    <RefreshCw className="mr-2 h-4 w-4" />
                                    Run Detection
                                </>
                            )}
                        </Button>
                        <Button onClick={fetchAnomalies} variant="outline" size="icon">
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                {error && (
                    <Card className="border-destructive/50 bg-destructive/5">
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-2 text-destructive">
                                <AlertCircle className="h-4 w-4" />
                                <span className="text-sm">{error}</span>
                            </div>
                        </CardContent>
                    </Card>
                )}

                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle>Anomalous Logs</CardTitle>
                                <CardDescription>
                                    {anomalies.length} anomaly{anomalies.length !== 1 ? "ies" : ""} detected
                                </CardDescription>
                            </div>
                            <Badge variant="destructive">{anomalies.length}</Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        {anomalies.length === 0 ? (
                            <div className="flex items-center justify-center h-64 text-center p-6">
                                <div>
                                    <p className="text-muted-foreground font-medium">No anomalies detected</p>
                                    <p className="text-sm text-muted-foreground/70 mt-1">
                                        Run anomaly detection to identify unusual patterns
                                    </p>
                                </div>
                            </div>
                        ) : (
                            <ScrollArea className="h-[calc(100vh-20rem)]">
                                <div>
                                    {anomalies.map(log => (
                                        <LogRow key={log.id} log={log} />
                                    ))}
                                </div>
                            </ScrollArea>
                        )}
                    </CardContent>
                </Card>
            </div>
        </ErrorBoundary>
    );
}

