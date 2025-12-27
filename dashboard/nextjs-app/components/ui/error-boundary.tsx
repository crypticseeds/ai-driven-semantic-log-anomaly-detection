"use client";

import { Component, ReactNode } from "react";
import { AlertCircle, RefreshCw, Wifi, WifiOff } from "lucide-react";
import { Button } from "./button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./card";

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
    onRetry?: () => void;
}

interface State {
    hasError: boolean;
    error: Error | null;
    retryCount: number;
}

export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null, retryCount: 0 };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error, retryCount: 0 };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        console.error("ErrorBoundary caught an error:", error, errorInfo);
        
        // Log additional context in development
        if (process.env.NODE_ENV === 'development') {
            console.error("Error details:", {
                message: error.message,
                stack: error.stack,
                componentStack: errorInfo.componentStack,
            });
        }
    }

    handleRetry = () => {
        this.setState(prevState => ({
            hasError: false,
            error: null,
            retryCount: prevState.retryCount + 1
        }));
        
        if (this.props.onRetry) {
            this.props.onRetry();
        } else {
            window.location.reload();
        }
    };

    getErrorType = (error: Error | null): 'network' | 'api' | 'render' | 'unknown' => {
        if (!error) return 'unknown';
        
        const message = error.message.toLowerCase();
        if (message.includes('network') || message.includes('fetch') || message.includes('cors')) {
            return 'network';
        }
        if (message.includes('api') || message.includes('response')) {
            return 'api';
        }
        if (message.includes('render') || message.includes('component')) {
            return 'render';
        }
        return 'unknown';
    };

    getErrorIcon = (errorType: string) => {
        switch (errorType) {
            case 'network':
                return <WifiOff className="h-5 w-5 text-destructive" />;
            case 'api':
                return <AlertCircle className="h-5 w-5 text-destructive" />;
            default:
                return <AlertCircle className="h-5 w-5 text-destructive" />;
        }
    };

    getErrorTitle = (errorType: string): string => {
        switch (errorType) {
            case 'network':
                return 'Connection Problem';
            case 'api':
                return 'Service Error';
            case 'render':
                return 'Display Error';
            default:
                return 'Something went wrong';
        }
    };

    getErrorDescription = (error: Error | null, errorType: string): string => {
        if (!error) return "An unexpected error occurred";
        
        switch (errorType) {
            case 'network':
                return "Unable to connect to the server. Please check your internet connection and try again.";
            case 'api':
                return "The service encountered an error. This might be temporary - please try again.";
            case 'render':
                return "There was a problem displaying this content. Refreshing the page may help.";
            default:
                return error.message || "An unexpected error occurred";
        }
    };

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            const errorType = this.getErrorType(this.state.error);
            const errorIcon = this.getErrorIcon(errorType);
            const errorTitle = this.getErrorTitle(errorType);
            const errorDescription = this.getErrorDescription(this.state.error, errorType);

            return (
                <div className="flex items-center justify-center min-h-[400px] p-6">
                    <Card className="max-w-md w-full">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                {errorIcon}
                                <CardTitle>{errorTitle}</CardTitle>
                            </div>
                            <CardDescription>
                                {errorDescription}
                            </CardDescription>
                            {this.state.retryCount > 0 && (
                                <div className="text-xs text-muted-foreground mt-2">
                                    Retry attempt: {this.state.retryCount}
                                </div>
                            )}
                        </CardHeader>
                        <CardContent className="space-y-2">
                            <Button
                                onClick={this.handleRetry}
                                className="w-full"
                                variant={this.state.retryCount > 2 ? "outline" : "default"}
                            >
                                <RefreshCw className="mr-2 h-4 w-4" />
                                {this.state.retryCount > 2 ? "Try Again" : "Retry"}
                            </Button>
                            
                            {process.env.NODE_ENV === 'development' && this.state.error && (
                                <details className="text-xs">
                                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                        Debug Info
                                    </summary>
                                    <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto max-h-32">
                                        {this.state.error.stack}
                                    </pre>
                                </details>
                            )}
                        </CardContent>
                    </Card>
                </div>
            );
        }

        return this.props.children;
    }
}

