/**
 * Property tests for environment configuration usage
 * Validates Requirements 3.3
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('Environment Configuration Usage Properties', () => {
    let originalEnv: NodeJS.ProcessEnv;

    beforeEach(() => {
        // Save original environment
        originalEnv = { ...process.env };
        
        // Reset console methods
        vi.spyOn(console, 'log').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'error').mockImplementation(() => {});
        
        // Clear module cache to ensure fresh imports
        vi.resetModules();
    });

    afterEach(() => {
        // Restore original environment
        process.env = originalEnv;
    });

    describe('Property 5: Environment Configuration Usage', () => {
        it('should prioritize NEXT_PUBLIC_API_URL when explicitly set', async () => {
            // Property: Explicit environment variables should take highest priority
            process.env.NEXT_PUBLIC_API_URL = 'http://explicit-api.example.com:8080';
            process.env.NODE_ENV = 'development';

            const { getAppConfig } = await import('./config');
            const config = getAppConfig();

            expect(config.apiUrl).toBe('http://explicit-api.example.com:8080');
        });

        it('should auto-detect API URL from browser hostname when env var not set', async () => {
            // Property: Auto-detection should work when explicit config is missing
            delete process.env.NEXT_PUBLIC_API_URL;
            process.env.NODE_ENV = 'development';

            // Mock window.location for browser environment
            Object.defineProperty(window, 'location', {
                value: {
                    protocol: 'http:',
                    hostname: 'test-frontend.local',
                },
                writable: true,
            });

            const { getAppConfig } = await import('./config');
            const config = getAppConfig();

            expect(config.apiUrl).toBe('http://test-frontend.local:8000');
        });

        it('should use server-side defaults when running on server', async () => {
            // Property: Server-side rendering should have appropriate defaults
            delete process.env.NEXT_PUBLIC_API_URL;
            process.env.NODE_ENV = 'development';

            // Mock server-side environment (no window)
            const originalWindow = global.window;
            // @ts-ignore
            delete global.window;

            const { getAppConfig } = await import('./config');
            const config = getAppConfig();

            expect(config.apiUrl).toBe('http://localhost:8000');

            // Restore window
            global.window = originalWindow;
        });

        it('should handle different NODE_ENV values correctly', async () => {
            // Property: Environment detection should work for all valid NODE_ENV values
            const envConfigs = [
                { nodeEnv: 'development', expectedDev: true, expectedProd: false },
                { nodeEnv: 'production', expectedDev: false, expectedProd: true },
                { nodeEnv: 'test', expectedDev: false, expectedProd: false },
                { nodeEnv: undefined, expectedDev: false, expectedProd: false },
            ];

            for (const envConfig of envConfigs) {
                if (envConfig.nodeEnv) {
                    process.env.NODE_ENV = envConfig.nodeEnv;
                } else {
                    delete process.env.NODE_ENV;
                }

                vi.resetModules();
                const { getAppConfig } = await import('./config');
                const config = getAppConfig();

                expect(config.isDevelopment).toBe(envConfig.expectedDev);
                expect(config.isProduction).toBe(envConfig.expectedProd);
            }
        });

        it('should validate configuration and log appropriate messages', async () => {
            // Property: Configuration validation should provide helpful feedback
            process.env.NEXT_PUBLIC_API_URL = 'invalid-url';
            process.env.NODE_ENV = 'development';

            const { validateConfig } = await import('./config');
            validateConfig();

            // Should log error for invalid URL
            expect(console.error).toHaveBeenCalledWith(
                expect.stringMatching(/Invalid API URL format/i),
                'invalid-url'
            );
        });

        it('should detect mixed content issues in configuration', async () => {
            // Property: Security issues should be detected and warned about
            process.env.NEXT_PUBLIC_API_URL = 'http://api.example.com';
            process.env.NODE_ENV = 'development';

            // Mock HTTPS frontend
            Object.defineProperty(window, 'location', {
                value: {
                    protocol: 'https:',
                    hostname: 'frontend.example.com',
                },
                writable: true,
            });

            const { validateConfig } = await import('./config');
            validateConfig();

            // Should warn about mixed content
            expect(console.warn).toHaveBeenCalledWith(
                expect.stringMatching(/Mixed content warning/i)
            );
        });

        it('should handle Sentry DSN configuration properly', async () => {
            // Property: Optional configuration should be handled gracefully
            const sentryConfigs = [
                { dsn: 'https://key@sentry.io/project', expected: 'https://key@sentry.io/project' },
                { dsn: '', expected: '' }, // Empty string is preserved
                { dsn: undefined, expected: undefined },
            ];

            for (const sentryConfig of sentryConfigs) {
                if (sentryConfig.dsn !== undefined) {
                    process.env.NEXT_PUBLIC_SENTRY_DSN = sentryConfig.dsn;
                } else {
                    delete process.env.NEXT_PUBLIC_SENTRY_DSN;
                }

                vi.resetModules();
                const { getAppConfig } = await import('./config');
                const config = getAppConfig();

                expect(config.sentryDsn).toBe(sentryConfig.expected);
            }
        });

        it('should remove trailing slashes from API URLs', async () => {
            // Property: URL normalization should be consistent
            const urlConfigs = [
                { input: 'http://api.example.com/', expected: 'http://api.example.com' },
                { input: 'http://api.example.com', expected: 'http://api.example.com' },
                { input: 'https://api.example.com:8080/', expected: 'https://api.example.com:8080' },
                { input: 'http://localhost:3000///', expected: 'http://localhost:3000//' }, // Only removes single trailing slash
            ];

            for (const urlConfig of urlConfigs) {
                process.env.NEXT_PUBLIC_API_URL = urlConfig.input;

                vi.resetModules();
                const { getAppConfig } = await import('./config');
                const config = getAppConfig();

                expect(config.apiUrl).toBe(urlConfig.expected);
            }
        });

        it('should provide comprehensive environment information', async () => {
            // Property: Environment introspection should be complete and accurate
            process.env.NODE_ENV = 'development';

            // Mock browser environment
            Object.defineProperty(window, 'location', {
                value: {
                    protocol: 'http:',
                    hostname: 'localhost',
                },
                writable: true,
            });

            Object.defineProperty(window, 'navigator', {
                value: {
                    userAgent: 'Test Browser/1.0',
                },
                writable: true,
            });

            const { getEnvironmentInfo } = await import('./config');
            const envInfo = getEnvironmentInfo();

            expect(envInfo).toHaveProperty('nodeEnv', 'development');
            expect(envInfo).toHaveProperty('isClient', true);
            expect(envInfo).toHaveProperty('isServer', false);
            expect(envInfo).toHaveProperty('hostname', 'localhost');
            expect(envInfo).toHaveProperty('protocol', 'http:');
            expect(envInfo).toHaveProperty('userAgent', 'Test Browser/1.0');
        });

        it('should handle server-side environment information correctly', async () => {
            // Property: Server-side environment detection should work without browser APIs
            process.env.NODE_ENV = 'production';

            // Mock server-side environment
            const originalWindow = global.window;
            const originalNavigator = global.navigator;
            // @ts-ignore
            delete global.window;
            // @ts-ignore
            delete global.navigator;

            const { getEnvironmentInfo } = await import('./config');
            const envInfo = getEnvironmentInfo();

            expect(envInfo.nodeEnv).toBe('production');
            expect(envInfo.isClient).toBe(false);
            expect(envInfo.isServer).toBe(true);
            expect(envInfo.hostname).toBe('server');
            expect(envInfo.protocol).toBe('unknown');
            expect(envInfo.userAgent).toBe('server');

            // Restore globals
            global.window = originalWindow;
            global.navigator = originalNavigator;
        });

        it('should log configuration details in development mode only', async () => {
            // Property: Debug logging should be environment-aware
            const environments = ['development', 'production', 'test'];

            for (const env of environments) {
                process.env.NODE_ENV = env;
                process.env.NEXT_PUBLIC_API_URL = 'http://test.example.com';

                vi.resetModules();
                vi.clearAllMocks();

                const { validateConfig } = await import('./config');
                validateConfig();

                if (env === 'development') {
                    expect(console.log).toHaveBeenCalledWith(
                        expect.stringMatching(/\[Config\].*Application Configuration/),
                        expect.any(Object)
                    );
                } else {
                    expect(console.log).not.toHaveBeenCalledWith(
                        expect.stringMatching(/\[Config\].*Application Configuration/),
                        expect.any(Object)
                    );
                }
            }
        });

        it('should perform non-blocking API reachability check in development', async () => {
            // Property: Configuration validation should not block application startup
            process.env.NODE_ENV = 'development';
            process.env.NEXT_PUBLIC_API_URL = 'http://unreachable.example.com:8000';

            // Mock fetch to simulate unreachable API
            const mockFetch = vi.fn().mockRejectedValue(new Error('Network error'));
            global.fetch = mockFetch;

            const { validateConfig } = await import('./config');
            
            // Should not throw or block
            expect(() => validateConfig()).not.toThrow();

            // Should attempt to check reachability
            expect(mockFetch).toHaveBeenCalledWith(
                'http://unreachable.example.com:8000/health',
                expect.objectContaining({
                    method: 'HEAD',
                    mode: 'no-cors',
                })
            );
        });
    });
});