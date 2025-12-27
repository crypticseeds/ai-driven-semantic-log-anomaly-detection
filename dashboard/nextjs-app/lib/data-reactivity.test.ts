/**
 * Property tests for data reactivity
 * Validates Requirements 2.3
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
import { api, LogSearchResponse, VolumeResponse } from './api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('Data Reactivity Properties', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Reset console methods
        vi.spyOn(console, 'log').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    describe('Property 6: Data Reactivity', () => {
        it('should reflect parameter changes in API responses', async () => {
            // Property: API responses should change appropriately when parameters change
            const baseVolumeResponse: VolumeResponse = {
                volume_data: [
                    {
                        timestamp: '2023-12-17T10:00:00Z',
                        count: 100,
                        level_breakdown: { ERROR: 10, WARN: 20, INFO: 60, DEBUG: 10 },
                    },
                ],
                total_logs: 100,
                time_range: {
                    start_time: '2023-12-17T10:00:00Z',
                    end_time: '2023-12-17T11:00:00Z',
                    hours: 1,
                    bucket_minutes: 5,
                },
                filters: {},
            };

            // Test different parameter combinations and their expected effects
            const parameterTests = [
                {
                    params: { hours: 1 },
                    expectedResponse: {
                        ...baseVolumeResponse,
                        time_range: { ...baseVolumeResponse.time_range, hours: 1 },
                    },
                },
                {
                    params: { hours: 6 },
                    expectedResponse: {
                        ...baseVolumeResponse,
                        time_range: { ...baseVolumeResponse.time_range, hours: 6 },
                        total_logs: 600, // More hours = more logs
                    },
                },
                {
                    params: { bucket_minutes: 10 },
                    expectedResponse: {
                        ...baseVolumeResponse,
                        time_range: { ...baseVolumeResponse.time_range, bucket_minutes: 10 },
                    },
                },
                {
                    params: { level: 'ERROR' },
                    expectedResponse: {
                        ...baseVolumeResponse,
                        filters: { level: 'ERROR', service: undefined },
                        total_logs: 50, // Filtered data = fewer logs
                    },
                },
                {
                    params: { service: 'test-service' },
                    expectedResponse: {
                        ...baseVolumeResponse,
                        filters: { level: undefined, service: 'test-service' },
                        total_logs: 75, // Service filter = different count
                    },
                },
            ];

            // Mock responses for each parameter test
            parameterTests.forEach(test => {
                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => test.expectedResponse,
                });
            });

            // Execute tests and verify reactivity
            for (const test of parameterTests) {
                const result = await api.getLogVolume(test.params);
                
                // Verify that the response reflects the parameter changes
                if ('hours' in test.params) {
                    expect(result.time_range.hours).toBe(test.params.hours);
                }
                if ('bucket_minutes' in test.params) {
                    expect(result.time_range.bucket_minutes).toBe(test.params.bucket_minutes);
                }
                if ('level' in test.params) {
                    expect(result.filters.level).toBe(test.params.level);
                }
                if ('service' in test.params) {
                    expect(result.filters.service).toBe(test.params.service);
                }
                
                // Verify that data changes appropriately
                expect(result.total_logs).toBe(test.expectedResponse.total_logs);
            }
        });

        it('should handle real-time data updates correctly', async () => {
            // Property: Subsequent API calls should reflect data changes over time
            const timeSequence = [
                {
                    timestamp: '2023-12-17T10:00:00Z',
                    response: {
                        volume_data: [
                            {
                                timestamp: '2023-12-17T10:00:00Z',
                                count: 100,
                                level_breakdown: { ERROR: 5, WARN: 15, INFO: 70, DEBUG: 10 },
                            },
                        ],
                        total_logs: 100,
                        time_range: {
                            start_time: '2023-12-17T09:00:00Z',
                            end_time: '2023-12-17T10:00:00Z',
                            hours: 1,
                            bucket_minutes: 5,
                        },
                        filters: {},
                    },
                },
                {
                    timestamp: '2023-12-17T10:05:00Z',
                    response: {
                        volume_data: [
                            {
                                timestamp: '2023-12-17T10:00:00Z',
                                count: 100,
                                level_breakdown: { ERROR: 5, WARN: 15, INFO: 70, DEBUG: 10 },
                            },
                            {
                                timestamp: '2023-12-17T10:05:00Z',
                                count: 150,
                                level_breakdown: { ERROR: 10, WARN: 25, INFO: 100, DEBUG: 15 },
                            },
                        ],
                        total_logs: 250, // Cumulative increase
                        time_range: {
                            start_time: '2023-12-17T09:05:00Z',
                            end_time: '2023-12-17T10:05:00Z',
                            hours: 1,
                            bucket_minutes: 5,
                        },
                        filters: {},
                    },
                },
                {
                    timestamp: '2023-12-17T10:10:00Z',
                    response: {
                        volume_data: [
                            {
                                timestamp: '2023-12-17T10:05:00Z',
                                count: 150,
                                level_breakdown: { ERROR: 10, WARN: 25, INFO: 100, DEBUG: 15 },
                            },
                            {
                                timestamp: '2023-12-17T10:10:00Z',
                                count: 200,
                                level_breakdown: { ERROR: 15, WARN: 35, INFO: 130, DEBUG: 20 },
                            },
                        ],
                        total_logs: 350, // Further increase
                        time_range: {
                            start_time: '2023-12-17T09:10:00Z',
                            end_time: '2023-12-17T10:10:00Z',
                            hours: 1,
                            bucket_minutes: 5,
                        },
                        filters: {},
                    },
                },
            ];

            // Mock sequential responses
            timeSequence.forEach(timePoint => {
                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => timePoint.response,
                });
            });

            // Simulate real-time updates
            const results = [];
            for (const timePoint of timeSequence) {
                const result = await api.getLogVolume();
                results.push(result);
            }

            // Verify that data shows progression over time
            expect(results[0].total_logs).toBe(100);
            expect(results[1].total_logs).toBe(250);
            expect(results[2].total_logs).toBe(350);

            // Verify that volume data grows over time
            expect(results[0].volume_data).toHaveLength(1);
            expect(results[1].volume_data).toHaveLength(2);
            expect(results[2].volume_data).toHaveLength(2);

            // Verify that time ranges shift appropriately
            expect(results[0].time_range.end_time).toBe('2023-12-17T10:00:00Z');
            expect(results[1].time_range.end_time).toBe('2023-12-17T10:05:00Z');
            expect(results[2].time_range.end_time).toBe('2023-12-17T10:10:00Z');
        });

        it('should handle search parameter changes reactively', async () => {
            // Property: Search results should change when search parameters change
            const baseLogResponse: LogSearchResponse = {
                logs: [
                    {
                        id: 'log-1',
                        timestamp: '2023-12-17T10:00:00Z',
                        level: 'INFO',
                        service: 'web-service',
                        message: 'User login successful',
                    },
                ],
                total: 1,
                limit: 100,
                offset: 0,
            };

            const searchTests = [
                {
                    params: { query: 'login' },
                    expectedLogs: [
                        {
                            id: 'log-1',
                            timestamp: '2023-12-17T10:00:00Z',
                            level: 'INFO',
                            service: 'web-service',
                            message: 'User login successful',
                        },
                    ],
                    expectedTotal: 1,
                },
                {
                    params: { query: 'error' },
                    expectedLogs: [
                        {
                            id: 'log-2',
                            timestamp: '2023-12-17T10:01:00Z',
                            level: 'ERROR',
                            service: 'api-service',
                            message: 'Database connection error',
                        },
                    ],
                    expectedTotal: 1,
                },
                {
                    params: { level: 'ERROR' },
                    expectedLogs: [
                        {
                            id: 'log-2',
                            timestamp: '2023-12-17T10:01:00Z',
                            level: 'ERROR',
                            service: 'api-service',
                            message: 'Database connection error',
                        },
                        {
                            id: 'log-3',
                            timestamp: '2023-12-17T10:02:00Z',
                            level: 'ERROR',
                            service: 'auth-service',
                            message: 'Authentication failed',
                        },
                    ],
                    expectedTotal: 2,
                },
                {
                    params: { service: 'web-service' },
                    expectedLogs: [
                        {
                            id: 'log-1',
                            timestamp: '2023-12-17T10:00:00Z',
                            level: 'INFO',
                            service: 'web-service',
                            message: 'User login successful',
                        },
                    ],
                    expectedTotal: 1,
                },
                {
                    params: { limit: 50, offset: 0 },
                    expectedLogs: baseLogResponse.logs.slice(0, 50),
                    expectedTotal: 100,
                },
            ];

            // Mock responses for each search test
            searchTests.forEach(test => {
                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => ({
                        results: test.expectedLogs,
                        total: test.expectedTotal,
                        limit: test.params.limit || 100,
                        offset: test.params.offset || 0,
                        has_more: false,
                        search_type: 'text',
                    }),
                });
            });

            // Execute search tests and verify reactivity
            for (const test of searchTests) {
                const result = await api.searchLogs(test.params);
                
                // Verify that results change based on parameters
                expect(result.logs).toHaveLength(test.expectedLogs.length);
                expect(result.total).toBe(test.expectedTotal);
                
                // Verify specific content changes
                if (test.params.query === 'login') {
                    expect(result.logs[0].message).toContain('login');
                }
                if (test.params.query === 'error') {
                    expect(result.logs[0].message).toContain('error');
                }
                if (test.params.level === 'ERROR') {
                    result.logs.forEach(log => {
                        expect(log.level).toBe('ERROR');
                    });
                }
                if (test.params.service === 'web-service') {
                    result.logs.forEach(log => {
                        expect(log.service).toBe('web-service');
                    });
                }
            }
        });

        it('should handle filter combinations reactively', async () => {
            // Property: Multiple filters should work together and affect results appropriately
            const filterCombinations = [
                {
                    params: { level: 'ERROR', service: 'api-service' },
                    expectedCount: 5, // Specific service + level combination
                },
                {
                    params: { level: 'ERROR', service: 'web-service' },
                    expectedCount: 3, // Different service, same level
                },
                {
                    params: { level: 'INFO', service: 'api-service' },
                    expectedCount: 20, // Same service, different level
                },
                {
                    params: { 
                        level: 'ERROR', 
                        service: 'api-service',
                        start_time: '2023-12-17T10:00:00Z',
                        end_time: '2023-12-17T11:00:00Z'
                    },
                    expectedCount: 2, // Time range further filters results
                },
                {
                    params: { 
                        query: 'database',
                        level: 'ERROR', 
                        service: 'api-service'
                    },
                    expectedCount: 1, // Text search + filters
                },
            ];

            // Mock responses for filter combinations
            filterCombinations.forEach(test => {
                const mockLogs = Array.from({ length: test.expectedCount }, (_, i) => ({
                    id: `log-${i + 1}`,
                    timestamp: '2023-12-17T10:00:00Z',
                    level: test.params.level || 'INFO',
                    service: test.params.service || 'default-service',
                    message: `Test message ${i + 1}`,
                }));

                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => ({
                        results: mockLogs,
                        total: test.expectedCount,
                        limit: 100,
                        offset: 0,
                        has_more: false,
                        search_type: 'text',
                    }),
                });
            });

            // Test each filter combination
            for (const test of filterCombinations) {
                const result = await api.searchLogs(test.params);
                
                // Verify that filter combinations affect results appropriately
                expect(result.logs).toHaveLength(test.expectedCount);
                expect(result.total).toBe(test.expectedCount);
                
                // Verify that all returned logs match the filters
                result.logs.forEach(log => {
                    if (test.params.level) {
                        expect(log.level).toBe(test.params.level);
                    }
                    if (test.params.service) {
                        expect(log.service).toBe(test.params.service);
                    }
                });
            }
        });

        it('should handle pagination changes reactively', async () => {
            // Property: Pagination parameters should affect which subset of data is returned
            const totalLogs = 250;
            const paginationTests = [
                { limit: 50, offset: 0, expectedStart: 0, expectedEnd: 50 },
                { limit: 50, offset: 50, expectedStart: 50, expectedEnd: 100 },
                { limit: 100, offset: 100, expectedStart: 100, expectedEnd: 200 },
                { limit: 25, offset: 200, expectedStart: 200, expectedEnd: 225 },
                { limit: 50, offset: 225, expectedStart: 225, expectedEnd: 250 }, // Partial last page
            ];

            // Mock responses for pagination tests
            paginationTests.forEach(test => {
                const expectedCount = Math.min(test.limit, totalLogs - test.offset);
                const mockLogs = Array.from({ length: expectedCount }, (_, i) => ({
                    id: `log-${test.offset + i + 1}`,
                    timestamp: '2023-12-17T10:00:00Z',
                    level: 'INFO',
                    service: 'test-service',
                    message: `Log message ${test.offset + i + 1}`,
                }));

                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => ({
                        results: mockLogs,
                        total: totalLogs,
                        limit: test.limit,
                        offset: test.offset,
                        has_more: (test.offset + test.limit) < totalLogs,
                        search_type: 'text',
                    }),
                });
            });

            // Test each pagination scenario
            for (const test of paginationTests) {
                const result = await api.searchLogs({
                    limit: test.limit,
                    offset: test.offset,
                });
                
                // Verify pagination parameters are reflected
                expect(result.limit).toBe(test.limit);
                expect(result.offset).toBe(test.offset);
                expect(result.total).toBe(totalLogs);
                
                // Verify correct subset of data is returned
                const expectedCount = Math.min(test.limit, totalLogs - test.offset);
                expect(result.logs).toHaveLength(expectedCount);
                
                // Verify log IDs correspond to the correct page
                if (result.logs.length > 0) {
                    const firstLogId = parseInt(result.logs[0].id.split('-')[1]);
                    expect(firstLogId).toBe(test.offset + 1);
                }
            }
        });

        it('should handle error state changes reactively', async () => {
            // Property: Error conditions should be reflected immediately in API responses
            const errorScenarios = [
                {
                    params: { limit: -1 }, // Invalid limit
                    expectedStatus: 400,
                    expectedError: 'Bad Request',
                },
                {
                    params: { start_time: 'invalid-date' }, // Invalid date format
                    expectedStatus: 400,
                    expectedError: 'Bad Request',
                },
                {
                    params: { offset: -10 }, // Invalid offset
                    expectedStatus: 400,
                    expectedError: 'Bad Request',
                },
            ];

            // Mock error responses
            errorScenarios.forEach(scenario => {
                mockFetch.mockResolvedValueOnce({
                    ok: false,
                    status: scenario.expectedStatus,
                    statusText: scenario.expectedError,
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => ({
                        detail: `Invalid parameter: ${Object.keys(scenario.params)[0]}`,
                    }),
                });
            });

            // Test error scenarios
            for (const scenario of errorScenarios) {
                try {
                    await api.searchLogs(scenario.params);
                    expect.fail(`Should have thrown error for params: ${JSON.stringify(scenario.params)}`);
                } catch (error: any) {
                    // Verify error is reflected immediately
                    expect(error.status).toBe(scenario.expectedStatus);
                    expect(error.statusText).toBe(scenario.expectedError);
                    expect(error.data).toHaveProperty('detail');
                }
            }
        });
    });
});