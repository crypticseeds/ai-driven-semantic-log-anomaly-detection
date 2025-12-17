"use client";

import { FacetSidebar } from "@/components/log-explorer/facet-sidebar";
import { LogFeed } from "@/components/log-explorer/log-feed";
import { VolumeChart } from "@/components/log-explorer/volume-chart";
import { ConnectionStatus } from "@/components/ui/connection-status";
import { useState } from "react";
import { ErrorBoundary } from "@/components/ui/error-boundary";

export default function LogsPage() {
    const [filters, setFilters] = useState<{
        level?: string;
        service?: string;
        cluster_id?: number;
        is_anomaly?: boolean;
    }>({});

    return (
        <ErrorBoundary>
            <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
                <FacetSidebar selectedFilters={filters} onFilterChange={setFilters} />
                <div className="flex-1 flex flex-col min-w-0">
                    {/* Connection status bar */}
                    <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b border-border">
                        <div className="text-xs text-muted-foreground">
                            Log Explorer
                        </div>
                        <ConnectionStatus showText />
                    </div>
                    <VolumeChart />
                    <LogFeed filters={filters} />
                </div>
            </div>
        </ErrorBoundary>
    );
}
