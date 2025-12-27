/**
 * Tests for API client response transformation
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock the API module to test the transformation function
// We need to access the internal transformation function for testing
const mockBackendResponse = {
    results: [
        {
            id: "test-id-1",
            timestamp: "2024-01-15T10:30:00Z",
            level: "INFO",
            service: "test-service",
            message: "Test log message",
            metadata: { key: "value" }
        }
    ],
    total: 1,
    limit: 100,
    offset: 0,
    has_more: false,
    search_type: "text"
};

const mockInvalidResponse = {
    logs: [  // Wrong field name
        {
            id: "test-id-1",
            timestamp: "2024-01-15T10:30:00Z",
            level: "INFO",
            service: "test-service",
            message: "Test log message"
        }
    ],
    total: 1,
    limit: 100,
    offset: 0
};

// Since the transformation function is not exported, we'll test it through the API
// This is an integration test that verifies the transformation works end-to-end
describe('API Response Transformation', () => {
    beforeEach(() => {
        // Reset any mocks
        vi.clearAllMocks();
        
        // Mock console methods to avoid noise in tests
        vi.spyOn(console, 'log').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    it('should handle volume API response correctly', async () => {
        const mockVolumeResponse = {
            volume_data: [
                {
                    timestamp: "2024-01-15T10:30:00Z",
                    count: 25,
                    level_breakdown: {
                        ERROR: 2,
                        WARN: 5,
                        INFO: 15,
                        DEBUG: 3
                    }
                },
                {
                    timestamp: "2024-01-15T10:35:00Z",
                    count: 18,
                    level_breakdown: {
                        ERROR: 1,
                        WARN: 3,
                        INFO: 12,
                        DEBUG: 2
                    }
                }
            ],
            total_logs: 43,
            time_range: {
                start_time: "2024-01-15T10:30:00Z",
                end_time: "2024-01-15T11:30:00Z",
                hours: 1,
                bucket_minutes: 5
            },
            filters: {
                level: null,
                service: null
            }
        };

        // Mock fetch to return our test data
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Headers({
                'content-type': 'application/json'
            }),
            json: async () => mockVolumeResponse
        });

        const { api } = await import('./api');
        const result = await api.getLogVolume({ hours: 1, bucket_minutes: 5 });

        expect(result).toEqual(mockVolumeResponse);
        expect(result.volume_data).toHaveLength(2);
        expect(result.total_logs).toBe(43);
        expect(result.volume_data[0].count).toBe(25);
        expect(result.volume_data[0].level_breakdown?.ERROR).toBe(2);
    });

    it('should handle backend response with results field', async () => {
        // Mock fetch to return the backend format
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: () => Promise.resolve(mockBackendResponse)
        });

        const { api } = await import('./api');
        
        const result = await api.searchLogs({ limit: 100 });
        
        expect(result).toHaveProperty('logs');
        expect(result.logs).toHaveLength(1);
        expect(result.logs[0]).toMatchObject({
            id: "test-id-1",
            level: "INFO",
            service: "test-service",
            message: "Test log message"
        });
        expect(result.total).toBe(1);
        expect(result.limit).toBe(100);
        expect(result.offset).toBe(0);
    });

    it('should handle backend response with logs field (backward compatibility)', async () => {
        // Mock fetch to return response with 'logs' instead of 'results'
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: () => Promise.resolve(mockInvalidResponse)
        });

        const { api } = await import('./api');
        
        const result = await api.searchLogs({ limit: 100 });
        
        // Should still work by using the 'logs' field
        expect(result).toHaveProperty('logs');
        expect(result.logs).toHaveLength(1);
        expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining('Backend returned logs field instead of results')
        );
    });

    it('should handle malformed log entries gracefully', async () => {
        const malformedResponse = {
            results: [
                {
                    id: "valid-id",
                    timestamp: "2024-01-15T10:30:00Z",
                    level: "INFO",
                    service: "test-service",
                    message: "Valid log"
                },
                {
                    // Missing required fields
                    id: "",
                    level: "ERROR"
                    // Missing timestamp, service, message
                },
                null, // Invalid entry
                {
                    id: "another-valid-id",
                    timestamp: "2024-01-15T10:31:00Z",
                    level: "WARN",
                    service: "another-service",
                    message: "Another valid log"
                }
            ],
            total: 3,
            limit: 100,
            offset: 0
        };

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: () => Promise.resolve(malformedResponse)
        });

        const { api } = await import('./api');
        
        const result = await api.searchLogs({ limit: 100 });
        
        // Should return valid entries (including the one with fallback values)
        expect(result.logs.length).toBeGreaterThanOrEqual(2);
        expect(result.logs[0].id).toBe("valid-id");
        expect(result.logs.find(log => log.id === "another-valid-id")).toBeDefined();
        
        // Should have logged warnings about invalid entries
        expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining('missing valid id field')
        );
    });

    it('should handle completely invalid response format', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: () => Promise.resolve("invalid response")
        });

        const { api } = await import('./api');
        
        try {
            await api.searchLogs({ limit: 100 });
            expect.fail('Expected API call to throw an error');
        } catch (error: unknown) {
            expect(error).toBeInstanceOf(Error);
            if (error instanceof Error) {
                expect(error.message).toContain('API Response Format Error');
            }
        }
    });

    it('should handle network errors with helpful messages', async () => {
        global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

        const { api } = await import('./api');
        
        await expect(api.searchLogs({ limit: 100 })).rejects.toThrow(
            'Network error: Unable to connect to http://localhost:8000. This is likely a CORS or connectivity issue.'
        );
    });

    it('should handle API errors with enhanced context', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 500,
            statusText: 'Internal Server Error',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: () => Promise.resolve({ detail: 'Database connection failed' })
        });

        const { api } = await import('./api');
        
        await expect(api.searchLogs({ limit: 100 })).rejects.toThrow(/API Error: 500/);
    });
});