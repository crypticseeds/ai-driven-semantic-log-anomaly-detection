/**
 * Property tests for API response transformation
 * Validates Requirements 1.2, 4.1, 4.2, 4.4
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
import { api, LogEntry, LogSearchResponse } from './api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('API Response Transformation Properties', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Reset console methods
        vi.spyOn(console, 'log').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    describe('Property 1: API Response Transformation', () => {
        it('should transform backend response format to frontend expectations', async () => {
            // Property: Any valid backend response should be transformable to frontend format
            const backendResponse = {
                results: [
                    {
                        id: 'log-1',
                        timestamp: '2023-12-17T10:00:00Z',
                        level: 'INFO' as const,
                        service: 'test-service',
                        message: 'Test message',
                        cluster_id: 1,
                        anomaly_score: 0.5,
                        is_anomaly: false,
                    }
                ],
                total: 1,
                limit: 100,
                offset: 0,
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => backendResponse,
            });

            const result = await api.searchLogs();

            // Verify transformation properties
            expect(result).toHaveProperty('logs');
            expect(result).toHaveProperty('total');
            expect(result).toHaveProperty('limit');
            expect(result).toHaveProperty('offset');
            
            expect(Array.isArray(result.logs)).toBe(true);
            expect(typeof result.total).toBe('number');
            expect(typeof result.limit).toBe('number');
            expect(typeof result.offset).toBe('number');
            
            // Verify log entry structure
            expect(result.logs[0]).toHaveProperty('id');
            expect(result.logs[0]).toHaveProperty('timestamp');
            expect(result.logs[0]).toHaveProperty('level');
            expect(result.logs[0]).toHaveProperty('service');
            expect(result.logs[0]).toHaveProperty('message');
        });

        it('should handle backend response with "logs" field instead of "results"', async () => {
            // Property: Backward compatibility with different field names
            const backendResponse = {
                logs: [  // Using 'logs' instead of 'results'
                    {
                        id: 'log-1',
                        timestamp: '2023-12-17T10:00:00Z',
                        level: 'INFO' as const,
                        service: 'test-service',
                        message: 'Test message',
                    }
                ],
                total: 1,
                limit: 100,
                offset: 0,
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => backendResponse,
            });

            const result = await api.searchLogs();

            // Should still transform correctly
            expect(result.logs).toHaveLength(1);
            expect(result.logs[0].id).toBe('log-1');
        });

        it('should provide fallback values for missing or invalid fields', async () => {
            // Property: Robustness - invalid data should be handled gracefully
            const backendResponse = {
                results: [
                    {
                        // Missing required fields
                        message: 'Test message',
                        // Invalid types
                        timestamp: null,
                        level: 123,
                        service: undefined,
                    }
                ],
                // Invalid numeric fields
                total: 'invalid',
                limit: null,
                offset: undefined,
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => backendResponse,
            });

            const result = await api.searchLogs();

            // Should provide fallback values
            expect(result.total).toBe(0);
            expect(result.limit).toBe(100);
            expect(result.offset).toBe(0);
            
            // Should handle invalid log entry
            expect(result.logs).toHaveLength(1);
            expect(result.logs[0].id).toMatch(/unknown-/);
            expect(result.logs[0].level).toBe('INFO');
            expect(result.logs[0].service).toBe('unknown');
            expect(typeof result.logs[0].timestamp).toBe('string');
        });

        it('should validate response structure and log warnings for issues', async () => {
            // Property: Validation - structural issues should be detected and logged
            const consoleSpy = vi.spyOn(console, 'warn');
            
            const backendResponse = {
                results: 'not-an-array',  // Invalid structure
                total: 1,
                limit: 100,
                offset: 0,
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => backendResponse,
            });

            try {
                await api.searchLogs();
                expect.fail('Should have thrown an error');
            } catch (error) {
                expect(error).toBeInstanceOf(Error);
                expect((error as Error).message).toContain('Invalid response format');
            }
        });

        it('should handle empty or null responses gracefully', async () => {
            // Property: Edge case handling - null/empty responses should not crash
            const testCases = [
                { response: null, shouldThrow: true },
                { response: undefined, shouldThrow: true },
                { response: {}, shouldThrow: true },
                { response: { results: [] }, shouldThrow: false }
            ];
            
            for (const testCase of testCases) {
                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => testCase.response,
                });

                if (testCase.shouldThrow) {
                    try {
                        await api.searchLogs();
                        expect.fail(`Should have thrown for response: ${JSON.stringify(testCase.response)}`);
                    } catch (error) {
                        expect(error).toBeInstanceOf(Error);
                    }
                } else {
                    const result = await api.searchLogs();
                    expect(result.logs).toEqual([]);
                    expect(typeof result.total).toBe('number');
                }
            }
        }, 10000);

        it('should preserve optional fields when present and valid', async () => {
            // Property: Data preservation - optional fields should be preserved when valid
            const backendResponse = {
                results: [
                    {
                        id: 'log-1',
                        timestamp: '2023-12-17T10:00:00Z',
                        level: 'ERROR' as const,
                        service: 'test-service',
                        message: 'Test message',
                        cluster_id: 5,
                        anomaly_score: 0.85,
                        is_anomaly: true,
                        metadata: { key: 'value' },
                        redacted_message: 'Redacted test message',
                        pii_entities_detected: { email: 1, phone: 2 },
                    }
                ],
                total: 1,
                limit: 100,
                offset: 0,
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => backendResponse,
            });

            const result = await api.searchLogs();

            const log = result.logs[0];
            expect(log.cluster_id).toBe(5);
            expect(log.anomaly_score).toBe(0.85);
            expect(log.is_anomaly).toBe(true);
            expect(log.metadata).toEqual({ key: 'value' });
            expect(log.redacted_message).toBe('Redacted test message');
            expect(log.pii_entities_detected).toEqual({ email: 1, phone: 2 });
        });

        it('should handle mixed valid and invalid log entries', async () => {
            // Property: Partial failure handling - some invalid entries shouldn't break the entire response
            const backendResponse = {
                results: [
                    // Valid entry
                    {
                        id: 'log-1',
                        timestamp: '2023-12-17T10:00:00Z',
                        level: 'INFO' as const,
                        service: 'test-service',
                        message: 'Valid message',
                    },
                    // Invalid entry (not an object)
                    'invalid-entry',
                    // Partially valid entry
                    {
                        id: 'log-2',
                        // Missing required fields
                        message: 'Partial message',
                    },
                    // Another valid entry
                    {
                        id: 'log-3',
                        timestamp: '2023-12-17T10:01:00Z',
                        level: 'WARN' as const,
                        service: 'another-service',
                        message: 'Another valid message',
                    }
                ],
                total: 4,
                limit: 100,
                offset: 0,
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => backendResponse,
            });

            const result = await api.searchLogs();

            // Should include valid entries and handle invalid ones
            expect(result.logs).toHaveLength(3); // 2 valid + 1 partially valid
            expect(result.logs[0].id).toBe('log-1');
            expect(result.logs[1].id).toBe('log-2');
            expect(result.logs[2].id).toBe('log-3');
            
            // Partially valid entry should have fallbacks
            expect(result.logs[1].service).toBe('unknown');
            expect(result.logs[1].level).toBe('INFO');
        });
    });
});