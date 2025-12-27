"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useEffect, useState, useCallback } from "react";
import { api, APIError, VolumeData } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { Button } from "@/components/ui/button";
import { RefreshCw, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChartVolumeData {
    time: string;
    count: number;
    timestamp: string; // Keep original timestamp for reference
}

export function VolumeChart() {
    const [data, setData] = useState<ChartVolumeData[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<Error | string | null>(null);
    const [refreshing, setRefreshing] = useState(false);
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

    const fetchVolumeData = useCallback(async (isRefresh = false) => {
        try {
            if (isRefresh) {
                setRefreshing(true);
            } else {
                setLoading(true);
            }
            setError(null);
            
            // Fetch real volume data from the backend
            const response = await api.getLogVolume({
                hours: 1,           // Last hour
                bucket_minutes: 5   // 5-minute buckets
            });

            // Validate response structure
            if (!response.volume_data || !Array.isArray(response.volume_data)) {
                throw new Error("Invalid volume data format received from server");
            }

            // Transform the data for the chart
            const chartData: ChartVolumeData[] = response.volume_data.map((bucket: VolumeData, index: number) => {
                if (!bucket.timestamp || typeof bucket.count !== 'number') {
                    console.warn(`Invalid volume bucket at index ${index}:`, bucket);
                    return {
                        time: `Bucket ${index}`,
                        count: 0,
                        timestamp: new Date().toISOString()
                    };
                }

                const timestamp = new Date(bucket.timestamp);
                const timeStr = timestamp.toLocaleTimeString([], { 
                    hour: '2-digit', 
                    minute: '2-digit' 
                });

                return {
                    time: timeStr,
                    count: bucket.count,
                    timestamp: bucket.timestamp
                };
            });

            setData(chartData);
            setLastUpdate(new Date());
        } catch (err) {
            console.error("Error fetching volume data:", err);
            
            let errorToSet: Error | string;
            if (err instanceof APIError) {
                errorToSet = new Error(`Failed to fetch volume data: ${err.statusText}`);
            } else if (err instanceof Error) {
                errorToSet = err;
            } else {
                errorToSet = "Failed to fetch volume data";
            }
            
            // Only set blocking error if we have no existing data
            if (data.length === 0) {
                setError(errorToSet);
                setData([]);
            } else {
                // Keep existing data and just log the error for non-blocking display
                console.warn("Volume data fetch failed, keeping existing data:", errorToSet);
                setError(null); // Clear any previous blocking errors
            }
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, [data.length]);

    useEffect(() => {
        fetchVolumeData();
        
        // Refresh every 30 seconds
        const interval = setInterval(() => fetchVolumeData(true), 30000);
        return () => clearInterval(interval);
    }, [fetchVolumeData]);

    const totalLogs = data.reduce((sum, bucket) => sum + bucket.count, 0);

    if (loading) {
        return (
            <div className="h-32 w-full bg-card/30 border-b border-border p-4">
                <div className="flex items-center justify-between mb-2">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-4 w-4 rounded-full" />
                </div>
                <Skeleton className="h-full w-full rounded" />
            </div>
        );
    }

    if (error && data.length === 0) {
        return (
            <div className="h-32 w-full bg-card/30 border-b border-border p-4">
                <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-semibold text-muted-foreground">
                        Log Volume (Last Hour)
                    </div>
                    <Button
                        onClick={() => fetchVolumeData(true)}
                        size="sm"
                        variant="ghost"
                        disabled={refreshing}
                        className="h-6 w-6 p-0"
                    >
                        <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                    </Button>
                </div>
                <div className="flex items-center justify-center h-full">
                    <div className="text-center">
                        <AlertCircle className="h-6 w-6 text-destructive mx-auto mb-2" />
                        <div className="text-xs text-destructive mb-1">Failed to load volume data</div>
                        <div className="text-xs text-muted-foreground max-w-48">
                            {typeof error === 'string' ? error : error.message}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (data.length === 0) {
        return (
            <div className="h-32 w-full bg-card/30 border-b border-border p-4">
                <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-semibold text-muted-foreground">
                        Log Volume (Last Hour)
                    </div>
                    <Button
                        onClick={() => fetchVolumeData(true)}
                        size="sm"
                        variant="ghost"
                        disabled={refreshing}
                        className="h-6 w-6 p-0"
                    >
                        <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                    </Button>
                </div>
                <div className="flex items-center justify-center h-full">
                    <div className="text-center">
                        <div className="text-xs text-muted-foreground mb-1">No log data available</div>
                        <div className="text-xs text-muted-foreground/70">
                            Check back later or verify your data sources
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="h-32 w-full bg-card/30 border-b border-border p-4">
            <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-semibold text-muted-foreground">
                    Log Volume (Last Hour) - {totalLogs} total logs
                    {lastUpdate && (
                        <span className="text-muted-foreground/70 ml-2">
                            (Updated: {lastUpdate.toLocaleTimeString()})
                        </span>
                    )}
                </div>
                <Button
                    onClick={() => fetchVolumeData(true)}
                    size="sm"
                    variant="ghost"
                    disabled={refreshing}
                    className="h-6 w-6 p-0"
                    title="Refresh volume data"
                >
                    <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                </Button>
            </div>
            <div className="h-full w-full">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
                        <XAxis
                            dataKey="time"
                            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                            axisLine={false}
                            tickLine={false}
                            interval="preserveStartEnd"
                        />
                        <YAxis
                            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                            axisLine={false}
                            tickLine={false}
                            width={30}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: "hsl(var(--card))",
                                borderColor: "hsl(var(--border))",
                                fontSize: "12px",
                                borderRadius: "6px",
                            }}
                            itemStyle={{ color: "hsl(var(--foreground))" }}
                            cursor={{ fill: "hsl(var(--muted))", opacity: 0.2 }}
                            formatter={(value, name) => [
                                `${value} logs`,
                                'Count'
                            ]}
                            labelFormatter={(label) => `Time: ${label}`}
                        />
                        <Bar
                            dataKey="count"
                            fill="hsl(var(--primary))"
                            radius={[4, 4, 0, 0]}
                            animationDuration={300}
                        />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
