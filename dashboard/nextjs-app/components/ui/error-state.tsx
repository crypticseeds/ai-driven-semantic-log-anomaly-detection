"use client";

import React from "react";
import { AlertCircle, RefreshCw, WifiOff, Server, Database, Clock } from "lucide-react";
import { Button } from "./button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./card";
import { cn } from "@/lib/utils";

export type ErrorType = 'network' | 'api' | 'timeout' | 'server' | 'data' | 'unknown';

interface ErrorStateProps {
    error: Error | string | null;
    errorType?: ErrorType;
    title?: string;
    description?: string;
    onRetry?: () => void;
    retryLabel?: string;
    retrying?: boolean;
    className?: string;
    compact?: boolean;
    showDetails?: boolean;
}

const errorConfig = {
    network: {
        icon: WifiOff,
        title: "Connection Problem",
        description: "Unable to connect to the server. Please check your internet connection.",
        color: "text-orange-500"
    },
    api: {
        icon: AlertCircle,
        title: "Service Error",
        description: "The service encountered an error. This might be temporary.",
        color: "text-red-500"
    },
    timeout: {
        icon: Clock,
        title: "Request Timeout",
        description: "The request took too long to complete. Please try again.",
        color: "text-yellow-500"
    },
    server: {
        icon: Server,
        title: "Server Error",
        description: "The server is experiencing issues. Please try again later.",
        color: "text-red-500"
    },
    data: {
        icon: Database,
        title: "Data Error",
        description: "There was a problem processing the data.",
        color: "text-blue-500"
    },
    unknown: {
        icon: AlertCircle,
        title: "Something went wrong",
        description: "An unexpected error occurred.",
        color: "text-gray-500"
    }
};

function getErrorType(error: Error | string | null): ErrorType {
    if (!error) return 'unknown';
    
    const message = typeof error === 'string' ? error : error.message;
    const lowerMessage = message.toLowerCase();
    
    if (lowerMessage.includes('network') || lowerMessage.includes('fetch') || lowerMessage.includes('cors') || lowerMessage.includes('connection')) {
        return 'network';
    }
    if (lowerMessage.includes('timeout') || lowerMessage.includes('timed out')) {
        return 'timeout';
    }
    if (lowerMessage.includes('server') || lowerMessage.includes('5')) {
        return 'server';
    }
    if (lowerMessage.includes('api') || lowerMessage.includes('response') || lowerMessage.includes('4')) {
        return 'api';
    }
    if (lowerMessage.includes('data') || lowerMessage.includes('format') || lowerMessage.includes('parse')) {
        return 'data';
    }
    
    return 'unknown';
}

export function ErrorState({
    error,
    errorType,
    title,
    description,
    onRetry,
    retryLabel = "Try Again",
    retrying = false,
    className,
    compact = false,
    showDetails = process.env.NODE_ENV === 'development'
}: ErrorStateProps) {
    const detectedType = errorType || getErrorType(error);
    const config = errorConfig[detectedType];
    const Icon = config.icon;
    
    const errorMessage = typeof error === 'string' ? error : error?.message;
    const finalTitle = title || config.title;
    const finalDescription = description || config.description;

    if (compact) {
        return (
            <div className={cn("flex items-center justify-center p-4 text-center", className)}>
                <div className="flex flex-col items-center gap-2 max-w-sm">
                    <Icon className={cn("h-8 w-8", config.color)} />
                    <div>
                        <h3 className="font-medium text-sm">{finalTitle}</h3>
                        <p className="text-xs text-muted-foreground mt-1">{finalDescription}</p>
                        {errorMessage && errorMessage !== finalDescription && (
                            <p className="text-xs text-muted-foreground/70 mt-1">{errorMessage}</p>
                        )}
                    </div>
                    {onRetry && (
                        <Button 
                            onClick={onRetry} 
                            size="sm" 
                            variant="outline"
                            disabled={retrying}
                            className="mt-1"
                        >
                            <RefreshCw className={cn("mr-1 h-3 w-3", retrying && "animate-spin")} />
                            {retryLabel}
                        </Button>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div className={cn("flex items-center justify-center p-6", className)}>
            <Card className="max-w-md w-full">
                <CardHeader>
                    <div className="flex items-center gap-2">
                        <Icon className={cn("h-5 w-5", config.color)} />
                        <CardTitle className="text-base">{finalTitle}</CardTitle>
                    </div>
                    <CardDescription>
                        {finalDescription}
                        {errorMessage && errorMessage !== finalDescription && (
                            <span className="block mt-1 text-xs opacity-75">{errorMessage}</span>
                        )}
                    </CardDescription>
                </CardHeader>
                {(onRetry || showDetails) && (
                    <CardContent className="space-y-3">
                        {onRetry && (
                            <Button
                                onClick={onRetry}
                                className="w-full"
                                disabled={retrying}
                            >
                                <RefreshCw className={cn("mr-2 h-4 w-4", retrying && "animate-spin")} />
                                {retrying ? "Retrying..." : retryLabel}
                            </Button>
                        )}
                        
                        {showDetails && error instanceof Error && error.stack && (
                            <details className="text-xs">
                                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                    Debug Details
                                </summary>
                                <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto max-h-32 whitespace-pre-wrap">
                                    {error.stack}
                                </pre>
                            </details>
                        )}
                    </CardContent>
                )}
            </Card>
        </div>
    );
}

// Specialized error components for common use cases
export function NetworkError({ onRetry, retrying }: { onRetry?: () => void; retrying?: boolean }) {
    return (
        <ErrorState
            error="Unable to connect to the server"
            errorType="network"
            onRetry={onRetry}
            retrying={retrying}
            compact
        />
    );
}

export function APIError({ error, onRetry, retrying }: { error: Error | string; onRetry?: () => void; retrying?: boolean }) {
    return (
        <ErrorState
            error={error}
            errorType="api"
            onRetry={onRetry}
            retrying={retrying}
            compact
        />
    );
}

export function DataError({ error, onRetry }: { error: Error | string; onRetry?: () => void }) {
    return (
        <ErrorState
            error={error}
            errorType="data"
            onRetry={onRetry}
            compact
        />
    );
}