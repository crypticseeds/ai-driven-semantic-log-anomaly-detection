"use client";

import { useState } from "react";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Search, Loader2 } from "lucide-react";
import { api, LogEntry, APIError } from "@/lib/api";
import { LogRow } from "@/components/log-explorer/log-row";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertCircle } from "lucide-react";
import { Loading } from "@/components/ui/loading";

export default function SearchPage() {
    const [query, setQuery] = useState("");
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searched, setSearched] = useState(false);

    const handleSearch = async () => {
        if (!query.trim()) return;

        try {
            setLoading(true);
            setError(null);
            setSearched(true);
            const response = await api.searchLogs({
                query: query.trim(),
                limit: 100,
            });
            setLogs(response.logs || []);
        } catch (err) {
            const message = err instanceof APIError
                ? `Search failed: ${err.statusText}`
                : "Search failed. Please check your connection.";
            setError(message);
            console.error("Error searching logs:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
            handleSearch();
        }
    };

    return (
        <ErrorBoundary>
            <div className="space-y-6">
                <div>
                    <h2 className="text-2xl font-bold">Semantic Search</h2>
                    <p className="text-muted-foreground mt-1">
                        Search logs using natural language queries
                    </p>
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Search Logs</CardTitle>
                        <CardDescription>
                            Enter a natural language query to find semantically similar log entries
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="e.g., connection errors, authentication failures, database timeouts..."
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    onKeyPress={handleKeyPress}
                                    className="pl-10"
                                />
                            </div>
                            <Button
                                onClick={handleSearch}
                                disabled={loading || !query.trim()}
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Searching...
                                    </>
                                ) : (
                                    <>
                                        <Search className="mr-2 h-4 w-4" />
                                        Search
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

                {loading && (
                    <div className="flex items-center justify-center min-h-[200px]">
                        <Loading text="Searching logs..." />
                    </div>
                )}

                {!loading && searched && (
                    <Card>
                        <CardHeader>
                            <CardTitle>Search Results</CardTitle>
                            <CardDescription>
                                {logs.length} result{logs.length !== 1 ? "s" : ""} found
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="p-0">
                            {logs.length === 0 ? (
                                <div className="flex items-center justify-center h-64 text-center p-6">
                                    <div>
                                        <p className="text-muted-foreground font-medium">No results found</p>
                                        <p className="text-sm text-muted-foreground/70 mt-1">
                                            Try a different search query
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <ScrollArea className="h-[calc(100vh-24rem)]">
                                    <div>
                                        {logs.map(log => (
                                            <LogRow key={log.id} log={log} />
                                        ))}
                                    </div>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                )}

                {!searched && !loading && (
                    <Card>
                        <CardContent className="pt-6">
                            <div className="text-center text-muted-foreground py-12">
                                <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                <p>Enter a search query to find logs</p>
                            </div>
                        </CardContent>
                    </Card>
                )}
            </div>
        </ErrorBoundary>
    );
}

