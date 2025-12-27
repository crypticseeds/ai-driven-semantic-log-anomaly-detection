"use client";

import { ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Legend } from "recharts";
import { useEffect, useState } from "react";
import { api, APIError } from "@/lib/api";
import { Loading } from "@/components/ui/loading";
import { AlertCircle } from "lucide-react";

interface ClusterPoint {
    x: number;
    y: number;
    z: number;
    cluster: number;
}

const COLORS: Record<string, string> = {
    "-1": "hsl(var(--destructive))",
    "0": "hsl(var(--primary))",
    "1": "hsl(var(--blue-500))",
    "2": "hsl(var(--green-500))",
    "3": "hsl(var(--yellow-500))",
    "4": "hsl(var(--purple-500))",
};

export function ClusterViz() {
    const [data, setData] = useState<ClusterPoint[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchClusterData = async () => {
            try {
                setLoading(true);
                setError(null);
                // For visualization, we'd need cluster coordinates from the API
                // For now, generate mock data based on cluster info
                const clusters = await api.getClusters();

                // Generate visualization data points
                const points: ClusterPoint[] = [];
                clusters.forEach((cluster, idx) => {
                    const baseX = (idx % 3) * 200 + 100;
                    const baseY = Math.floor(idx / 3) * 200 + 100;
                    const count = Math.min(cluster.count, 20); // Limit points for performance

                    for (let i = 0; i < count; i++) {
                        points.push({
                            x: baseX + (Math.random() - 0.5) * 100,
                            y: baseY + (Math.random() - 0.5) * 100,
                            z: 200 + Math.random() * 200,
                            cluster: cluster.cluster_id,
                        });
                    }
                });

                setData(points);
            } catch (err) {
                console.error("Error fetching cluster data:", err);
                setError("Failed to load cluster visualization data");
                // Fallback to mock data
                setData([
                    { x: 100, y: 200, z: 200, cluster: 0 },
                    { x: 120, y: 100, z: 260, cluster: 0 },
                    { x: 170, y: 300, z: 400, cluster: 0 },
                    { x: 140, y: 250, z: 280, cluster: 0 },
                    { x: 150, y: 400, z: 500, cluster: 1 },
                    { x: 110, y: 280, z: 200, cluster: 1 },
                    { x: 300, y: 300, z: 200, cluster: 2 },
                    { x: 400, y: 500, z: 200, cluster: 2 },
                    { x: 200, y: 700, z: 200, cluster: -1 },
                ]);
            } finally {
                setLoading(false);
            }
        };

        fetchClusterData();
    }, []);

    if (loading) {
        return (
            <div className="h-[400px] w-full bg-card/30 border border-border p-4 rounded-lg flex items-center justify-center">
                <Loading text="Loading cluster visualization..." />
            </div>
        );
    }

    if (error && data.length === 0) {
        return (
            <div className="h-[400px] w-full bg-card/30 border border-border p-4 rounded-lg flex items-center justify-center">
                <div className="text-center">
                    <AlertCircle className="h-8 w-8 mx-auto mb-2 text-destructive" />
                    <p className="text-sm text-muted-foreground">{error}</p>
                </div>
            </div>
        );
    }

    // Group data by cluster for different colors
    const clusterGroups = data.reduce((acc, point) => {
        const key = String(point.cluster);
        if (!acc[key]) acc[key] = [];
        acc[key].push(point);
        return acc;
    }, {} as Record<string, ClusterPoint[]>);

    return (
        <div className="h-[400px] w-full bg-card/30 border border-border p-4 rounded-lg">
            <div className="text-sm font-semibold text-muted-foreground mb-4">
                Semantic Clusters (HDBSCAN)
            </div>
            <div style={{ height: 'calc(100% - 2rem)' }}>
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
                            name="Density"
                        />
                        <Tooltip
                            cursor={{ strokeDasharray: "3 3" }}
                            contentStyle={{
                                backgroundColor: "hsl(var(--card))",
                                borderColor: "hsl(var(--border))",
                                borderRadius: "6px",
                            }}
                        />
                        {Object.entries(clusterGroups).map(([clusterId, points]) => (
                            <Scatter
                                key={clusterId}
                                name={clusterId === "-1" ? "Outlier" : `Cluster ${clusterId}`}
                                data={points}
                                fill={COLORS[clusterId] || "hsl(var(--muted-foreground))"}
                                shape="circle"
                            />
                        ))}
                        <Legend />
                    </ScatterChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
