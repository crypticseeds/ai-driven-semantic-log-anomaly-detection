import { Inter } from "next/font/google";
import { cn } from "@/lib/utils";
import "./globals.css";
import React from "react";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

import { AppShell } from "@/components/layout/app-shell";

export const metadata = {
    title: "Semantic Log Analyzer",
    description: "AI-Driven Semantic Log Anomaly Detection",
};

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en" suppressHydrationWarning>
            <body
                className={cn(
                    "min-h-screen bg-background font-sans antialiased",
                    inter.variable
                )}
            >
                <AppShell>{children}</AppShell>
            </body>
        </html>
    );
}
