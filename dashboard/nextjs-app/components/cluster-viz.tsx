"use client";

import { ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Legend } from "recharts";
import { useEffect, useState } from "react";
import { api, Cluster, LogEntry } from "@/lib/api";
import { Loading } from "@/components/ui/loading";
import { AlertCircle, Brain, CheckCircle, Filter, BarChart3, Eye, EyeOff } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ClusterPoint {
    x: number;
    y: number;
    z: number;
    cluster: number;
    logId?: string;
    isOutlier?: boolean;
    hasLlmReasoning?: boolean;
    llmValidated?: boolean;
    anomalyScore?: number;
}



interface ClusterMetrics {
    totalClusters: number;
    totalOutliers: number;
    llmValidatedOutliers: number;
    tier1Anomalies: number;
    tier2Anomalies: number;
}

const COLORS: Record<string, string> = {
    "-1": "hsl(var(--destructive))",
    "0": "hsl(var(--primary))",
    "1": "hsl(220, 70%, 50%)",
    "2": "hsl(142, 70%, 45%)",
    "3": "hsl(48, 96%, 53%)",
    "4": "hsl(262, 83%, 58%)",
    "5": "hsl(346, 87%, 43%)",
    "6": "hsl(24, 70%, 50%)",
    "7": "hsl(197, 71%, 52%)",
    "8": "hsl(119, 41%, 51%)",
};

