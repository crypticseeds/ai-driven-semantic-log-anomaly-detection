"use client";

import { useState } from "react";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Bot, Send, Loader2, Sparkles } from "lucide-react";
import { api, APIError } from "@/lib/api";
import { AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function AgentPage() {
    const [logId, setLogId] = useState("");
    const [analysis, setAnalysis] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleAnalyze = async () => {
        if (!logId.trim()) return;

        try {
            setLoading(true);
            setError(null);
            setAnalysis(null);
            const result = await api.analyzeAnomaly(logId.trim());
            setAnalysis(result);
        } catch (err) {
            const message = err instanceof APIError
                ? `Analysis failed: ${err.statusText}`
                : "Analysis failed. Please check your connection.";
            setError(message);
            console.error("Error analyzing anomaly:", err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <ErrorBoundary>
            <div className="space-y-6">
                <div>
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <Bot className="h-6 w-6" />
                        AI Agent
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Get AI-powered root cause analysis and remediation guidance
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Analyze Anomaly</CardTitle>
                        <CardDescription>
                            Enter a log ID to get AI-powered analysis with root cause identification
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex gap-2">
                            <Input
                                placeholder="Enter log ID..."
                                value={logId}
                                onChange={(e) => setLogId(e.target.value)}
                                onKeyPress={(e) => {
                                    if (e.key === "Enter") {
                                        handleAnalyze();
                                    }
                                }}
                            />
                            <Button
                                onClick={handleAnalyze}
                                disabled={loading || !logId.trim()}
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Analyzing...
                                    </>
                                ) : (
                                    <>
                                        <Sparkles className="mr-2 h-4 w-4" />
                                        Analyze
                                    </>
                                )}
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {error && (
                    <Card className="border-destructive/50 bg-destructive/5">
                        <CardContent className="pt-6">
                            <div className="flex items-center gap-2 text-destructive">
                                <AlertCircle className="h-4 w-4" />
                                <span className="text-sm">{error}</span>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {analysis && (
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <CardTitle>Analysis Results</CardTitle>
                                {analysis.severity && (
                                    <Badge
                                        variant={
                                            analysis.severity === "CRITICAL" ? "destructive" :
                                            analysis.severity === "HIGH" ? "destructive" :
                                            analysis.severity === "MEDIUM" ? "default" : "secondary"
                                        }
                                    >
                                        {analysis.severity}
                                    </Badge>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {analysis.root_cause && (
                                <div>
                                    <h4 className="font-semibold mb-2">Root Cause</h4>
                                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                                        {analysis.root_cause}
                                    </p>
                                </div>
                            )}

                            {analysis.confidence_score !== undefined && (
                                <div>
                                    <h4 className="font-semibold mb-2">Confidence</h4>
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1 bg-muted rounded-full h-2">
                                            <div
                                                className="bg-primary h-2 rounded-full transition-all"
                                                style={{ width: `${analysis.confidence_score * 100}%` }}
                                            />
                                        </div>
                                        <span className="text-sm text-muted-foreground">
                                            {(analysis.confidence_score * 100).toFixed(1)}%
                                        </span>
                                    </div>
                                </div>
                            )}

                            {analysis.remediation_steps && analysis.remediation_steps.length > 0 && (
                                <div>
                                    <h4 className="font-semibold mb-2">Remediation Steps</h4>
                                    <ol className="list-decimal list-inside space-y-1 text-sm text-muted-foreground">
                                        {analysis.remediation_steps.map((step: string, idx: number) => (
                                            <li key={idx}>{step}</li>
                                        ))}
                                    </ol>
                                </div>
                            )}

                            {analysis.raw_response && (
                                <div>
                                    <h4 className="font-semibold mb-2">Raw Response</h4>
                                    <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">
                                        {JSON.stringify(analysis, null, 2)}
                                    </pre>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}

                {!analysis && !loading && !error && (
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-center text-muted-foreground py-12">
                                <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                <p>Enter a log ID to start analysis</p>
                            </div>
                        </CardContent>
                    </Card>
                )}
            </div>
        </ErrorBoundary>
    );
}

