/**
 * Frontend configuration utilities
 */

export interface AppConfig {
    apiUrl: string;
    isDevelopment: boolean;
    isProduction: boolean;
    sentryDsn?: string;
}

/**
 * Get application configuration
 */
export function getAppConfig(): AppConfig {
    const isDevelopment = process.env.NODE_ENV === 'development';
    const isProduction = process.env.NODE_ENV === 'production';
    
    // Get API URL with fallback logic
    let apiUrl = process.env.NEXT_PUBLIC_API_URL;
    
    if (!apiUrl) {
        if (typeof window !== 'undefined') {
            // Browser: use current hostname with backend port
            const protocol = window.location.protocol;
            const hostname = window.location.hostname;
            apiUrl = `${protocol}//${hostname}:8000`;
        } else {
            // Server-side: use localhost
            apiUrl = 'http://localhost:8000';
        }
    }
    
    return {
        apiUrl: apiUrl.replace(/\/$/, ''), // Remove trailing slash
        isDevelopment,
        isProduction,
        sentryDsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    };
}

/**
 * Validate configuration and log warnings
 */
export function validateConfig(): void {
    const config = getAppConfig();
    
    if (config.isDevelopment) {
        console.log('[Config] Application Configuration:', {
            apiUrl: config.apiUrl,
            environment: process.env.NODE_ENV,
            sentryEnabled: !!config.sentryDsn,
            envVariables: {
                NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'not set',
                NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN ? 'set' : 'not set',
            }
        });
        
        // Validate API URL format
        try {
            new URL(config.apiUrl);
        } catch (error) {
            console.error('[Config] Invalid API URL format:', config.apiUrl);
        }
        
        // Check for common issues
        if (typeof window !== 'undefined') {
            const isHttps = window.location.protocol === 'https:';
            const apiIsHttp = config.apiUrl.startsWith('http:');
            
            if (isHttps && apiIsHttp) {
                console.warn('[Config] Mixed content warning: HTTPS frontend with HTTP API may be blocked by browser');
            }
        }
        
        // Check if API URL is reachable (non-blocking)
        if (typeof window !== 'undefined') {
            fetch(`${config.apiUrl}/health`, { 
                method: 'HEAD',
                mode: 'no-cors' // Avoid CORS preflight for this check
            }).catch(() => {
                console.warn(`[Config] API endpoint may not be reachable: ${config.apiUrl}/health`);
            });
        }
    }
}

/**
 * Get environment-specific configuration
 */
export function getEnvironmentInfo() {
    return {
        nodeEnv: process.env.NODE_ENV,
        isClient: typeof window !== 'undefined',
        isServer: typeof window === 'undefined',
        hostname: typeof window !== 'undefined' ? window.location.hostname : 'server',
        protocol: typeof window !== 'undefined' ? window.location.protocol : 'unknown',
        userAgent: typeof window !== 'undefined' ? navigator.userAgent : 'server',
    };
}