import React from 'react';
import { render, screen } from '@testing-library/react';
import { CredentialBadge } from './CredentialBadge';
import { useCredentialStatus } from '../hooks/useCredentialStatus';

// Mock the useCredentialStatus hook
jest.mock('../hooks/useCredentialStatus');

const mockUseCredentialStatus = useCredentialStatus as jest.MockedFunction<
  typeof useCredentialStatus
>;

describe('CredentialBadge', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should show loading state initially', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: null,
      loading: true,
      error: null,
      timeRemaining: null,
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should show error state when there is an error', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: null,
      loading: false,
      error: 'Network error',
      timeRemaining: null,
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('should show "No Credentials" when credentials are not present', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: false,
        expired: false,
      },
      loading: false,
      error: null,
      timeRemaining: null,
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText('No Credentials')).toBeInTheDocument();
  });

  it('should show "Credentials Expired" when credentials have expired', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: true,
        account_id: '123456789012',
      },
      loading: false,
      error: null,
      timeRemaining: null,
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText('Credentials Expired')).toBeInTheDocument();
  });

  it('should show active status with green color when time remaining > 10 minutes', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: false,
        account_id: '123456789012',
      },
      loading: false,
      error: null,
      timeRemaining: 900, // 15 minutes
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText(/Active \(15m\)/)).toBeInTheDocument();
  });

  it('should show warning status with orange color when time remaining < 10 minutes', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: false,
        account_id: '123456789012',
      },
      loading: false,
      error: null,
      timeRemaining: 300, // 5 minutes
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText(/Active \(5m\)/)).toBeInTheDocument();
  });

  it('should format time correctly for seconds only (rounded to minutes)', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: false,
      },
      loading: false,
      error: null,
      timeRemaining: 45,
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText(/Active \(0m\)/)).toBeInTheDocument();
  });

  it('should format time correctly for hours and minutes', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: false,
      },
      loading: false,
      error: null,
      timeRemaining: 3900, // 1 hour 5 minutes
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText(/Active \(1h 5m\)/)).toBeInTheDocument();
  });

  it('should show active status without time when timeRemaining is null', () => {
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: false,
        account_id: '123456789012',
      },
      loading: false,
      error: null,
      timeRemaining: null,
      refresh: jest.fn(),
    });

    render(<CredentialBadge />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });
});
