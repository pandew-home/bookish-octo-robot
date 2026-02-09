import { renderHook, act, waitFor } from '@testing-library/react';
import { useCredentials } from './useCredentials';
import { authApi } from '../services/api';
import { useCredentialStatus } from './useCredentialStatus';

// Mock the dependencies
jest.mock('../services/api');
jest.mock('./useCredentialStatus');

const mockAuthApi = authApi as jest.Mocked<typeof authApi>;
const mockUseCredentialStatus = useCredentialStatus as jest.MockedFunction<typeof useCredentialStatus>;

describe('useCredentials', () => {
  const mockRefresh = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Default mock implementation
    mockUseCredentialStatus.mockReturnValue({
      status: null,
      loading: false,
      error: null,
      timeRemaining: null,
      refresh: mockRefresh,
    });
  });

  describe('login', () => {
    it('should successfully authenticate with valid credentials', async () => {
      mockAuthApi.login.mockResolvedValue({
        success: true,
        sessionId: 'test-session-id',
      });

      const { result } = renderHook(() => useCredentials());

      await act(async () => {
        await result.current.login({
          accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
          secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
          sessionToken: 'test-session-token',
          region: 'us-east-1',
        });
      });

      expect(mockAuthApi.login).toHaveBeenCalledWith({
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'test-session-token',
        region: 'us-east-1',
      });
      expect(mockRefresh).toHaveBeenCalled();
    });

    it('should handle authentication failure', async () => {
      const errorMessage = 'Invalid credentials';
      mockAuthApi.login.mockRejectedValue({
        response: {
          data: {
            detail: errorMessage,
          },
        },
      });

      const { result } = renderHook(() => useCredentials());

      let caughtErrorMessage: string | null = null;
      
      await act(async () => {
        try {
          await result.current.login({
            accessKeyId: 'INVALID',
            secretAccessKey: 'INVALID',
            sessionToken: 'INVALID',
            region: 'us-east-1',
          });
        } catch (error: any) {
          caughtErrorMessage = error?.message ?? String(error);
        }
      });

      if (!caughtErrorMessage) {
        throw new Error('Expected login to throw');
      }

      expect(caughtErrorMessage).toBe(errorMessage);
    });

    it('should set loading state during authentication', async () => {
      mockAuthApi.login.mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({ success: true, sessionId: 'test' }), 100))
      );

      const { result } = renderHook(() => useCredentials());

      act(() => {
        result.current.login({
          accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
          secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
          sessionToken: 'test-session-token',
          region: 'us-east-1',
        });
      });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
    });
  });

  describe('logout', () => {
    it('should successfully logout', async () => {
      mockAuthApi.logout.mockResolvedValue({ success: true });

      const { result } = renderHook(() => useCredentials());

      await act(async () => {
        await result.current.logout();
      });

      expect(mockAuthApi.logout).toHaveBeenCalled();
      expect(mockRefresh).toHaveBeenCalled();
    });

    it('should handle logout failure', async () => {
      const errorMessage = 'Logout failed';
      mockAuthApi.logout.mockRejectedValue({
        response: {
          data: {
            detail: errorMessage,
          },
        },
      });

      const { result } = renderHook(() => useCredentials());

      let caughtErrorMessage: string | null = null;
      
      await act(async () => {
        try {
          await result.current.logout();
        } catch (error: any) {
          caughtErrorMessage = error?.message ?? String(error);
        }
      });

      if (!caughtErrorMessage) {
        throw new Error('Expected logout to throw');
      }

      expect(caughtErrorMessage).toBe(errorMessage);
    });
  });

  describe('authentication state', () => {
    it('should be authenticated when credentials are present and not expired', () => {
      mockUseCredentialStatus.mockReturnValue({
        status: {
          present: true,
          expired: false,
          account_id: '123456789012',
          user_arn: 'arn:aws:iam::123456789012:user/test',
        },
        loading: false,
        error: null,
        timeRemaining: 3600,
        refresh: mockRefresh,
      });

      const { result } = renderHook(() => useCredentials());

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.accountId).toBe('123456789012');
      expect(result.current.userArn).toBe('arn:aws:iam::123456789012:user/test');
    });

    it('should not be authenticated when credentials are expired', () => {
      mockUseCredentialStatus.mockReturnValue({
        status: {
          present: true,
          expired: true,
        },
        loading: false,
        error: null,
        timeRemaining: 0,
        refresh: mockRefresh,
      });

      const { result } = renderHook(() => useCredentials());

      expect(result.current.isAuthenticated).toBe(false);
    });

    it('should not be authenticated when credentials are not present', () => {
      mockUseCredentialStatus.mockReturnValue({
        status: {
          present: false,
          expired: false,
        },
        loading: false,
        error: null,
        timeRemaining: null,
        refresh: mockRefresh,
      });

      const { result } = renderHook(() => useCredentials());

      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  describe('time remaining', () => {
    it('should expose time remaining from credential status', () => {
      mockUseCredentialStatus.mockReturnValue({
        status: {
          present: true,
          expired: false,
        },
        loading: false,
        error: null,
        timeRemaining: 1800, // 30 minutes
        refresh: mockRefresh,
      });

      const { result } = renderHook(() => useCredentials());

      expect(result.current.timeRemaining).toBe(1800);
    });
  });
});
