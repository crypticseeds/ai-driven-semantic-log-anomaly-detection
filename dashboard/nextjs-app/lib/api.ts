/**
 * API client utilities for backend communication
 */

import { getAppConfig, validateConfig } from './config';

// Use the new configuration system - initialize before validateApiConfig
const appConfig = getAppConfig();
export const API_BASE_URL = appConfig.apiUrl;
const API_VERSION = 'v1';

/**
 * Validate API configuration and log diagnostics
 */
const validateApiConfig = (url: string) => {
    const isDevelopment = process.env.NODE_ENV === 'development';
    
    if (isDevelopment) {
        console.log('[API Config] Configuration Summary:', {
            apiBaseUrl: url,
            envVariable: process.env.NEXT_PUBLIC_API_URL || 'not set',
            isClient: typeof window !== 'undefined',
            hostname: typeof window !== 'undefined' ? window.location.hostname : 'server-side',
            protocol: typeof window !== 'undefined' ? window.location.protocol : 'N/A'
        });
        
        // Validate URL format
        try {
            new URL(url);
        } catch (error) {
            console.error('[API Config] Invalid API URL format:', url, error);
        }
        
        // Check for common misconfigurations
        if (url.endsWith('/')) {
            console.warn('[API Config] API URL should not end with slash:', url);
        }
        
        if (typeof window !== 'undefined' && window.location.protocol === 'https:' && url.startsWith('http:')) {
            console.warn('[API Config] Mixed content warning: HTTPS frontend trying to access HTTP backend');
        }
    }
};

// Validate configuration on module load
validateApiConfig(API_BASE_URL);
validateConfig();

export class APIError extends Error {
    constructor(
        public status: number,
        public statusText: string,
        public data?: any
    ) {
        super(`API Error: ${status} ${statusText}`);
        this.name = 'APIError';
    }
}

/**
 * Check if an error is retryable (network issues, 5xx errors)
 */
function isRetryableError(error: unknown): boolean {
    if (error instanceof APIError) {
        // Retry on server errors (5xx) but not client errors (4xx)
        return error.status >= 500;
    }
    
    if (error instanceof Error) {
        // Retry on network errors
        return error.message.includes('Network error') || 
               error.message.includes('fetch') ||
               error.message.includes('Unable to connect');
    }
    
    return false;
}

/**
 * Validate and provide detailed information about response structure
 */
function validateResponseStructure(response: any, expectedFields: string[]): { isValid: boolean; issues: string[] } {
    const issues: string[] = [];
    
    if (!response || typeof response !== 'object') {
        issues.push(`Expected object, got ${typeof response}`);
        return { isValid: false, issues };
    }
    
    expectedFields.forEach(field => {
        if (!(field in response)) {
            issues.push(`Missing required field: ${field}`);
        }
    });
    
    // Check for common alternative field names
    if (!('results' in response) && ('logs' in response)) {
        issues.push('Found "logs" field instead of expected "results" field');
    }
    
    if ('results' in response && !Array.isArray(response.results)) {
        issues.push(`Field "results" should be array, got ${typeof response.results}`);
    }
    
    return { isValid: issues.length === 0, issues };
}

/**
 * Sleep for a given number of milliseconds
 */
function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry a function with exponential backoff
 */
async function withRetry<T>(
    fn: () => Promise<T>,
    maxRetries: number = 2,
    baseDelay: number = 1000
): Promise<T> {
    let lastError: unknown;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            return await fn();
        } catch (error) {
            lastError = error;
            
            // Don't retry on the last attempt or if error is not retryable
            if (attempt === maxRetries || !isRetryableError(error)) {
                throw error;
            }
            
            // Exponential backoff: 1s, 2s, 4s, etc.
            const delay = baseDelay * Math.pow(2, attempt);
            
            if (process.env.NODE_ENV === 'development') {
                console.log(`[API] Retrying in ${delay}ms (attempt ${attempt + 1}/${maxRetries + 1})`);
            }
            
            await sleep(delay);
        }
    }
    
    throw lastError;
}

