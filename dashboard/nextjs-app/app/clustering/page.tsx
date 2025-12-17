"use client";

import { ClusterViz } from "@/components/cluster-viz";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { api, Cluster, APIError } from "@/lib/api";
import { Loading } from "@/components/ui/loading";
import { RefreshCw, Play, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { LogRow } from "@/components/log-explorer/log-row";

export default function ClusteringPage() {
    const [clusters, setClusters] = useState<Cluster[]>([]);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedCluster, setSelectedCluster] = useState<number | null>(null);

    const fetchClusters = async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await api.getClusters();
            setClusters(data || []);
        } catch (err) {
            const message = err instanceof APIError
                ? `Failed to load clusters: ${err.statusText}`
                : "Failed to load clusters. Please check your connection.";
            setError(message);
            console.error("Error fetching clusters:", err);
        } finally {
            setLoading(false);
        }
    };

    const runClustering = async () => {
        try {
            setRunning(true);
            setError(null);
            await api.runClustering();
            // Refresh clusters after running
            await fetchClusters();
        } catch (err) {
            const message = err instanceof APIError
                ? `Failed to run clustering: ${err.statusText}`
                : "Failed to run clustering.";
            setError(message);
            console.error("Error running clustering:", err);
        } finally {
            setRunning(false);
        }
    };

    useEffect(() => {
        fetchClusters();
    }, []);

    return (
        <ErrorBoundary>
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold">Log Clusters</h2>
                        <p className="text-muted-foreground mt-1">
                            Visualizing semantic similarity groups. Outliers (Cluster -1) may indicate anomalies.
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button
                            onClick={runClustering}
                            disabled={running}
                            variant="outline"
                        >
                            {running ? (
                                <>
                                    <Loading className="mr-2" size="sm" />
                                    Running...
                                </>
                            ) : (
                                <>
                                    <Play className="mr-2 h-4 w-4" />
                                    Run Clustering
                                </>
                            )}
                        </Button>
                        <Button onClick={fetchClusters} variant="outline" size="icon">
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

                {loading ? (
                    <div className="flex items-center justify-center min-h-[400px]">
                        <Loading text="Loading clusters..." />
                    </div>
                ) : (
                    <div className="grid gap-6 lg:grid-cols-2">
                        <Card>
                            <CardHeader>
                                <CardTitle>Cluster Visualization</CardTitle>
                                <CardDescription>
                                    HDBSCAN semantic clustering results
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <ClusterViz />
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle>Clusters</CardTitle>
                                <CardDescription>
                                    {clusters.length} cluster{clusters.length !== 1 ? "s" : ""} found
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="p-0">
                                {clusters.length === 0 ? (
                                    <div className="flex items-center justify-center h-64 text-center p-6">
                                        <div>
                                            <p className="text-muted-foreground font-medium">No clusters found</p>
                                            <p className="text-sm text-muted-foreground/70 mt-1">
                                                Run clustering to group similar logs
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <ScrollArea className="h-[400px]">
                                        <div className="p-4 space-y-2">
                                            {clusters.map((cluster) => (
                                                <button
                                                    key={cluster.cluster_id}
                                                    onClick={() => setSelectedCluster(
                                                        selectedCluster === cluster.cluster_id ? null : cluster.cluster_id
                                                    )}
                                                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                                                        selectedCluster === cluster.cluster_id
                                                            ? "border-primary bg-primary/5"
                                                            : "border-border hover:bg-muted/50"
                                                    }`}
                                                >
                                                    <div className="flex items-center justify-between">
                                                        <div className="flex items-center gap-2">
                                                            <Badge
                                                                variant={
                                                                    cluster.cluster_id === -1
                                                                        ? "destructive"
                                                                        : "outline"
                                                                }
                                                            >
                                                                {cluster.cluster_id === -1
                                                                    ? "Outlier"
                                                                    : `Cluster ${cluster.cluster_id}`}
                                                            </Badge>
                                                            <span className="text-sm text-muted-foreground">
                                                                {cluster.count} log{cluster.count !== 1 ? "s" : ""}
                                                            </span>
                                                        </div>
                                                    </div>
                                                    {selectedCluster === cluster.cluster_id && cluster.sample_logs && (
                                                        <div className="mt-3 space-y-1 border-t border-border pt-3">
                                                            {cluster.sample_logs.slice(0, 3).map((log) => (
                                                                <div
                                                                    key={log.id}
                                                                    className="text-xs text-muted-foreground truncate"
                                                                >
                                                                    {log.message}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </button>
                                            ))}
                                        </div>
                                    </ScrollArea>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                )}
            </div>
        </ErrorBoundary>
    );
}
