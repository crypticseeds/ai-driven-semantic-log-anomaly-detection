"use client";

import React, { useEffect, useState } from "react";
import { Wifi, WifiOff, AlertTriangle, Settings, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { getAppConfig, getEnvironmentInfo } from "@/lib/config";

type ConnectionStatus = 'connected' | 'disconnected' | 'checking' | 'error';

interface ConnectionStatusProps {
    className?: string;
    showText?: boolean;
    checkInterval?: number;
    showDiagnostics?: boolean;
}

export function ConnectionStatus({ 
    className, 
    showText = false, 
    checkInterval = 30000, // 30 seconds
    showDiagnostics = false
}: ConnectionStatusProps) {
    const [status, setStatus] = useState<ConnectionStatus>('checking');
    const [lastCheck, setLastCheck] = useState<Date | null>(null);
    const [corsInfo, setCorsInfo] = useState<any>(null);
    const [showDetails, setShowDetails] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const checkConnection = async () => {
        try {
            setStatus('checking');
            setError(null);
            
            await api.healthCheck();
            setStatus('connected');
            setLastCheck(new Date());
            
            // If connected and in development, also check CORS info
            if (process.env.NODE_ENV === 'development') {
                try {
                    const corsData = await api.corsCheck();
                    setCorsInfo(corsData);
                } catch (corsError) {
                    console.warn('[ConnectionStatus] CORS check failed:', corsError);
                }
            }
        } catch (err) {
            console.warn('Connection check failed:', err);
            setStatus('disconnected');
            setError(err instanceof Error ? err.message : 'Unknown error');
            setLastCheck(new Date());
        }
    };

    useEffect(() => {
        // Initial check
        checkConnection();

        // Set up periodic checks
        const interval = setInterval(checkConnection, checkInterval);

        return () => clearInterval(interval);
    }, [checkInterval]);

    const getStatusConfig = () => {
        switch (status) {
            case 'connected':
                return {
                    icon: Wifi,
                    color: 'text-green-500',
                    bgColor: 'bg-green-500/10',
                    text: 'Connected'
                };
            case 'disconnected':
                return {
                    icon: WifiOff,
                    color: 'text-red-500',
                    bgColor: 'bg-red-500/10',
                    text: 'Disconnected'
                };
            case 'checking':
                return {
                    icon: Wifi,
                    color: 'text-yellow-500',
                    bgColor: 'bg-yellow-500/10',
                    text: 'Checking...'
                };
            case 'error':
                return {
                    icon: AlertTriangle,
                    color: 'text-orange-500',
                    bgColor: 'bg-orange-500/10',
                    text: 'Error'
                };
        }
    };

    const config = getStatusConfig();
    const Icon = config.icon;
    const appConfig = getAppConfig();
    const envInfo = getEnvironmentInfo();

    return (
        <div className={cn("flex flex-col space-y-2", className)}>
            <div 
                className={cn(
                    "flex items-center gap-2 px-2 py-1 rounded-md transition-colors",
                    config.bgColor
                )}
                title={`Backend connection: ${config.text}${lastCheck ? ` (Last checked: ${lastCheck.toLocaleTimeString()})` : ''}`}
            >
                <Icon 
                    className={cn(
                        "h-4 w-4",
                        config.color,
                        status === 'checking' && "animate-pulse"
                    )} 
                />
                {showText && (
                    <span className={cn("text-xs font-medium", config.color)}>
                        {config.text}
                    </span>
                )}
                {error && status === 'disconnected' && (
                    <div title={error}>
                        <Info className="h-3 w-3 text-red-500 cursor-help" />
                    </div>
                )}
                {(showDiagnostics || appConfig.isDevelopment) && (
                    <button
                        onClick={() => setShowDetails(!showDetails)}
                        className="text-gray-500 hover:text-gray-700 transition-colors"
                        title="Show diagnostics"
                    >
                        <Settings className="h-3 w-3" />
                    </button>
                )}
            </div>
            
            {showDetails && (appConfig.isDevelopment || showDiagnostics) && (
                <div className="text-xs bg-gray-50 dark:bg-gray-800 p-3 rounded border space-y-2 max-w-md">
                    <div>
                        <strong className="text-gray-700 dark:text-gray-300">Configuration:</strong>
                        <div className="ml-2 space-y-1 text-gray-600 dark:text-gray-400">
                            <div>API URL: {appConfig.apiUrl}</div>
                            <div>Environment: {envInfo.nodeEnv}</div>
                            <div>Client: {envInfo.isClient ? 'Browser' : 'Server'}</div>
                            {envInfo.isClient && (
                                <>
                                    <div>Origin: {envInfo.protocol}{'//'}{envInfo.hostname}</div>
                                    <div>Protocol: {envInfo.protocol}</div>
                                </>
                            )}
                        </div>
                    </div>
                    
                    {corsInfo && (
                        <div>
                            <strong className="text-gray-700 dark:text-gray-300">CORS Status:</strong>
                            <div className="ml-2 space-y-1 text-gray-600 dark:text-gray-400">
                                <div>Origin Allowed: {corsInfo.origin_allowed ? '✅' : '❌'}</div>
                                <div>Request Origin: {corsInfo.request_origin || 'None'}</div>
                                <div>Debug Mode: {corsInfo.debug_mode ? 'Enabled' : 'Disabled'}</div>
                                {corsInfo.allowed_origins && (
                                    <div>Allowed Origins: {corsInfo.allowed_origins.join(', ')}</div>
                                )}
                            </div>
                        </div>
                    )}
                    
                    {error && (
                        <div>
                            <strong className="text-red-700 dark:text-red-300">Error Details:</strong>
                            <div className="ml-2 text-red-600 dark:text-red-400 break-words">{error}</div>
                        </div>
                    )}
                    
                    <div>
                        <strong className="text-gray-700 dark:text-gray-300">Troubleshooting:</strong>
                        <div className="ml-2 space-y-1 text-gray-600 dark:text-gray-400">
                            <div>• Check if backend is running on {appConfig.apiUrl}</div>
                            <div>• Verify CORS configuration allows your origin</div>
                            <div>• Check browser console for detailed errors</div>
                            <div>• Try accessing {appConfig.apiUrl}/health/cors directly</div>
                        </div>
                    </div>
                    
                    <div className="flex gap-2 pt-2">
                        <button
                            onClick={checkConnection}
                            className="text-xs bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600 transition-colors"
                            disabled={status === 'checking'}
                        >
                            Retry Connection
                        </button>
                        <button
                            onClick={() => window.open(`${appConfig.apiUrl}/health/cors`, '_blank')}
                            className="text-xs bg-gray-500 text-white px-2 py-1 rounded hover:bg-gray-600 transition-colors"
                        >
                            Open CORS Check
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

// Hook for components that need to react to connection status
export function useConnectionStatus(checkInterval = 30000) {
    const [status, setStatus] = useState<ConnectionStatus>('checking');
    const [isOnline, setIsOnline] = useState(true);

    useEffect(() => {
        const checkConnection = async () => {
            try {
                setStatus('checking');
                await api.healthCheck();
                setStatus('connected');
            } catch (error) {
                setStatus('disconnected');
            }
        };

        // Check browser online status
        const handleOnline = () => setIsOnline(true);
        const handleOffline = () => setIsOnline(false);

        window.addEventListener('online', handleOnline);
        window.addEventListener('offline', handleOffline);

        // Initial check
        checkConnection();

        // Periodic checks
        const interval = setInterval(checkConnection, checkInterval);

        return () => {
            clearInterval(interval);
            window.removeEventListener('online', handleOnline);
            window.removeEventListener('offline', handleOffline);
        };
    }, [checkInterval]);

    return {
        status,
        isOnline,
        isConnected: status === 'connected' && isOnline
    };
}