export function ClusterViz() {
    const [data, setData] = useState<ClusterPoint[]>([]);
    const [clusters, setClusters] = useState<Cluster[]>([]);
    const [outliers, setOutliers] = useState<LogEntry[]>([]);
    const [metrics, setMetrics] = useState<ClusterMetrics>({
        totalClusters: 0,
        totalOutliers: 0,
        llmValidatedOutliers: 0,
        tier1Anomalies: 0,
        tier2Anomalies: 0,
    });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filterValidation, setFilterValidation] = useState<'all' | 'validated' | 'unvalidated'>('all');
    const [showOutliersOnly, setShowOutliersOnly] = useState(false);

    const fetchClusterData = async () => {
        try {
            setLoading(true);
            setError(null);

            // Fetch clusters and outliers in parallel with Promise.allSettled
            // This allows partial success if one API call fails
            const [clustersResult, outliersResult] = await Promise.allSettled([
                api.getClusters(),
                api.getOutliers()
            ]);

            // Handle clusters result
            let clustersData: any[] = [];
            if (clustersResult.status === 'fulfilled') {
                clustersData = clustersResult.value || [];
                setClusters(clustersData);
            } else {
                console.error('Failed to fetch clusters:', clustersResult.reason);
                setClusters([]);
            }

            // Handle outliers result
            let outliersData: any[] = [];
            if (outliersResult.status === 'fulfilled') {
                outliersData = outliersResult.value || [];
                setOutliers(outliersData);
            } else {
                console.error('Failed to fetch outliers:', outliersResult.reason);
                setOutliers([]);
            }

            // Set error message if both calls failed
            if (clustersResult.status === 'rejected' && outliersResult.status === 'rejected') {
                setError("Failed to load cluster visualization data");
                return;
            }

            // Set partial error message if one call failed
            if (clustersResult.status === 'rejected') {
                setError("Failed to load cluster data (outliers only)");
            } else if (outliersResult.status === 'rejected') {
                setError("Failed to load outlier data (clusters only)");
            }

            // Calculate metrics
            const totalClusters = clustersData.filter(c => c.cluster_id !== -1).length;
            const totalOutliers = outliersData.length;
            const llmValidatedOutliers = outliersData.filter(o => o.llm_validated).length;
            
            setMetrics({
                totalClusters,
                totalOutliers,
                llmValidatedOutliers,
                tier1Anomalies: outliersData.filter(o => o.hybrid_tier === 'tier1').length,
                tier2Anomalies: outliersData.filter(o => o.hybrid_tier === 'tier2').length,
            });

            // Generate visualization data points
            const points: ClusterPoint[] = [];
            
            // Add cluster points (if we have cluster data)
            if (clustersData.length > 0) {
                clustersData.forEach((cluster, idx) => {
                    if (cluster.cluster_id === -1) return; // Skip outliers for now
                    
                    const baseX = (idx % 4) * 200 + 100;
                    const baseY = Math.floor(idx / 4) * 200 + 100;
                    const count = Math.min(cluster.count, 15); // Limit points for performance

                    for (let i = 0; i < count; i++) {
                        points.push({
                            x: baseX + (Math.random() - 0.5) * 80,
                            y: baseY + (Math.random() - 0.5) * 80,
                            z: 150 + Math.random() * 100,
                            cluster: cluster.cluster_id,
                            isOutlier: false,
                        });
                    }
                });
            } else if (totalOutliers > 0) {
                // If we have outliers but no cluster metadata, show a message
                console.warn('Clusters exist but metadata is not available. Showing outliers only.');
                // We'll still show outliers below
            }

            // Add outlier points
            outliersData.forEach((outlier, idx) => {
                points.push({
                    x: 50 + (idx % 10) * 80 + (Math.random() - 0.5) * 30,
                    y: 600 + Math.floor(idx / 10) * 60 + (Math.random() - 0.5) * 30,
                    z: 200 + (outlier.anomaly_score || 0) * 300,
                    cluster: -1,
                    logId: outlier.id,
                    isOutlier: true,
                    hasLlmReasoning: !!outlier.llm_reasoning,
                    llmValidated: outlier.llm_validated,
                    anomalyScore: outlier.anomaly_score,
                });
            });

            setData(points);
        } catch (err) {
            console.error("Error fetching cluster data:", err);
            setError("Failed to load cluster visualization data");
            
            // Fallback to mock data only in development
            if (process.env.NODE_ENV === 'development') {
                const mockData: ClusterPoint[] = [
                    { x: 100, y: 200, z: 200, cluster: 0, isOutlier: false },
                    { x: 120, y: 180, z: 260, cluster: 0, isOutlier: false },
                    { x: 300, y: 300, z: 200, cluster: 1, isOutlier: false },
                    { x: 320, y: 280, z: 240, cluster: 1, isOutlier: false },
                    { x: 500, y: 150, z: 180, cluster: 2, isOutlier: false },
                    { x: 200, y: 600, z: 400, cluster: -1, isOutlier: true, hasLlmReasoning: true, llmValidated: true, anomalyScore: 0.8 },
                    { x: 280, y: 620, z: 350, cluster: -1, isOutlier: true, hasLlmReasoning: false, llmValidated: false, anomalyScore: 0.6 },
                ];
                setData(mockData);
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchClusterData();
    }, []);

    // Filter data based on current filters
    const filteredData = data.filter(point => {
        if (showOutliersOnly && !point.isOutlier) return false;
        
        if (filterValidation !== 'all' && point.isOutlier) {
            if (filterValidation === 'validated' && !point.llmValidated) return false;
            if (filterValidation === 'unvalidated' && point.llmValidated) return false;
        }
        
        return true;
    });

    // Group data by cluster for different colors
    const clusterGroups = filteredData.reduce((acc, point) => {
        const key = String(point.cluster);
        if (!acc[key]) acc[key] = [];
        acc[key].push(point);
        return acc;
    }, {} as Record<string, ClusterPoint[]>);

    const CustomTooltip = ({ active, payload }: any) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload;
            return (
                <div className="bg-card border border-border rounded-lg p-3 shadow-lg">
                    <div className="space-y-1">
                        <div className="flex items-center gap-2">
                            <Badge variant={data.cluster === -1 ? "destructive" : "outline"}>
                                {data.cluster === -1 ? "Outlier" : `Cluster ${data.cluster}`}
                            </Badge>
                            {data.isOutlier && data.hasLlmReasoning && (
                                <Brain className="h-3 w-3 text-blue-500" />
                            )}
                            {data.isOutlier && data.llmValidated && (
                                <CheckCircle className="h-3 w-3 text-green-500" />
                            )}
                        </div>
                        {data.anomalyScore !== undefined && data.anomalyScore !== null && !isNaN(data.anomalyScore) && (
                            <p className="text-xs text-muted-foreground">
                                Anomaly Score: {data.anomalyScore.toFixed(3)}
                            </p>
                        )}
                        {data.logId && (
                            <p className="text-xs text-muted-foreground">
                                Log ID: {data.logId.slice(0, 8)}...
                            </p>
                        )}
                    </div>
                </div>
            );
        }
        return null;
    };

    if (loading) {
        return (
            <div className="space-y-6">
                <div className="flex items-center justify-center min-h-[400px]">
                    <Loading text="Loading cluster visualization..." />
                </div>
            </div>
        );
    }

    if (error && data.length === 0) {
        return (
            <div className="space-y-6">
                <Card className="border-destructive/50 bg-destructive/5">
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-2 text-destructive">
                            <AlertCircle className="h-4 w-4" />
                            <span className="text-sm">{error}</span>
                        </div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Metrics Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <Card>
                    <CardContent className="pt-4">
                        <div className="text-2xl font-bold">{metrics.totalClusters}</div>
                        <p className="text-xs text-muted-foreground">Clusters</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <div className="text-2xl font-bold text-destructive">{metrics.totalOutliers}</div>
                        <p className="text-xs text-muted-foreground">Outliers</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <div className="text-2xl font-bold text-green-600">{metrics.llmValidatedOutliers}</div>
                        <p className="text-xs text-muted-foreground">LLM Validated</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <div className="text-2xl font-bold text-orange-600">{metrics.tier1Anomalies}</div>
                        <p className="text-xs text-muted-foreground">Tier 1</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="pt-4">
                        <div className="text-2xl font-bold text-blue-600">{metrics.tier2Anomalies}</div>
                        <p className="text-xs text-muted-foreground">Tier 2</p>
                    </CardContent>
                </Card>
            </div>

            {/* Controls */}
            <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                    <Filter className="h-4 w-4" />
                    <Select value={filterValidation} onValueChange={(value: 'all' | 'validated' | 'unvalidated') => setFilterValidation(value)}>
                        <SelectTrigger className="w-[180px]">
                            <SelectValue placeholder="Filter validation" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">All Outliers</SelectItem>
                            <SelectItem value="validated">LLM Validated</SelectItem>
                            <SelectItem value="unvalidated">Unvalidated</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowOutliersOnly(!showOutliersOnly)}
                >
                    {showOutliersOnly ? <Eye className="h-4 w-4 mr-2" /> : <EyeOff className="h-4 w-4 mr-2" />}
                    {showOutliersOnly ? "Show All" : "Outliers Only"}
                </Button>
                <Button variant="outline" size="sm" onClick={fetchClusterData}>
                    <BarChart3 className="h-4 w-4 mr-2" />
                    Refresh
                </Button>
            </div>

            <Tabs defaultValue="visualization" className="w-full">
                <TabsList>
                    <TabsTrigger value="visualization">Cluster Visualization</TabsTrigger>
                    <TabsTrigger value="outliers">Outlier Analysis</TabsTrigger>
                </TabsList>

                <TabsContent value="visualization" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>HDBSCAN Cluster Visualization</CardTitle>
                            <CardDescription>
                                Semantic clustering results with hybrid anomaly detection pipeline
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="h-[500px] w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                                        <XAxis
                                            type="number"
                                            dataKey="x"
                                            name="Dimension 1"
                                            tick={false}
                                            axisLine={false}
                                        />
                                        <YAxis
                                            type="number"
                                            dataKey="y"
                                            name="Dimension 2"
                                            tick={false}
                                            axisLine={false}
                                        />
                                        <ZAxis
                                            type="number"
                                            dataKey="z"
                                            range={[60, 400]}
                                            name="Density/Score"
                                        />
                                        <Tooltip content={<CustomTooltip />} />
                                        {Object.entries(clusterGroups).map(([clusterId, points]) => (
                                            <Scatter
                                                key={clusterId}
                                                name={clusterId === "-1" ? "Outliers" : `Cluster ${clusterId}`}
                                                data={points}
                                                fill={COLORS[clusterId] || "hsl(var(--muted-foreground))"}
                                                shape={clusterId === "-1" ? "diamond" : "circle"}
                                            />
                                        ))}
                                        <Legend />
                                    </ScatterChart>
                                </ResponsiveContainer>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="outliers" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>Outlier Analysis</CardTitle>
                            <CardDescription>
                                Detailed view of outliers with LLM reasoning and validation status
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {outliers.length === 0 ? (
                                <div className="flex items-center justify-center h-32 text-center">
                                    <div>
                                        <p className="text-muted-foreground font-medium">No outliers found</p>
                                        <p className="text-sm text-muted-foreground/70 mt-1">
                                            Run clustering to identify anomalous logs
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <ScrollArea className="h-[400px]">
                                    <div className="space-y-3">
                                        {outliers.map((outlier) => (
                                            <div
                                                key={outlier.id}
                                                className="border border-border rounded-lg p-4 space-y-2"
                                            >
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <Badge variant="destructive">Outlier</Badge>
                                                        {outlier.llm_reasoning && (
                                                            <Badge variant="outline" className="text-blue-600">
                                                                <Brain className="h-3 w-3 mr-1" />
                                                                LLM Analyzed
                                                            </Badge>
                                                        )}
                                                        {outlier.llm_validated && (
                                                            <Badge variant="outline" className="text-green-600">
                                                                <CheckCircle className="h-3 w-3 mr-1" />
                                                                Validated
                                                            </Badge>
                                                        )}
                                                        {outlier.hybrid_tier && (
                                                            <Badge variant="secondary">
                                                                {outlier.hybrid_tier.toUpperCase()}
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <div className="text-sm text-muted-foreground">
                                                        Score: {outlier.anomaly_score?.toFixed(3) || 'N/A'}
                                                    </div>
                                                </div>
                                                <div className="text-sm">
                                                    <span className="font-medium">{outlier.service}</span> • {outlier.level}
                                                </div>
                                                <div className="text-sm text-muted-foreground">
                                                    {outlier.redacted_message || outlier.message}
                                                </div>
                                                {outlier.llm_reasoning && (
                                                    <div className="mt-2 p-3 bg-muted/50 rounded-md">
                                                        <div className="text-xs font-medium text-muted-foreground mb-1">
                                                            LLM Analysis:
                                                        </div>
                                                        <div className="text-sm">{outlier.llm_reasoning}</div>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}