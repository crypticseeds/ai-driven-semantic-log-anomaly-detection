/**
 * Property tests for data rendering consistency
 * Validates Requirements 1.3, 2.2
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
import { api, VolumeData, VolumeResponse } from './api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('Data Rendering Consistency Properties', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Reset console methods
        vi.spyOn(console, 'log').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    describe('Property 2: Data Rendering Consistency', () => {
        it('should maintain consistent data structure across multiple API calls', async () => {
            // Property: Multiple calls to the same endpoint should return consistent structure
            const mockVolumeResponse: VolumeResponse = {
                volume_data: [
                    {
                        timestamp: '2023-12-17T10:00:00Z',
                        count: 150,
                        level_breakdown: {
                            ERROR: 10,
                            WARN: 25,
                            INFO: 100,
                            DEBUG: 15,
                        },
                    },
                    {
                        timestamp: '2023-12-17T10:05:00Z',
                        count: 200,
                        level_breakdown: {
                            ERROR: 15,
                            WARN: 30,
                            INFO: 140,
                            DEBUG: 15,
                        },
                    },
                ],
                total_logs: 350,
                time_range: {
                    start_time: '2023-12-17T10:00:00Z',
                    end_time: '2023-12-17T11:00:00Z',
                    hours: 1,
                    bucket_minutes: 5,
                },
                filters: {
                    level: undefined,
                    service: undefined,
                },
            };

            // Mock multiple identical responses
            for (let i = 0; i < 3; i++) {
                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => mockVolumeResponse,
                });
            }

            // Make multiple calls
            const results = await Promise.all([
                api.getLogVolume(),
                api.getLogVolume(),
                api.getLogVolume(),
            ]);

            // Verify all results have identical structure
            for (let i = 1; i < results.length; i++) {
                expect(results[i]).toEqual(results[0]);
            }

            // Verify consistent data structure properties
            results.forEach((result, index) => {
                expect(result).toHaveProperty('volume_data');
                expect(result).toHaveProperty('total_logs');
                expect(result).toHaveProperty('time_range');
                expect(result).toHaveProperty('filters');
                
                expect(Array.isArray(result.volume_data)).toBe(true);
                expect(typeof result.total_logs).toBe('number');
                expect(typeof result.time_range).toBe('object');
                expect(typeof result.filters).toBe('object');
                
                // Verify each volume data point has consistent structure
                result.volume_data.forEach((dataPoint, pointIndex) => {
                    expect(dataPoint).toHaveProperty('timestamp');
                    expect(dataPoint).toHaveProperty('count');
                    expect(dataPoint).toHaveProperty('level_breakdown');
                    
                    expect(typeof dataPoint.timestamp).toBe('string');
                    expect(typeof dataPoint.count).toBe('number');
                    expect(typeof dataPoint.level_breakdown).toBe('object');
                    
                    // Verify level breakdown structure
                    expect(dataPoint.level_breakdown).toHaveProperty('ERROR');
                    expect(dataPoint.level_breakdown).toHaveProperty('WARN');
                    expect(dataPoint.level_breakdown).toHaveProperty('INFO');
                    expect(dataPoint.level_breakdown).toHaveProperty('DEBUG');
                });
            });
        });

        it('should handle empty data consistently', async () => {
            // Property: Empty data should be represented consistently
            const emptyVolumeResponse: VolumeResponse = {
                volume_data: [],
                total_logs: 0,
                time_range: {
                    start_time: '2023-12-17T10:00:00Z',
                    end_time: '2023-12-17T11:00:00Z',
                    hours: 1,
                    bucket_minutes: 5,
                },
                filters: {
                    level: undefined,
                    service: undefined,
                },
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => emptyVolumeResponse,
            });

            const result = await api.getLogVolume();

            // Verify empty data structure is consistent
            expect(result.volume_data).toEqual([]);
            expect(result.total_logs).toBe(0);
            expect(result.time_range).toBeDefined();
            expect(result.filters).toBeDefined();
            
            // Should not have undefined or null values in required fields
            expect(result.volume_data).not.toBeNull();
            expect(result.volume_data).not.toBeUndefined();
            expect(result.total_logs).not.toBeNull();
            expect(result.total_logs).not.toBeUndefined();
        });

        it('should maintain data type consistency across different parameter combinations', async () => {
            // Property: Different query parameters should not affect data structure consistency
            const baseResponse: VolumeResponse = {
                volume_data: [
                    {
                        timestamp: '2023-12-17T10:00:00Z',
                        count: 100,
                        level_breakdown: {
                            ERROR: 5,
                            WARN: 15,
                            INFO: 70,
                            DEBUG: 10,
                        },
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

            const parameterCombinations = [
                { hours: 1, bucket_minutes: 5 },
                { hours: 2, bucket_minutes: 10, level: 'ERROR' },
                { hours: 6, bucket_minutes: 30, service: 'test-service' },
                { hours: 12, bucket_minutes: 60, level: 'INFO', service: 'another-service' },
            ];

            // Mock responses for each parameter combination
            parameterCombinations.forEach(() => {
                mockFetch.mockResolvedValueOnce({
                    ok: true,
                    status: 200,
                    statusText: 'OK',
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => ({
                        ...baseResponse,
                        filters: {}, // Filters will vary but structure should be consistent
                    }),
                });
            });

            // Test each parameter combination
            const results = await Promise.all(
                parameterCombinations.map(params => api.getLogVolume(params))
            );

            // Verify all results have consistent structure regardless of parameters
            results.forEach((result, index) => {
                const params = parameterCombinations[index];
                
                // Structure should be identical
                expect(result).toHaveProperty('volume_data');
                expect(result).toHaveProperty('total_logs');
                expect(result).toHaveProperty('time_range');
                expect(result).toHaveProperty('filters');
                
                // Data types should be consistent
                expect(Array.isArray(result.volume_data)).toBe(true);
                expect(typeof result.total_logs).toBe('number');
                expect(typeof result.time_range).toBe('object');
                expect(typeof result.filters).toBe('object');
                
                // Time range should have consistent structure
                expect(result.time_range).toHaveProperty('start_time');
                expect(result.time_range).toHaveProperty('end_time');
                expect(result.time_range).toHaveProperty('hours');
                expect(result.time_range).toHaveProperty('bucket_minutes');
                
                expect(typeof result.time_range.start_time).toBe('string');
                expect(typeof result.time_range.end_time).toBe('string');
                expect(typeof result.time_range.hours).toBe('number');
                expect(typeof result.time_range.bucket_minutes).toBe('number');
            });
        });

        it('should handle numeric data consistently without precision loss', async () => {
            // Property: Numeric data should maintain precision and type consistency
            const precisionTestResponse: VolumeResponse = {
                volume_data: [
                    {
                        timestamp: '2023-12-17T10:00:00Z',
                        count: 999999,
                        level_breakdown: {
                            ERROR: 123456,
                            WARN: 234567,
                            INFO: 345678,
                            DEBUG: 296298,
                        },
                    },
                    {
                        timestamp: '2023-12-17T10:05:00Z',
                        count: 0,
                        level_breakdown: {
                            ERROR: 0,
                            WARN: 0,
                            INFO: 0,
                            DEBUG: 0,
                        },
                    },
                ],
                total_logs: 999999,
                time_range: {
                    start_time: '2023-12-17T10:00:00Z',
                    end_time: '2023-12-17T11:00:00Z',
                    hours: 24,
                    bucket_minutes: 60,
                },
                filters: {},
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => precisionTestResponse,
            });

            const result = await api.getLogVolume();

            // Verify large numbers are handled correctly
            expect(result.total_logs).toBe(999999);
            expect(result.volume_data[0].count).toBe(999999);
            expect(result.volume_data[0].level_breakdown.ERROR).toBe(123456);
            
            // Verify zero values are handled correctly
            expect(result.volume_data[1].count).toBe(0);
            expect(result.volume_data[1].level_breakdown.ERROR).toBe(0);
            
            // Verify all numeric values are actually numbers, not strings
            expect(typeof result.total_logs).toBe('number');
            result.volume_data.forEach(dataPoint => {
                expect(typeof dataPoint.count).toBe('number');
                expect(typeof dataPoint.level_breakdown.ERROR).toBe('number');
                expect(typeof dataPoint.level_breakdown.WARN).toBe('number');
                expect(typeof dataPoint.level_breakdown.INFO).toBe('number');
                expect(typeof dataPoint.level_breakdown.DEBUG).toBe('number');
            });
        });

        it('should handle timestamp formatting consistently', async () => {
            // Property: Timestamp formats should be consistent and parseable
            const timestampTestResponse: VolumeResponse = {
                volume_data: [
                    {
                        timestamp: '2023-12-17T10:00:00Z',
                        count: 100,
                        level_breakdown: { ERROR: 0, WARN: 0, INFO: 100, DEBUG: 0 },
                    },
                    {
                        timestamp: '2023-12-17T10:05:00.000Z',
                        count: 150,
                        level_breakdown: { ERROR: 5, WARN: 10, INFO: 130, DEBUG: 5 },
                    },
                    {
                        timestamp: '2023-12-17T10:10:00+00:00',
                        count: 200,
                        level_breakdown: { ERROR: 10, WARN: 20, INFO: 160, DEBUG: 10 },
                    },
                ],
                total_logs: 450,
                time_range: {
                    start_time: '2023-12-17T10:00:00Z',
                    end_time: '2023-12-17T11:00:00Z',
                    hours: 1,
                    bucket_minutes: 5,
                },
                filters: {},
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => timestampTestResponse,
            });

            const result = await api.getLogVolume();

            // Verify all timestamps are strings and parseable as dates
            result.volume_data.forEach(dataPoint => {
                expect(typeof dataPoint.timestamp).toBe('string');
                
                // Should be parseable as a valid date
                const date = new Date(dataPoint.timestamp);
                expect(date.getTime()).not.toBeNaN();
                expect(date instanceof Date).toBe(true);
            });

            // Verify time range timestamps are also consistent
            expect(typeof result.time_range.start_time).toBe('string');
            expect(typeof result.time_range.end_time).toBe('string');
            
            const startDate = new Date(result.time_range.start_time);
            const endDate = new Date(result.time_range.end_time);
            expect(startDate.getTime()).not.toBeNaN();
            expect(endDate.getTime()).not.toBeNaN();
            expect(endDate.getTime()).toBeGreaterThan(startDate.getTime());
        });

        it('should maintain consistent error response structure', async () => {
            // Property: Error responses should have consistent structure for reliable error handling
            const errorScenarios = [
                { status: 400, statusText: 'Bad Request', errorData: { detail: 'Invalid parameters' } },
                { status: 404, statusText: 'Not Found', errorData: { detail: 'Endpoint not found' } },
                { status: 500, statusText: 'Internal Server Error', errorData: { detail: 'Server error' } },
            ];

            for (const scenario of errorScenarios) {
                mockFetch.mockResolvedValueOnce({
                    ok: false,
                    status: scenario.status,
                    statusText: scenario.statusText,
                    headers: new Headers({
                        'content-type': 'application/json',
                    }),
                    json: async () => scenario.errorData,
                });

                try {
                    await api.getLogVolume();
                    expect.fail(`Should have thrown error for status ${scenario.status}`);
                } catch (error: any) {
                    // Verify error structure is consistent for APIError
                    expect(error.name).toBe('APIError');
                    expect(error.status).toBe(scenario.status);
                    expect(error.statusText).toBe(scenario.statusText);
                    expect(error.data).toHaveProperty('detail');
                    expect(error.data).toHaveProperty('requestId');
                    expect(error.data).toHaveProperty('responseTime');
                    expect(error.data).toHaveProperty('endpoint');
                }
            }
        });

        it('should handle partial data gracefully with consistent fallbacks', async () => {
            // Property: Partial or malformed data should be handled with consistent fallback behavior
            const partialDataResponse = {
                volume_data: [
                    {
                        timestamp: '2023-12-17T10:00:00Z',
                        count: 100,
                        // Missing level_breakdown
                    },
                    {
                        timestamp: '2023-12-17T10:05:00Z',
                        // Missing count
                        level_breakdown: { ERROR: 5, WARN: 10, INFO: 80, DEBUG: 5 },
                    },
                    {
                        // Missing timestamp
                        count: 200,
                        level_breakdown: { ERROR: 10, WARN: 20, INFO: 160, DEBUG: 10 },
                    },
                ],
                total_logs: 300,
                // Missing time_range and filters
            };

            mockFetch.mockResolvedValueOnce({
                ok: true,
                status: 200,
                statusText: 'OK',
                headers: new Headers({
                    'content-type': 'application/json',
                }),
                json: async () => partialDataResponse,
            });

            const result = await api.getLogVolume();

            // Should still return a valid structure
            expect(result).toHaveProperty('volume_data');
            expect(result).toHaveProperty('total_logs');
            expect(Array.isArray(result.volume_data)).toBe(true);
            expect(typeof result.total_logs).toBe('number');

            // Should handle missing fields gracefully
            expect(result.total_logs).toBe(300);
            expect(result.volume_data).toHaveLength(3);
        });
    });
});