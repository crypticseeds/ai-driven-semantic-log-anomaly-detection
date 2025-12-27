"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    BarChart3,
    LayoutDashboard,
    List,
    Settings,
    ShieldAlert,
    Search
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
    { name: "Logs", href: "/logs", icon: List },
    { name: "Anomalies", href: "/anomalies", icon: ShieldAlert },
    { name: "Clusters", href: "/clustering", icon: BarChart3 },
    { name: "Search", href: "/search", icon: Search },
];

const secondaryNavigation = [
    { name: "Agent", href: "/agent", icon: LayoutDashboard }, // Placeholder for chat
    { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <div className="flex flex-col w-16 md:w-64 border-r border-border bg-card/50 backdrop-blur-xl h-full transition-all duration-300">
            <div className="flex items-center justify-center md:justify-start h-14 md:h-16 px-0 md:px-6 border-b border-border">
                <span className="hidden md:block font-bold text-lg tracking-tight text-primary">
                    LogSentinel
                </span>
                <span className="md:hidden font-bold text-lg text-primary">LS</span>
            </div>

            <nav className="flex-1 flex flex-col gap-y-4 pt-4 px-2 md:px-4">
                <div className="space-y-1">
                    {navigation.map((item) => {
                        const isActive = pathname.startsWith(item.href);
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                className={cn(
                                    "flex items-center gap-x-3 px-3 py-2 text-sm font-medium rounded-md transition-all duration-200 relative group",
                                    isActive
                                        ? "bg-primary/10 text-primary shadow-sm"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                <item.icon className={cn(
                                    "h-5 w-5 shrink-0 transition-transform duration-200",
                                    isActive && "scale-110"
                                )} />
                                <span className="hidden md:block">{item.name}</span>
                                {isActive && (
                                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-primary rounded-r-full" />
                                )}
                            </Link>
                        );
                    })}
                </div>

                <div className="mt-auto pb-4 space-y-1">
                    <div className="px-3 mb-2 hidden md:block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        Tools
                    </div>
                    {secondaryNavigation.map((item) => {
                        const isActive = pathname.startsWith(item.href);
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                className={cn(
                                    "flex items-center gap-x-3 px-3 py-2 text-sm font-medium rounded-md transition-all duration-200 relative group",
                                    isActive
                                        ? "bg-primary/10 text-primary shadow-sm"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                <item.icon className={cn(
                                    "h-5 w-5 shrink-0 transition-transform duration-200",
                                    isActive && "scale-110"
                                )} />
                                <span className="hidden md:block">{item.name}</span>
                                {isActive && (
                                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-primary rounded-r-full" />
                                )}
                            </Link>
                        );
                    })}
                </div>
            </nav>
        </div>
    );
}
