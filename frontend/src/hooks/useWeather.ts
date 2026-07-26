import { useState, useCallback, useEffect, useRef } from 'react';
import { WeatherData } from '../types/weather';
import apiClient from '../services/api';
import { formatApiError, toApiError } from '../utils/apiError';

const WEATHER_POLL_INTERVAL = 60000; // 60 seconds

export interface UseWeatherState {
  weatherData: WeatherData | null;
  previousWeatherData: WeatherData | null;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * React hook to manage weather polling and state updates
 * 
 * Features:
 * - Poll weather endpoint every 60 seconds
 * - Calculate weather state from K8sGPT Results
 * - Preserve previous data during refresh to prevent flicker
 * - Handle weather data caching
 * - Auto-refresh when cluster changes
 * 
 * Requirements: 3.1, 3.2, 3.3
 */
export const useWeather = (
  selectedCluster: string | null,
  isAuthenticated: boolean
): UseWeatherState => {
  const [weatherData, setWeatherData] = useState<WeatherData | null>(null);
  const [previousWeatherData, setPreviousWeatherData] = useState<WeatherData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Fetch weather data from backend
   * Backend reads K8sGPT Result CRDs and calculates weather state
   */
  const fetchWeather = useCallback(async (isManualRefresh: boolean = false) => {
    if (!isAuthenticated || !selectedCluster) {
      return;
    }

    // Set appropriate loading state
    if (isManualRefresh) {
      setIsRefreshing(true);
    } else if (!weatherData) {
      setIsLoading(true);
    }

    setError(null);

    try {
      const response = await apiClient.get('/weather');
      const data: WeatherData = response.data;

      // Preserve previous data before updating
      if (weatherData) {
        setPreviousWeatherData(weatherData);
      }

      setWeatherData(data);
    } catch (err: unknown) {
      const apiErr = toApiError(err);
      setError(formatApiError(apiErr));
      console.error('Failed to fetch weather:', apiErr);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [isAuthenticated, selectedCluster, weatherData]);

  /**
   * Manual refresh trigger
   */
  const refresh = useCallback(async () => {
    await fetchWeather(true);
  }, [fetchWeather]);

  /**
   * Set up polling interval when cluster is selected
   */
  useEffect(() => {
    // Clear existing interval
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    // Clear weather data when cluster is deselected or user logs out
    if (!selectedCluster || !isAuthenticated) {
      setWeatherData(null);
      setPreviousWeatherData(null);
      setError(null);
      return;
    }

    // Initial fetch
    fetchWeather(false);

    // Set up polling interval
    pollIntervalRef.current = setInterval(() => {
      fetchWeather(false);
    }, WEATHER_POLL_INTERVAL);

    // Cleanup on unmount or when dependencies change
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [selectedCluster, isAuthenticated, fetchWeather]);

  return {
    weatherData,
    previousWeatherData,
    isLoading,
    isRefreshing,
    error,
    refresh,
  };
};
