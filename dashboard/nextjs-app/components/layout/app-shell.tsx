"use client";

import { ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { Header } from "./header";
import { ErrorBoundary } from "@/components/ui/error-boundary";

interface AppShellProps {
    children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
    return (
        <ErrorBoundary>
            <div className="flex h-screen w-full bg-background overflow-hidden">
                <Sidebar />
                <div className="flex flex-col flex-1 min-w-0">
                    <Header />
                    <main className="flex-1 overflow-auto p-4 md:p-6 lg:p-8 relative">
                        {children}
                    </main>
                </div>
            </div>
        </ErrorBoundary>
    );
}