async function fetchAPI<T>(
    endpoint: string,
    options?: RequestInit
): Promise<T> {
    const url = `${API_BASE_URL}/api/${API_VERSION}${endpoint}`;
    const isDevelopment = process.env.NODE_ENV === 'development';
    const requestId = `req-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    const startTime = performance.now();

    if (isDevelopment) {
        console.log(`[API] ${options?.method || 'GET'} ${url} - Request ID: ${requestId}`);
        
        // Log request details in development
        if (options?.body) {
            console.log(`[API] Request body:`, options.body);
        }
        if (options?.headers) {
            console.log(`[API] Request headers:`, options.headers);
        }
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-Debug-Mode': isDevelopment ? 'true' : 'false',
                'X-Request-ID': requestId,
                'X-Client-Version': '1.0.0',
                'X-Timestamp': new Date().toISOString(),
                ...options?.headers,
            },
        });

        const responseTime = performance.now() - startTime;

        if (isDevelopment) {
            console.log(`[API] Response: ${response.status} ${response.statusText} - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}`);
            
            // Log response headers in development
            const responseHeaders: Record<string, string> = {};
            response.headers.forEach((value, key) => {
                responseHeaders[key] = value;
            });
            console.log(`[API] Response headers:`, responseHeaders);
            
            // Log CORS debug headers if present
            const corsDebug = response.headers.get('X-CORS-Debug');
            const debugInfo = response.headers.get('X-Debug-Info');
            const originAllowed = response.headers.get('X-Origin-Allowed');
            
            if (corsDebug || debugInfo) {
                console.log('[API] CORS Debug Info:', {
                    corsDebug,
                    debugInfo,
                    originAllowed,
                    requestId,
                    responseTime: `${responseTime.toFixed(2)}ms`
                });
            }
        }

        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
            } catch {
                errorData = { detail: response.statusText };
            }
            
            if (isDevelopment) {
                console.error(`[API] Error response - Request ID: ${requestId}:`, {
                    status: response.status,
                    statusText: response.statusText,
                    errorData,
                    responseTime: `${responseTime.toFixed(2)}ms`,
                    url
                });
            }
            
            throw new APIError(
                response.status,
                response.statusText,
                {
                    ...errorData,
                    requestId,
                    responseTime,
                    endpoint
                }
            );
        }

        // Handle empty responses
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            if (isDevelopment) {
                console.warn(`[API] Non-JSON response - Request ID: ${requestId}, content-type: ${contentType}`);
            }
            return {} as T;
        }

        const data = await response.json();
        
        if (isDevelopment) {
            console.log(`[API] Response data - Request ID: ${requestId}:`, {
                dataType: typeof data,
                dataKeys: data && typeof data === 'object' ? Object.keys(data) : 'not object',
                responseTime: `${responseTime.toFixed(2)}ms`
            });
            
            // Validate response structure for log search endpoints
            if (endpoint.includes('/logs/search')) {
                const validation = validateResponseStructure(data, ['results', 'total', 'limit', 'offset']);
                if (!validation.isValid) {
                    console.warn(`[API] Response structure issues - Request ID: ${requestId}:`, validation.issues);
                }
            }
            
            // Log performance metrics
            if (responseTime > 1000) {
                console.warn(`[API] Slow response - Request ID: ${requestId}: ${responseTime.toFixed(2)}ms`);
            }
        }
        
        // Validate response structure
        if (data === null || data === undefined) {
            throw new Error(`Received null or undefined response from server - Request ID: ${requestId}`);
        }

        return data;
    } catch (error) {
        const responseTime = performance.now() - startTime;
        
        if (isDevelopment) {
            console.error(`[API] Request failed - Request ID: ${requestId} - ${responseTime.toFixed(2)}ms:`, {
                error: error instanceof Error ? error.message : error,
                url,
                endpoint,
                method: options?.method || 'GET',
                responseTime: `${responseTime.toFixed(2)}ms`
            });
        }
        
        if (error instanceof APIError) {
            throw error;
        }
        
        // Enhanced network error handling with CORS diagnostics
        if (error instanceof TypeError && error.message.includes('fetch')) {
            const corsError = new Error(`Network error: Unable to connect to ${API_BASE_URL}. This is likely a CORS or connectivity issue. Request ID: ${requestId}`);
            
            if (isDevelopment) {
                console.error(`[API] Network Error Details - Request ID: ${requestId}:`, {
                    url,
                    apiBaseUrl: API_BASE_URL,
                    origin: typeof window !== 'undefined' ? window.location.origin : 'server-side',
                    error: error.message,
                    responseTime: `${responseTime.toFixed(2)}ms`,
                    suggestions: [
                        'Check if backend is running on the expected port',
                        'Verify CORS configuration allows your origin',
                        'Check browser developer tools for specific CORS errors',
                        'Try accessing the CORS diagnostic endpoint: /health/cors'
                    ]
                });
            }
            
            throw corsError;
        }
        
        if (error instanceof Error && error.message.includes('Failed to fetch')) {
            const networkError = new Error(`Network error: Connection failed to ${API_BASE_URL}. This could be due to CORS issues, network connectivity, or the backend being offline. Request ID: ${requestId}`);
            
            if (isDevelopment) {
                console.error(`[API] Connection Failed - Request ID: ${requestId}:`, {
                    url,
                    apiBaseUrl: API_BASE_URL,
                    responseTime: `${responseTime.toFixed(2)}ms`,
                    possibleCauses: [
                        'Backend server is not running',
                        'CORS policy blocking the request',
                        'Network connectivity issues',
                        'Firewall blocking the connection',
                        'Wrong API URL configuration'
                    ]
                });
            }
            
            throw networkError;
        }
        
        throw new Error(`Network error: ${error instanceof Error ? error.message : 'Unknown error'} - Request ID: ${requestId}`);
    }
}

// Log Entry Types
export interface LogEntry {
    id: string;
    timestamp: string;
    level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' | 'FATAL';
    message: string;
    service: string;
    cluster_id?: number;
    anomaly_score?: number;
    is_anomaly?: boolean;
    metadata?: Record<string, any>;
    redacted_message?: string;
    pii_entities?: Record<string, number>;
}

export interface LogSearchParams {
    query?: string;
    level?: string;
    service?: string;
    cluster_id?: number;
    is_anomaly?: boolean;
    limit?: number;
    offset?: number;
    start_time?: string;
    end_time?: string;
}

export interface LogSearchResponse {
    logs: LogEntry[];
    total: number;
    limit: number;
    offset: number;
}

// Backend response format (what the API actually returns)
interface BackendLogSearchResponse {
    results: LogEntry[];
    total: number;
    limit: number;
    offset: number;
    has_more?: boolean;
    search_type?: string;
}

/**
 * Transform backend response format to frontend expected format
 */
function transformLogSearchResponse(backendResponse: BackendLogSearchResponse): LogSearchResponse {
    // Validate that the response has the expected structure
    if (!backendResponse || typeof backendResponse !== 'object') {
        throw new Error('Invalid response format: expected object, received: ' + typeof backendResponse);
    }

    // Handle case where backend returns different field names or structure
    if (!Array.isArray(backendResponse.results)) {
        // Check if response has 'logs' field instead (for backward compatibility)
        if (Array.isArray((backendResponse as any).logs)) {
            console.warn('[API] Backend returned logs field instead of results, using logs field');
            backendResponse.results = (backendResponse as any).logs;
        } else {
            throw new Error('Invalid response format: results field must be an array, received: ' + typeof backendResponse.results);
        }
    }

    // Validate numeric fields with defaults
    const total = typeof backendResponse.total === 'number' ? backendResponse.total : 0;
    const limit = typeof backendResponse.limit === 'number' ? backendResponse.limit : 100;
    const offset = typeof backendResponse.offset === 'number' ? backendResponse.offset : 0;

    if (typeof backendResponse.total !== 'number') {
        console.warn('[API] Invalid total field, using default: 0');
    }
    if (typeof backendResponse.limit !== 'number') {
        console.warn('[API] Invalid limit field, using default: 100');
    }
    if (typeof backendResponse.offset !== 'number') {
        console.warn('[API] Invalid offset field, using default: 0');
    }

    // Validate and sanitize each log entry
    const validatedLogs: LogEntry[] = [];
    backendResponse.results.forEach((log, index) => {
        try {
            if (!log || typeof log !== 'object') {
                console.warn(`[API] Skipping invalid log entry at index ${index}: expected object, got ${typeof log}`);
                return;
            }

            // Validate required fields with fallbacks
            const id = log.id && typeof log.id === 'string' ? log.id : `unknown-${index}`;
            const timestamp = log.timestamp && typeof log.timestamp === 'string' ? log.timestamp : new Date().toISOString();
            const level = log.level && typeof log.level === 'string' ? log.level as LogEntry['level'] : 'INFO';
            const service = log.service && typeof log.service === 'string' ? log.service : 'unknown';
            const message = log.message && typeof log.message === 'string' ? log.message : '';

            // Warn about missing or invalid required fields
            if (!log.id || typeof log.id !== 'string') {
                console.warn(`[API] Log entry at index ${index} missing valid id field, using fallback: ${id}`);
            }
            if (!log.timestamp || typeof log.timestamp !== 'string') {
                console.warn(`[API] Log entry at index ${index} missing valid timestamp field, using current time`);
            }
            if (!log.level || typeof log.level !== 'string') {
                console.warn(`[API] Log entry at index ${index} missing valid level field, using INFO`);
            }
            if (!log.service || typeof log.service !== 'string') {
                console.warn(`[API] Log entry at index ${index} missing valid service field, using 'unknown'`);
            }
            if (!log.message || typeof log.message !== 'string') {
                console.warn(`[API] Log entry at index ${index} missing valid message field, using empty string`);
            }

            // Create validated log entry
            const validatedLog: LogEntry = {
                id,
                timestamp,
                level,
                service,
                message,
                cluster_id: typeof log.cluster_id === 'number' ? log.cluster_id : undefined,
                anomaly_score: typeof log.anomaly_score === 'number' ? log.anomaly_score : undefined,
                is_anomaly: typeof log.is_anomaly === 'boolean' ? log.is_anomaly : undefined,
                metadata: log.metadata && typeof log.metadata === 'object' ? log.metadata : undefined,
                redacted_message: log.redacted_message && typeof log.redacted_message === 'string' ? log.redacted_message : undefined,
                pii_entities: log.pii_entities && typeof log.pii_entities === 'object' ? log.pii_entities : undefined,
            };

            validatedLogs.push(validatedLog);
        } catch (error) {
            console.warn(`[API] Error validating log entry at index ${index}:`, error);
            // Skip invalid entries rather than failing the entire response
        }
    });

    // Transform the response
    return {
        logs: validatedLogs,
        total,
        limit,
        offset,
    };
}

export interface Cluster {
    cluster_id: number;
    count: number;
    sample_logs: LogEntry[];
}

export interface AnomalyDetectionResult {
    log_id: string;
    is_anomaly: boolean;
    score: number;
    method: string;
}

export interface VolumeData {
    timestamp: string;
    count: number;
    level_breakdown?: {
        ERROR: number;
        WARN: number;
        INFO: number;
        DEBUG: number;
    };
}

export interface VolumeResponse {
    volume_data: VolumeData[];
    total_logs: number;
    time_range: {
        start_time: string;
        end_time: string;
        hours: number;
        bucket_minutes: number;
    };
    filters: {
        level?: string;
        service?: string;
    };
}

// API Functions
export const api = {
    // Health Check with enhanced monitoring
    async healthCheck(): Promise<{ status: string; timestamp: string; responseTime?: number; details?: any }> {
        const startTime = performance.now();
        const requestId = `health-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
        
        try {
            if (process.env.NODE_ENV === 'development') {
                console.log(`[API] Health check started - Request ID: ${requestId}`);
            }
            
            // Try a simple endpoint first
            const response = await fetch(`${API_BASE_URL}/health`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-Request-ID': requestId,
                },
            });
            
            const responseTime = performance.now() - startTime;
            
            if (response.ok) {
                const data = await response.json();
                
                if (process.env.NODE_ENV === 'development') {
                    console.log(`[API] Health check successful - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}`);
                }
                
                return {
                    status: 'healthy',
                    timestamp: new Date().toISOString(),
                    responseTime,
                    details: data
                };
            } else {
                const errorMessage = `Health check failed: ${response.status} ${response.statusText}`;
                
                if (process.env.NODE_ENV === 'development') {
                    console.error(`[API] Health check failed - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}`, {
                        status: response.status,
                        statusText: response.statusText,
                        headers: (() => {
                            const headers: Record<string, string> = {};
                            response.headers.forEach((value, key) => {
                                headers[key] = value;
                            });
                            return headers;
                        })()
                    });
                }
                
                throw new Error(errorMessage);
            }
        } catch (error) {
            const responseTime = performance.now() - startTime;
            const errorMessage = `Backend unreachable: ${error instanceof Error ? error.message : 'Unknown error'}`;
            
            if (process.env.NODE_ENV === 'development') {
                console.error(`[API] Health check error - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}`, {
                    error: error instanceof Error ? error.message : error,
                    apiUrl: API_BASE_URL,
                    responseTime
                });
            }
            
            throw new Error(errorMessage);
        }
    },

    // CORS Diagnostics with enhanced monitoring
    async corsCheck(): Promise<any> {
        const startTime = performance.now();
        const requestId = `cors-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
        
        try {
            if (process.env.NODE_ENV === 'development') {
                console.log(`[API] CORS diagnostic started - Request ID: ${requestId}`);
            }
            
            const response = await fetch(`${API_BASE_URL}/health/cors`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-Debug-Mode': process.env.NODE_ENV === 'development' ? 'true' : 'false',
                    'X-Request-ID': requestId,
                },
            });
            
            const responseTime = performance.now() - startTime;
            
            if (response.ok) {
                const data = await response.json();
                
                if (process.env.NODE_ENV === 'development') {
                    console.log(`[API] CORS Diagnostic Results - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}:`, data);
                }
                
                return {
                    ...data,
                    requestId,
                    responseTime
                };
            } else {
                const errorMessage = `CORS check failed: ${response.status} ${response.statusText}`;
                
                if (process.env.NODE_ENV === 'development') {
                    console.error(`[API] CORS check failed - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}`, {
                        status: response.status,
                        statusText: response.statusText
                    });
                }
                
                throw new Error(errorMessage);
            }
        } catch (error) {
            const responseTime = performance.now() - startTime;
            
            if (process.env.NODE_ENV === 'development') {
                console.error(`[API] CORS Check Error - ${responseTime.toFixed(2)}ms - Request ID: ${requestId}:`, error);
            }
            throw new Error(`CORS diagnostic failed: ${error instanceof Error ? error.message : 'Unknown error'} - Request ID: ${requestId}`);
        }
    },

    // API Performance and Connectivity Monitoring
    async performanceCheck(): Promise<{
        health: { status: string; responseTime: number };
        cors: { status: string; responseTime: number };
        connectivity: { status: string; details: string };
        overall: { status: 'healthy' | 'degraded' | 'unhealthy'; score: number };
    }> {
        const results = {
            health: { status: 'unknown', responseTime: 0 },
            cors: { status: 'unknown', responseTime: 0 },
            connectivity: { status: 'unknown', details: '' },
            overall: { status: 'unhealthy' as 'healthy' | 'degraded' | 'unhealthy', score: 0 }
        };

        try {
            // Test basic health endpoint
            const healthStart = performance.now();
            try {
                await this.healthCheck();
                results.health = {
                    status: 'healthy',
                    responseTime: performance.now() - healthStart
                };
            } catch (error) {
                results.health = {
                    status: 'unhealthy',
                    responseTime: performance.now() - healthStart
                };
            }

            // Test CORS configuration
            const corsStart = performance.now();
            try {
                await this.corsCheck();
                results.cors = {
                    status: 'healthy',
                    responseTime: performance.now() - corsStart
                };
            } catch (error) {
                results.cors = {
                    status: 'unhealthy',
                    responseTime: performance.now() - corsStart
                };
            }

            // Determine connectivity status
            if (results.health.status === 'healthy' && results.cors.status === 'healthy') {
                results.connectivity = {
                    status: 'healthy',
                    details: 'All endpoints accessible'
                };
            } else if (results.health.status === 'healthy') {
                results.connectivity = {
                    status: 'degraded',
                    details: 'Basic connectivity works, CORS issues detected'
                };
            } else {
                results.connectivity = {
                    status: 'unhealthy',
                    details: 'Cannot reach backend services'
                };
            }

            // Calculate overall score and status
            let score = 0;
            if (results.health.status === 'healthy') score += 50;
            if (results.cors.status === 'healthy') score += 30;
            if (results.health.responseTime < 1000) score += 10;
            if (results.cors.responseTime < 1000) score += 10;

            if (score >= 80) {
                results.overall = { status: 'healthy', score };
            } else if (score >= 50) {
                results.overall = { status: 'degraded', score };
            } else {
                results.overall = { status: 'unhealthy', score };
            }

            if (process.env.NODE_ENV === 'development') {
                console.log('[API] Performance Check Results:', results);
            }

            return results;
        } catch (error) {
            if (process.env.NODE_ENV === 'development') {
                console.error('[API] Performance Check Error:', error);
            }
            
            results.connectivity = {
                status: 'unhealthy',
                details: `Performance check failed: ${error instanceof Error ? error.message : 'Unknown error'}`
            };
            
            return results;
        }
    },
    // Log Management
    async searchLogs(params: LogSearchParams = {}): Promise<LogSearchResponse> {
        const queryParams = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null) {
                queryParams.append(key, String(value));
            }
        });
        
        return withRetry(async () => {
            try {
                const backendResponse = await fetchAPI<BackendLogSearchResponse>(`/logs/search?${queryParams.toString()}`);
                
                // Log successful response in development
                if (process.env.NODE_ENV === 'development') {
                    console.log('[API] Raw backend response structure:', {
                        hasResults: 'results' in backendResponse,
                        hasLogs: 'logs' in backendResponse,
                        resultsType: typeof backendResponse.results,
                        resultsLength: Array.isArray(backendResponse.results) ? backendResponse.results.length : 'not array',
                        total: backendResponse.total,
                        limit: backendResponse.limit,
                        offset: backendResponse.offset,
                    });
                }
                
                return transformLogSearchResponse(backendResponse);
            } catch (error) {
                // Add more context to API errors
                if (error instanceof APIError) {
                    const enhancedError = new APIError(
                        error.status,
                        error.statusText,
                        {
                            ...error.data,
                            endpoint: '/logs/search',
                            params: Object.fromEntries(queryParams.entries()),
                            message: `Failed to search logs: ${error.statusText}`,
                            suggestion: error.status === 404 
                                ? 'The logs endpoint may not be available. Check if the backend is running.'
                                : error.status >= 500 
                                ? 'Server error occurred. Please try again later.'
                                : 'Check your search parameters and try again.'
                        }
                    );
                    
                    if (process.env.NODE_ENV === 'development') {
                        console.error('[API] Enhanced error details:', enhancedError.data);
                    }
                    
                    throw enhancedError;
                }
                
                // Handle response transformation errors
                if (error instanceof Error && error.message.includes('Invalid response format')) {
                    throw new Error(`API Response Format Error: ${error.message}. This indicates a mismatch between frontend expectations and backend response format.`);
                }
                
                throw error;
            }
        });
    },

    async getLog(logId: string): Promise<LogEntry> {
        try {
            return await fetchAPI<LogEntry>(`/logs/${logId}`);
        } catch (error) {
            // Add more context to API errors
            if (error instanceof APIError) {
                throw new APIError(
                    error.status,
                    error.statusText,
                    {
                        ...error.data,
                        endpoint: `/logs/${logId}`,
                        logId
                    }
                );
            }
            throw error;
        }
    },

    // Clustering
    async runClustering(): Promise<{ message: string; clusters: number }> {
        return fetchAPI<{ message: string; clusters: number }>('/logs/clustering/run', {
            method: 'POST',
        });
    },

    async getClusters(): Promise<Cluster[]> {
        try {
            const response = await fetchAPI<{ clusters: Cluster[]; total: number; limit: number; offset: number }>('/logs/clustering/clusters');
            return response.clusters || [];
        } catch (error) {
            if (error instanceof APIError) {
                throw new APIError(
                    error.status,
                    error.statusText,
                    {
                        ...error.data,
                        endpoint: '/logs/clustering/clusters'
                    }
                );
            }
            throw error;
        }
    },

    async getOutliers(): Promise<LogEntry[]> {
        try {
            const response = await fetchAPI<{ outliers: LogEntry[]; total: number; limit: number; offset: number }>('/logs/clustering/outliers');
            return response.outliers || [];
        } catch (error) {
            if (error instanceof APIError) {
                throw new APIError(
                    error.status,
                    error.statusText,
                    {
                        ...error.data,
                        endpoint: '/logs/clustering/outliers'
                    }
                );
            }
            throw error;
        }
    },

    // Anomaly Detection
    async detectAnomaliesIsolationForest(): Promise<AnomalyDetectionResult[]> {
        return fetchAPI<AnomalyDetectionResult[]>('/logs/anomaly-detection/isolation-forest', {
            method: 'POST',
        });
    },

    async detectAnomaliesZScore(): Promise<AnomalyDetectionResult[]> {
        return fetchAPI<AnomalyDetectionResult[]>('/logs/anomaly-detection/z-score', {
            method: 'POST',
        });
    },

    async detectAnomaliesIQR(): Promise<AnomalyDetectionResult[]> {
        return fetchAPI<AnomalyDetectionResult[]>('/logs/anomaly-detection/iqr', {
            method: 'POST',
        });
    },

    async scoreLog(logId: string): Promise<AnomalyDetectionResult> {
        return fetchAPI<AnomalyDetectionResult>(`/logs/anomaly-detection/score/${logId}`, {
            method: 'POST',
        });
    },

    // Agent API
    async analyzeAnomaly(logId: string): Promise<any> {
        return fetchAPI<any>(`/agent/analyze-anomaly/${logId}`, {
            method: 'POST',
        });
    },

    // Volume Data
    async getLogVolume(params: {
        hours?: number;
        bucket_minutes?: number;
        level?: string;
        service?: string;
    } = {}): Promise<VolumeResponse> {
        const queryParams = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null) {
                queryParams.append(key, String(value));
            }
        });
        
        return withRetry(async () => {
            try {
                const response = await fetchAPI<VolumeResponse>(`/logs/volume?${queryParams.toString()}`);
                
                if (process.env.NODE_ENV === 'development') {
                    console.log('[API] Volume data response:', {
                        buckets: response.volume_data?.length || 0,
                        totalLogs: response.total_logs,
                        timeRange: response.time_range
                    });
                }
                
                return response;
            } catch (error) {
                if (error instanceof APIError) {
                    const enhancedError = new APIError(
                        error.status,
                        error.statusText,
                        {
                            ...error.data,
                            endpoint: '/logs/volume',
                            params: Object.fromEntries(queryParams.entries()),
                            message: `Failed to fetch log volume: ${error.statusText}`,
                            suggestion: error.status === 404 
                                ? 'The volume endpoint may not be available. Check if the backend is running.'
                                : error.status >= 500 
                                ? 'Server error occurred. Please try again later.'
                                : 'Check your parameters and try again.'
                        }
                    );
                    
                    if (process.env.NODE_ENV === 'development') {
                        console.error('[API] Volume API error:', enhancedError.data);
                    }
                    
                    throw enhancedError;
                }
                
                throw error;
            }
        });
    },
};

