"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings as SettingsIcon, Database, Zap, Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { getAppConfig } from "@/lib/config";

function useConnectionStatus() {
    const [isConnected, setIsConnected] = useState<boolean | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const checkConnection = async () => {
            try {
                setLoading(true);
                // Use the existing api.healthCheck() helper for consistent request handling
                const response = await api.healthCheck();
                setIsConnected(response.status === 'healthy');
            } catch (error) {
                console.error('Connection check failed:', error);
                setIsConnected(false);
            } finally {
                setLoading(false);
            }
        };

        checkConnection();
        
        // Check connection every 30 seconds
        const interval = setInterval(checkConnection, 30000);
        return () => clearInterval(interval);
    }, []);

    return { isConnected, loading };
}

export default function SettingsPage() {
    const { isConnected, loading } = useConnectionStatus();
    const config = getAppConfig();

    const getStatusBadge = () => {
        if (loading) {
            return (
                <Badge variant="outline" className="bg-yellow-500/10 text-yellow-600 dark:text-yellow-400">
                    Checking...
                </Badge>
            );
        }
        
        if (isConnected) {
            return (
                <Badge variant="outline" className="bg-green-500/10 text-green-600 dark:text-green-400">
                    Connected
                </Badge>
            );
        }
        
        return (
            <Badge variant="outline" className="bg-red-500/10 text-red-600 dark:text-red-400">
                Disconnected
            </Badge>
        );
    };
    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-2xl font-bold flex items-center gap-2">
                    <SettingsIcon className="h-6 w-6" />
                    Settings
                </h2>
                <p className="text-muted-foreground mt-1">
                    Configure dashboard preferences and system settings
                </p>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <div className="flex items-center gap-2">
                            <Database className="h-5 w-5" />
                            <CardTitle>Data Source</CardTitle>
                        </div>
                        <CardDescription>Backend API configuration</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground">API URL</span>
                            <Badge variant="outline">
                                {config.apiUrl}
                            </Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground">Status</span>
                            {getStatusBadge()}
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div className="flex items-center gap-2">
                            <Zap className="h-5 w-5" />
                            <CardTitle>Features</CardTitle>
                        </div>
                        <CardDescription>Enabled system features</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="text-sm">PII Protection</span>
                            <Badge variant="outline" className="bg-green-500/10 text-green-600 dark:text-green-400">
                                <Shield className="h-3 w-3 mr-1" />
                                Active
                            </Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm">Anomaly Detection</span>
                            <Badge variant="outline">Enabled</Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm">Clustering</span>
                            <Badge variant="outline">Enabled</Badge>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm">AI Agent</span>
                            <Badge variant="outline">Enabled</Badge>
                        </div>
                    </CardContent>
                </Card>

                <Card className="md:col-span-2">
                    <CardHeader>
                        <CardTitle>About</CardTitle>
                        <CardDescription>System information</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground">Version</span>
                            <span className="text-sm font-mono">0.1.0</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-muted-foreground">Environment</span>
                            <Badge variant="outline">
                                {process.env.NODE_ENV || "development"}
                            </Badge>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

