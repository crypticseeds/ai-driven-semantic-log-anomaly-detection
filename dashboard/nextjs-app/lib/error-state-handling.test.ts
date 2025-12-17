/**
 * Property tests for error state handling
 * Validates Requirements 1.5, 2.5, 3.4
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the config module
vi.mock('./config', () => ({
    getAppConfig: () => ({
        apiUrl: 'http://localhost:8000',
        isDevelopment: true,
        isProduction: false,
    }),
    validateConfig: vi.fn(),
}));

// Import after mocking
import { api, APIError } from './api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('Error State Handling Properties', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Reset console methods
        vi.spyOn(console, 'log').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    describe('Property 3: Error State Handling', () => {
        it('should provide consistent error structure across all API methods', async () => {
            // Property: All API methods should handle errors with consistent structure
            // Test only methods that use fetchAPI for consistent error handling
            const apiMethods = [
                { method: 'searchLogs', args: [{}] },
                { method: 'getLogVolume', args: [{}] },
                { method: 'getClusters', args: [] },
                { method: 'getOutliers', args: [] },
            ];

            const errorScenarios = [
                { status: 400, statusText: 'Bad Request', detail: 'Invalid parameters' },
                { status: 404, statusText: 'Not Found', detail: 'Resource not found' },
                { status: 500, statusText: 'Internal Server Error', detail: 'Server error' },
            ];

            for (const scenario of errorScenarios) {
                for (const apiMethod of apiMethods) {
                    mockFetch.mockResolvedValueOnce({
                        ok: false,
                        status: scenario.status,
                        statusText: scenario.statusText,
                        headers: new Headers({
                            'content-type': 'application/json',
                        }),
                        json: async () => ({ detail: scenario.detail }),
                    });

                    try {
                        // @ts-ignore - Dynamic method call for testing
                        await api[apiMethod.method](...apiMethod.args);
                        expect.fail(`${apiMethod.method} should have thrown error for ${scenario.status}`);
                    } catch (error) {
                        // Verify consistent APIError structure
                        expect(error).toBeInstanceOf(APIError);
                        const apiError = error as APIError;
                        expect(apiError.status).toBe(scenario.status);
                        expect(apiError.statusText).toBe(scenario.statusText);
                        expect(apiError.data).toHaveProperty('detail', scenario.detail);
                        expect(apiError.data).toHaveProperty('requestId');
                        expect(apiError.data).toHaveProperty('responseTime');
                        expect(apiError.data).toHaveProperty('endpoint');
                    }
                }
            }
        });

        it('should handle network errors gracefully with helpful messages', async () => {
            // Property: Network errors should be transformed into user-friendly messages
            const networkErrors = [
                {
                    error: new TypeError('Failed to fetch'),
                    expectedMessagePattern: /Network error.*Connection failed/i,
                },
                {
                    error: new TypeError('NetworkError when attempting to fetch resource'),
                    expectedMessagePattern: /Network error.*Unable to connect/i,
                },
                {
                    error: new Error('CORS policy: No \'Access-Control-Allow-Origin\' header'),
                    expectedMessagePattern: /Network error/i,
                },
            ];

            for (const networkError of networkErrors) {
                mockFetch.mockRejectedValueOnce(networkError.error);

                try {
                    await api.searchLogs();
                    expect.fail('Should have thrown network error');
                } catch (error) {
                    expect(error).toBeInstanceOf(Error);
                    expect((error as Error).message).toMatch(/Network error/i);
                    expect((error as Error).message).toContain('Request ID:');
                }
            }
        });

        it('should provide detailed error context in development mode', async () => {
            // Property: Development mode should provide enhanced error information
            const originalEnv = process.env.NODE_ENV;
            process.env.NODE_ENV = 'development';

            const errorResponse = {
                status: 500,
                statusText: 'Internal Server Error',
                detail: 'Database connection failed',
            };

            mockFetch.mockResolvedValueOnce({
                ok: false,
                status: errorResponse.status,
                statusText: errorResponse.statusText,
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => ({ detail: errorResponse.detail }),
            });

            try {
                await api.searchLogs();
                expect.fail('Should have thrown error');
            } catch (error) {
                expect(error).toBeInstanceOf(APIError);
                const apiError = error as APIError;
                
                // Verify enhanced error context in development
                expect(apiError.data).toHaveProperty('requestId');
                expect(apiError.data).toHaveProperty('responseTime');
                expect(apiError.data).toHaveProperty('endpoint');
                expect(apiError.data.endpoint).toBe('/logs/search');
                
                // Verify console logging occurred (check that console.error was called)
                expect(console.error).toHaveBeenCalled();
            }

            process.env.NODE_ENV = originalEnv;
        });

        it('should handle malformed error responses gracefully', async () => {
            // Property: Malformed error responses should not crash the application
            const malformedResponses = [
                {
                    description: 'Non-JSON response',
                    mockResponse: {
                        ok: false,
                        status: 500,
                        statusText: 'Internal Server Error',
                        headers: new Headers({
                            'content-type': 'text/html',
                        }),
                        json: async () => {
                            throw new Error('Unexpected token < in JSON');
                        },
                    },
                },
            ];

            for (const testCase of malformedResponses) {
                mockFetch.mockResolvedValueOnce(testCase.mockResponse);

                try {
                    await api.searchLogs();
                    expect.fail(`Should have thrown error for ${testCase.description}`);
                } catch (error) {
                    expect(error).toBeInstanceOf(APIError);
                    const apiError = error as APIError;
                    
                    // Should still provide basic error information
                    expect(apiError.status).toBe(500);
                    expect(apiError.statusText).toBe('Internal Server Error');
                    
                    // Should have fallback error data
                    expect(apiError.data).toHaveProperty('detail');
                    expect(apiError.data.detail).toBe('Internal Server Error');
                }
            }
        });

        it('should implement retry logic for retryable errors', async () => {
            // Property: Retryable errors should trigger retry attempts with exponential backoff
            const retryableError = new TypeError('Failed to fetch');

            // Mock: First two attempts fail, third succeeds
            mockFetch
                .mockRejectedValueOnce(retryableError)
                .mockRejectedValueOnce(retryableError)
                .mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => ({
                        results: [],
                        total: 0,
                        limit: 100,
                        offset: 0,
                    }),
                });

            const result = await api.searchLogs();

            // Should eventually succeed after retries
            expect(result.logs).toEqual([]);
            expect(mockFetch).toHaveBeenCalledTimes(3);
        }, 10000);

        it('should not retry non-retryable errors', async () => {
            // Property: Client errors (4xx) should not trigger retries
            const status = 400;
            
            mockFetch.mockResolvedValueOnce({
                ok: false,
                status,
                statusText: 'Bad Request',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => ({ detail: 'Client error' }),
            });

            try {
                await api.searchLogs();
                expect.fail(`Should have thrown error for status ${status}`);
            } catch (error) {
                expect(error).toBeInstanceOf(APIError);
                expect((error as APIError).status).toBe(status);
            }

            // Should only have made one attempt (no retries)
            expect(mockFetch).toHaveBeenCalledTimes(1);
        });

        it('should handle timeout scenarios appropriately', async () => {
            // Property: Long-running requests should be handled gracefully
            const timeoutError = new TypeError('Failed to fetch');
            
            mockFetch.mockRejectedValueOnce(timeoutError);

            try {
                await api.searchLogs();
                expect.fail('Should have thrown timeout error');
            } catch (error) {
                expect(error).toBeInstanceOf(Error);
                expect((error as Error).message).toContain('Network error');
            }
        });

        it('should provide appropriate error messages for different failure modes', async () => {
            // Property: Different types of failures should have contextually appropriate error messages
            const failureModes = [
                {
                    scenario: 'Server overloaded',
                    mockResponse: {
                        ok: false,
                        status: 503,
                        statusText: 'Service Unavailable',
                        headers: new Headers({ 'content-type': 'application/json' }),
                        json: async () => ({ detail: 'Server temporarily overloaded' }),
                    },
                    expectedContext: 'Service Unavailable',
                },
                {
                    scenario: 'Invalid request format',
                    mockResponse: {
                        ok: false,
                        status: 400,
                        statusText: 'Bad Request',
                        headers: new Headers({ 'content-type': 'application/json' }),
                        json: async () => ({ detail: 'Invalid JSON in request body' }),
                    },
                    expectedContext: 'Bad Request',
                },
            ];

            for (const failureMode of failureModes) {
                mockFetch.mockResolvedValueOnce(failureMode.mockResponse);

                try {
                    await api.searchLogs();
                    expect.fail(`Should have thrown error for ${failureMode.scenario}`);
                } catch (error) {
                    expect(error).toBeInstanceOf(APIError);
                    const apiError = error as APIError;
                    
                    // Verify appropriate error context
                    expect(apiError.statusText).toBe(failureMode.expectedContext);
                    expect(apiError.data.detail).toBeTruthy();
                    
                    // Verify error message provides helpful context
                    expect(apiError.message).toContain(failureMode.expectedContext);
                }
            }
        });

        it('should handle concurrent error scenarios correctly', async () => {
            // Property: Multiple concurrent requests with errors should be handled independently
            const concurrentRequests = [
                { shouldFail: false, response: { results: [], total: 0, limit: 100, offset: 0 } },
                { shouldFail: true, status: 500, statusText: 'Internal Server Error' },
            ];

            // Mock responses for concurrent requests
            concurrentRequests.forEach(request => {
                if (request.shouldFail) {
                    mockFetch.mockResolvedValueOnce({
                        ok: false,
                        status: request.status,
                        statusText: request.statusText,
                        headers: new Headers({ 'content-type': 'application/json' }),
                        json: async () => ({ detail: 'Error occurred' }),
                    });
                } else {
                    mockFetch.mockResolvedValueOnce({
                        ok: true,
                        status: 200,
                        statusText: 'OK',
                        headers: new Headers({ 'content-type': 'application/json' }),
                        json: async () => request.response,
                    });
                }
            });

            // Execute concurrent requests
            const promises = concurrentRequests.map(() => api.searchLogs());
            const results = await Promise.allSettled(promises);

            // Verify that successful and failed requests are handled independently
            expect(results[0].status).toBe('fulfilled');
            expect(results[1].status).toBe('rejected');

            // Verify error details for failed requests
            if (results[1].status === 'rejected') {
                expect(results[1].reason).toBeInstanceOf(APIError);
                expect((results[1].reason as APIError).status).toBe(500);
            }
        });
    });
});