import { renderHook, act, waitFor } from '@testing-library/react';
import { useWeather } from './useWeather';
import apiClient from '../services/api';
import { WeatherData } from '../types/weather';

// Mock the API client
jest.mock('../services/api');

const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

describe('useWeather', () => {
  const selectedCluster = 'dev-cluster-1';
  const isAuthenticated = true;

  const mockWeatherData: WeatherData = {
    state: 'partly-cloudy',
    clusterName: 'dev-cluster-1',
    clusterVersion: '1.28',
    k8sgptResultCount: 3,
    topIssues: [
      {
        name: 'pod-1',
        kind: 'Pod',
        namespace: 'default',
        severity: 'medium',
        problem: 'Pod is pending',
        solution: 'Check node resources',
        analyzer: 'PodAnalyzer',
        timestamp: '2024-01-01T00:00:00Z',
      },
    ],
    clusterTools: [
      {
        name: 'k8sgpt',
        version: '0.3.0',
      },
    ],
    timestamp: '2024-01-01T00:00:00Z',
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('initial fetch', () => {
    it('should fetch weather data when cluster is selected and authenticated', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      await waitFor(() => {
        expect(result.current.weatherData).toEqual(mockWeatherData);
      });

      expect(mockApiClient.get).toHaveBeenCalledWith('/weather');
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('should not fetch weather when not authenticated', () => {
      renderHook(() => useWeather(selectedCluster, false));

      // Advance timers to ensure no polling happens
      act(() => {
        jest.advanceTimersByTime(1000);
      });

      expect(mockApiClient.get).not.toHaveBeenCalled();
    });

    it('should not fetch weather when no cluster is selected', () => {
      renderHook(() => useWeather(null, isAuthenticated));

      // Advance timers to ensure no polling happens
      act(() => {
        jest.advanceTimersByTime(1000);
      });

      expect(mockApiClient.get).not.toHaveBeenCalled();
    });

    it('should set loading state during initial fetch', async () => {
      mockApiClient.get.mockImplementation(() =>
        new Promise(resolve =>
          setTimeout(() => resolve({ data: mockWeatherData }), 100)
        )
      );

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Should be loading initially
      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.weatherData).toEqual(mockWeatherData);
    });

    it('should handle fetch errors gracefully', async () => {
      mockApiClient.get.mockRejectedValue({
        response: {
          status: 500,
          data: {
            detail: 'Failed to read K8sGPT Results',
          },
        },
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      await waitFor(() => {
        expect(result.current.error).toBe('Failed to read K8sGPT Results');
      });

      expect(result.current.weatherData).toBeNull();
    });

    it('should handle 401 authentication errors', async () => {
      mockApiClient.get.mockRejectedValue({
        response: {
          status: 401,
        },
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      await waitFor(() => {
        expect(result.current.error).toBe('Authentication required');
      });
    });

    it('should handle 404 no cluster errors', async () => {
      mockApiClient.get.mockRejectedValue({
        response: {
          status: 404,
        },
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      await waitFor(() => {
        expect(result.current.error).toBe('No cluster selected');
      });
    });
  });

  describe('polling', () => {
    it('should poll weather data every 60 seconds', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch to complete
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalled();
      });

      // Clear the mock to start counting from here
      mockApiClient.get.mockClear();

      // Advance time by 60 seconds
      act(() => {
        jest.advanceTimersByTime(60000);
      });

      // Should have polled once
      await waitFor(() => {
        expect(mockApiClient.get.mock.calls.length).toBeGreaterThanOrEqual(1);
      });

      const callsAfterFirstPoll = mockApiClient.get.mock.calls.length;

      // Advance time by another 60 seconds
      act(() => {
        jest.advanceTimersByTime(60000);
      });

      // Should have polled again
      await waitFor(() => {
        expect(mockApiClient.get.mock.calls.length).toBeGreaterThan(callsAfterFirstPoll);
      });
    });

    it('should stop polling when cluster is deselected', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { rerender } = renderHook(
        ({ cluster, auth }) => useWeather(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      // Initial fetch
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(1);
      });

      // Deselect cluster
      rerender({ cluster: null, auth: isAuthenticated });

      // Advance time by 60 seconds
      act(() => {
        jest.advanceTimersByTime(60000);
      });

      // Should not have made another call
      expect(mockApiClient.get).toHaveBeenCalledTimes(1);
    });

    it('should stop polling when authentication is lost', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { rerender } = renderHook(
        ({ cluster, auth }) => useWeather(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      // Initial fetch
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(1);
      });

      // Lose authentication
      rerender({ cluster: selectedCluster, auth: false });

      // Advance time by 60 seconds
      act(() => {
        jest.advanceTimersByTime(60000);
      });

      // Should not have made another call
      expect(mockApiClient.get).toHaveBeenCalledTimes(1);
    });

    it('should restart polling when cluster changes', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { rerender } = renderHook(
        ({ cluster, auth }) => useWeather(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      // Initial fetch
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(1);
      });

      // Change cluster
      rerender({ cluster: 'staging-cluster-1', auth: isAuthenticated });

      // Should fetch immediately for new cluster
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(2);
      });

      // Advance time by 60 seconds
      act(() => {
        jest.advanceTimersByTime(60000);
      });

      // Should poll again
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(3);
      });
    });
  });

  describe('manual refresh', () => {
    it('should refresh weather data manually', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch to complete
      await waitFor(() => {
        expect(result.current.weatherData).toEqual(mockWeatherData);
      });

      // Clear the mock to start counting from here
      mockApiClient.get.mockClear();

      // Manual refresh
      await act(async () => {
        await result.current.refresh();
      });

      // Should have called the API at least once for the manual refresh
      expect(mockApiClient.get.mock.calls.length).toBeGreaterThanOrEqual(1);
    });

    it('should set refreshing state during manual refresh', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch
      await waitFor(() => {
        expect(result.current.weatherData).toEqual(mockWeatherData);
      });

      // Manual refresh with delay
      mockApiClient.get.mockImplementation(() =>
        new Promise(resolve =>
          setTimeout(() => resolve({ data: mockWeatherData }), 100)
        )
      );

      act(() => {
        result.current.refresh();
      });

      // Should be refreshing
      expect(result.current.isRefreshing).toBe(true);

      await waitFor(() => {
        expect(result.current.isRefreshing).toBe(false);
      });
    });

    it('should not set loading state during manual refresh', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch
      await waitFor(() => {
        expect(result.current.weatherData).toEqual(mockWeatherData);
      });

      // Manual refresh
      await act(async () => {
        await result.current.refresh();
      });

      // isLoading should remain false during manual refresh
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe('previous weather data preservation', () => {
    it('should preserve previous weather data during refresh', async () => {
      const initialWeatherData: WeatherData = {
        ...mockWeatherData,
        state: 'sunny',
        k8sgptResultCount: 0,
      };

      const updatedWeatherData: WeatherData = {
        ...mockWeatherData,
        state: 'cloudy',
        k8sgptResultCount: 5,
      };

      mockApiClient.get.mockResolvedValueOnce({
        data: initialWeatherData,
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch
      await waitFor(() => {
        expect(result.current.weatherData).toEqual(initialWeatherData);
      });

      expect(result.current.previousWeatherData).toBeNull();

      // Update weather data
      mockApiClient.get.mockResolvedValueOnce({
        data: updatedWeatherData,
      });

      await act(async () => {
        await result.current.refresh();
      });

      // Previous data should be preserved
      expect(result.current.previousWeatherData).toEqual(initialWeatherData);
      expect(result.current.weatherData).toEqual(updatedWeatherData);
    });

    it('should clear previous data when cluster is deselected', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { result, rerender } = renderHook(
        ({ cluster, auth }) => useWeather(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      // Wait for initial fetch
      await waitFor(() => {
        expect(result.current.weatherData).toEqual(mockWeatherData);
      });

      // Deselect cluster
      rerender({ cluster: null, auth: isAuthenticated });

      await waitFor(() => {
        expect(result.current.weatherData).toBeNull();
        expect(result.current.previousWeatherData).toBeNull();
      });
    });
  });

  describe('weather state transitions', () => {
    it('should handle weather state changes from sunny to stormy', async () => {
      const sunnyWeather: WeatherData = {
        ...mockWeatherData,
        state: 'sunny',
        k8sgptResultCount: 0,
        topIssues: [],
      };

      const stormyWeather: WeatherData = {
        ...mockWeatherData,
        state: 'stormy',
        k8sgptResultCount: 15,
        topIssues: [
          {
            name: 'pod-1',
            kind: 'Pod',
            namespace: 'default',
            severity: 'high',
            problem: 'Pod is crashing',
            solution: 'Check logs',
            analyzer: 'PodAnalyzer',
            timestamp: '2024-01-01T00:00:00Z',
          },
        ],
      };

      mockApiClient.get.mockResolvedValueOnce({
        data: sunnyWeather,
      });

      const { result } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch
      await waitFor(() => {
        expect(result.current.weatherData?.state).toBe('sunny');
      });

      // Update to stormy
      mockApiClient.get.mockResolvedValueOnce({
        data: stormyWeather,
      });

      await act(async () => {
        await result.current.refresh();
      });

      expect(result.current.weatherData?.state).toBe('stormy');
      expect(result.current.previousWeatherData?.state).toBe('sunny');
    });
  });

  describe('cleanup', () => {
    it('should cleanup polling interval on unmount', async () => {
      mockApiClient.get.mockResolvedValue({
        data: mockWeatherData,
      });

      const { unmount } = renderHook(() => useWeather(selectedCluster, isAuthenticated));

      // Wait for initial fetch
      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledTimes(1);
      });

      // Unmount
      unmount();

      // Advance time by 60 seconds
      act(() => {
        jest.advanceTimersByTime(60000);
      });

      // Should not have made another call after unmount
      expect(mockApiClient.get).toHaveBeenCalledTimes(1);
    });
  });
});
