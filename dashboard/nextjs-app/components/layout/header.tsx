"use client";

import { usePathname } from "next/navigation";
import { Activity, Wifi, WifiOff } from "lucide-react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

const pageTitles: Record<string, string> = {
    logs: "Logs",
    anomalies: "Anomalies",
    clustering: "Clusters",
    search: "Search",
    agent: "AI Agent",
    settings: "Settings",
};

export function Header() {
    const pathname = usePathname();
    const [isOnline, setIsOnline] = useState(true);
    const [isLive, setIsLive] = useState(true);

    useEffect(() => {
        setIsOnline(navigator.onLine);
        const handleOnline = () => setIsOnline(true);
        const handleOffline = () => setIsOnline(false);
        window.addEventListener("online", handleOnline);
        window.addEventListener("offline", handleOffline);
        return () => {
            window.removeEventListener("online", handleOnline);
            window.removeEventListener("offline", handleOffline);
        };
    }, []);

    const pageKey = pathname.split('/')[1] || "";
    const title = pageTitles[pageKey] || "Dashboard";

    return (
        <header className="flex h-14 md:h-16 items-center gap-x-4 border-b border-border bg-card/50 backdrop-blur-xl px-4 md:px-6 shadow-sm z-10 sticky top-0">
            <div className="flex flex-1 items-center justify-between">
                <div className="flex items-center gap-3">
                    <h1 className="text-lg md:text-xl font-semibold text-foreground">{title}</h1>
                    {isLive && (
                        <Badge variant="outline" className="gap-1.5 text-xs">
                            <Activity className="h-3 w-3 animate-pulse text-green-500" />
                            Live
                        </Badge>
                    )}
                </div>
                <div className="flex items-center gap-x-3">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        {isOnline ? (
                            <Wifi className="h-4 w-4 text-green-500" />
                        ) : (
                            <WifiOff className="h-4 w-4 text-destructive" />
                        )}
                        <span className="hidden sm:inline">{isOnline ? "Online" : "Offline"}</span>
                    </div>
                    <ThemeToggle />
                </div>
            </div>
        </header>
    );
}
