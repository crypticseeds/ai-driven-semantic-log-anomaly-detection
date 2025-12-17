"use client";

import { cn } from "@/lib/utils";
import { Check, ChevronDown, Filter, X, AlertCircle, RefreshCw } from "lucide-react";
import { useState, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { api, APIError } from "@/lib/api";

interface FacetOption {
    label: string;
    count: number;
    value: string;
}

interface FacetGroup {
    id: string;
    label: string;
    options: FacetOption[];
}

interface FacetSidebarProps {
    selectedFilters: {
        level?: string;
        service?: string;
        cluster_id?: number;
        is_anomaly?: boolean;
    };
    onFilterChange: (filters: {
        level?: string;
        service?: string;
        cluster_id?: number;
        is_anomaly?: boolean;
    }) => void;
}

export function FacetSidebar({ selectedFilters, onFilterChange }: FacetSidebarProps) {
    const [openFacets, setOpenFacets] = useState<Record<string, boolean>>({
        service: true,
        level: true,
        cluster: true,
        anomaly: true,
    });
    const [facets, setFacets] = useState<FacetGroup[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [retrying, setRetrying] = useState(false);

    const fetchFacets = async (isRetry = false) => {
        try {
            if (isRetry) {
                setRetrying(true);
            } else {
                setLoading(true);
            }
            setError(null);
            
            // For now, we'll derive facets from search results
            // In a real implementation, you'd have a dedicated facets endpoint
            const response = await api.searchLogs({ limit: 1000 });
            
            // Group by service
            const services = new Map<string, number>();
            const levels = new Map<string, number>();
            const clusters = new Map<number, number>();
            let anomalyCount = 0;

            response.logs.forEach(log => {
                services.set(log.service, (services.get(log.service) || 0) + 1);
                levels.set(log.level, (levels.get(log.level) || 0) + 1);
                if (log.cluster_id !== undefined) {
                    clusters.set(log.cluster_id, (clusters.get(log.cluster_id) || 0) + 1);
                }
                if (log.is_anomaly) anomalyCount++;
            });

            setFacets([
                {
                    id: "service",
                    label: "Service",
                    options: Array.from(services.entries())
                        .map(([value, count]) => ({ label: value, count, value }))
                        .sort((a, b) => b.count - a.count),
                },
                {
                    id: "level",
                    label: "Level",
                    options: Array.from(levels.entries())
                        .map(([value, count]) => ({ label: value, count, value }))
                        .sort((a, b) => b.count - a.count),
                },
                {
                    id: "cluster",
                    label: "Cluster",
                    options: Array.from(clusters.entries())
                        .map(([id, count]) => ({
                            label: id === -1 ? "Outlier (Noise)" : `Cluster ${id}`,
                            count,
                            value: String(id),
                        }))
                        .sort((a, b) => Number(a.value) - Number(b.value)),
                },
                {
                    id: "anomaly",
                    label: "Anomalies",
                    options: [
                        { label: "Anomalies Only", count: anomalyCount, value: "true" },
                        { label: "Normal Only", count: response.logs.length - anomalyCount, value: "false" },
                    ],
                },
            ]);
        } catch (err) {
            console.error("Error fetching facets:", err);
            
            let errorMessage = "Failed to load filter options";
            if (err instanceof APIError) {
                errorMessage = `Failed to load filters: ${err.statusText}`;
            } else if (err instanceof Error) {
                if (err.message.includes('Network error')) {
                    errorMessage = "Network error: Unable to connect to server";
                } else {
                    errorMessage = `Error: ${err.message}`;
                }
            }
            
            setError(errorMessage);
            
            // Set empty facets on error
            setFacets([]);
        } finally {
            setLoading(false);
            setRetrying(false);
        }
    };

    useEffect(() => {
        fetchFacets();
    }, []);

    const toggleFacet = (id: string) => {
        setOpenFacets((prev) => ({ ...prev, [id]: !prev[id] }));
    };

    const toggleFilter = (facetId: string, value: string) => {
        const newFilters = { ...selectedFilters };

        if (facetId === "service") {
            newFilters.service = newFilters.service === value ? undefined : value;
        } else if (facetId === "level") {
            newFilters.level = newFilters.level === value ? undefined : value;
        } else if (facetId === "cluster") {
            const clusterId = Number(value);
            newFilters.cluster_id = newFilters.cluster_id === clusterId ? undefined : clusterId;
        } else if (facetId === "anomaly") {
            const isAnomaly = value === "true";
            newFilters.is_anomaly = newFilters.is_anomaly === isAnomaly ? undefined : isAnomaly;
        }

        onFilterChange(newFilters);
    };

    const clearFilters = () => {
        onFilterChange({});
    };

    const hasActiveFilters = Object.values(selectedFilters).some(v => v !== undefined);

    return (
        <div className="w-64 border-r border-border bg-card/30 flex flex-col h-full hidden lg:flex">
            <div className="flex items-center justify-between p-4 border-b border-border">
                <div className="flex items-center gap-x-2 text-sm font-semibold text-foreground">
                    <Filter className="w-4 h-4" />
                    <span>Filters</span>
                </div>
                {hasActiveFilters && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={clearFilters}
                        className="h-6 px-2 text-xs"
                    >
                        <X className="h-3 w-3 mr-1" />
                        Clear
                    </Button>
                )}
            </div>

            <ScrollArea className="flex-1 p-4">
                {loading ? (
                    <div className="space-y-6">
                        {[1, 2, 3].map((i) => (
                            <div key={i} className="space-y-2">
                                <Skeleton className="h-5 w-24" />
                                <div className="space-y-1">
                                    <Skeleton className="h-8 w-full" />
                                    <Skeleton className="h-8 w-full" />
                                    <Skeleton className="h-8 w-full" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center py-8 px-4">
                        <AlertCircle className="h-8 w-8 text-muted-foreground mb-3" />
                        <div className="text-center mb-4">
                            <h3 className="text-sm font-medium text-foreground mb-1">
                                Failed to load filters
                            </h3>
                            <p className="text-xs text-muted-foreground">
                                {error}
                            </p>
                        </div>
                        <Button
                            onClick={() => fetchFacets(true)}
                            size="sm"
                            variant="outline"
                            disabled={retrying}
                            className="w-full"
                        >
                            <RefreshCw className={cn("mr-2 h-3 w-3", retrying && "animate-spin")} />
                            {retrying ? "Retrying..." : "Retry"}
                        </Button>
                    </div>
                ) : facets.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
                        <Filter className="h-8 w-8 text-muted-foreground mb-3" />
                        <div>
                            <h3 className="text-sm font-medium text-foreground mb-1">
                                No filters available
                            </h3>
                            <p className="text-xs text-muted-foreground">
                                No data available to generate filter options
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-6">
                        {facets.map((group) => (
                            <div key={group.id}>
                                <button
                                    onClick={() => toggleFacet(group.id)}
                                    className="flex items-center justify-between w-full text-sm font-medium text-foreground mb-2 group hover:text-primary transition-colors"
                                >
                                    <span>{group.label}</span>
                                    <ChevronDown
                                        className={cn(
                                            "w-4 h-4 text-muted-foreground transition-transform duration-200",
                                            !openFacets[group.id] && "-rotate-90"
                                        )}
                                    />
                                </button>
                                {openFacets[group.id] && (
                                    <div className="space-y-1 animate-in slide-in-from-top-2 duration-200">
                                        {group.options.length === 0 ? (
                                            <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                                                No options available
                                            </div>
                                        ) : (
                                            group.options.map((opt) => {
                                                const isSelected =
                                                    (group.id === "service" && selectedFilters.service === opt.value) ||
                                                    (group.id === "level" && selectedFilters.level === opt.value) ||
                                                    (group.id === "cluster" && selectedFilters.cluster_id === Number(opt.value)) ||
                                                    (group.id === "anomaly" && selectedFilters.is_anomaly === (opt.value === "true"));

                                                return (
                                                    <button
                                                        key={opt.value}
                                                        onClick={() => toggleFilter(group.id, opt.value)}
                                                        className={cn(
                                                            "flex items-center justify-between w-full px-2 py-1.5 rounded-md text-sm transition-all duration-150",
                                                            isSelected
                                                                ? "bg-primary/10 text-primary font-medium"
                                                                : "hover:bg-muted/50 text-muted-foreground"
                                                        )}
                                                    >
                                                        <div className="flex items-center gap-x-2 flex-1 min-w-0">
                                                            <div className={cn(
                                                                "w-4 h-4 border rounded flex items-center justify-center shrink-0 transition-colors",
                                                                isSelected
                                                                    ? "border-primary bg-primary"
                                                                    : "border-input"
                                                            )}>
                                                                {isSelected && <Check className="h-3 w-3 text-primary-foreground" />}
                                                            </div>
                                                            <span className="truncate">{opt.label}</span>
                                                        </div>
                                                        <span className="text-xs text-muted-foreground/70 ml-2 shrink-0">
                                                            {opt.count}
                                                        </span>
                                                    </button>
                                                );
                                            })
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </ScrollArea>
        </div>
    );
}
