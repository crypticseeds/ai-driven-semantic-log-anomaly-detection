import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ErrorState, NetworkError, APIError, DataError } from './error-state';

describe('ErrorState Component', () => {
    it('should render basic error state', () => {
        render(<ErrorState error="Test error message" />);
        
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
        expect(screen.getByText('An unexpected error occurred.')).toBeInTheDocument();
    });

    it('should render network error with correct icon and message', () => {
        render(<ErrorState error="Network connection failed" errorType="network" />);
        
        expect(screen.getByText('Connection Problem')).toBeInTheDocument();
        expect(screen.getByText('Unable to connect to the server. Please check your internet connection.')).toBeInTheDocument();
    });

    it('should render compact error state', () => {
        render(<ErrorState error="Test error" compact />);
        
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
        expect(screen.getByText('An unexpected error occurred.')).toBeInTheDocument();
    });

    it('should call onRetry when retry button is clicked', () => {
        const mockRetry = vi.fn();
        render(<ErrorState error="Test error" onRetry={mockRetry} />);
        
        const retryButton = screen.getByRole('button', { name: /try again/i });
        fireEvent.click(retryButton);
        
        expect(mockRetry).toHaveBeenCalledTimes(1);
    });

    it('should show retrying state', () => {
        render(<ErrorState error="Test error" onRetry={() => {}} retrying />);
        
        expect(screen.getByText('Retrying...')).toBeInTheDocument();
    });

    it('should detect error type from error message', () => {
        render(<ErrorState error={new Error('Network error: connection failed')} />);
        
        expect(screen.getByText('Connection Problem')).toBeInTheDocument();
    });
});

describe('Specialized Error Components', () => {
    it('should render NetworkError correctly', () => {
        render(<NetworkError />);
        
        expect(screen.getByText('Connection Problem')).toBeInTheDocument();
    });

    it('should render APIError correctly', () => {
        const mockRetry = vi.fn();
        render(<APIError error="API failed" onRetry={mockRetry} />);
        
        expect(screen.getByText('Service Error')).toBeInTheDocument();
        
        const retryButton = screen.getByRole('button');
        fireEvent.click(retryButton);
        expect(mockRetry).toHaveBeenCalledTimes(1);
    });

    it('should render DataError correctly', () => {
        render(<DataError error="Invalid data format" />);
        
        expect(screen.getByText('Data Error')).toBeInTheDocument();
    });
});