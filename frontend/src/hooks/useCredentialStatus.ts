import { useState, useEffect, useCallback } from 'react';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export interface CredentialStatus {
  present: boolean;
  expired: boolean;
  account_id?: string;
  user_arn?: string;
  expires_at?: string;
  ttl_seconds?: number;
}

export interface CredentialStatusState {
  status: CredentialStatus | null;
  loading: boolean;
  error: string | null;
  timeRemaining: number | null; // seconds until expiry
  refresh: () => Promise<void>;
}

/**
 * React hook to poll Kion AWS credential status from backend
 * Polls every 30 seconds and calculates time remaining until expiry
 */
export const useCredentialStatus = (): CredentialStatusState => {
  const [status, setStatus] = useState<CredentialStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const sessionId = localStorage.getItem('sessionId');
      const response = await fetch(`${API_BASE_URL}/api/credentials/status`, {
        method: 'GET',
        credentials: 'include',
        headers: sessionId ? { 'x-session-id': sessionId } : {},
      });

      if (!response.ok) {
        // If 401 or 404, credentials not present
        if (response.status === 401 || response.status === 404) {
          const fallback: CredentialStatus = {
            present: false,
            expired: false,
          };
          setStatus(fallback);
          setError(null);
          setTimeRemaining(null);
          return;
        }
        throw new Error(`Status check failed: ${response.status}`);
      }

      const data = await response.json();

      // Calculate expiry
      const now = Math.floor(Date.now() / 1000);
      let expiryEpoch: number | undefined;
      let expired = false;

      if (data.expires_at) {
        expiryEpoch = Math.floor(Date.parse(data.expires_at) / 1000);
        expired = expiryEpoch <= now;
      } else if (data.ttl_seconds !== undefined) {
        // Use TTL if provided
        expiryEpoch = now + data.ttl_seconds;
        expired = data.ttl_seconds <= 0;
      }

      const mapped: CredentialStatus = {
        present: data.present === true || (data.status !== undefined && data.status !== 'no_credentials' && data.status !== 'expired'),
        expired,
        account_id: data.account_id,
        user_arn: data.user_arn,
        expires_at: data.expires_at,
        ttl_seconds: data.ttl_seconds,
      };

      setStatus(mapped);
      setError(null);

      // Calculate time remaining if credentials are present and not expired
      if (mapped.present && !mapped.expired && expiryEpoch) {
        const remaining = expiryEpoch - now;
        setTimeRemaining(remaining > 0 ? remaining : 0);
      } else {
        setTimeRemaining(null);
      }
    } catch (err: any) {
      console.error('Failed to fetch credential status:', err);
      setError(err.message || 'Failed to fetch credential status');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Poll every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchStatus();
    }, 30000);

    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Update countdown timer every second
  useEffect(() => {
    if (timeRemaining === null || timeRemaining <= 0) {
      return;
    }

    const interval = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev === null || prev <= 0) {
          return null;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [timeRemaining]);

  return {
    status,
    loading,
    error,
    timeRemaining,
    refresh: fetchStatus,
  };
};
