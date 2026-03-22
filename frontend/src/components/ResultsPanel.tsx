import React, { useState, useEffect, useMemo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Alert,
  Chip,
  Stack,
  Tabs,
  Tab,
  Divider,
  IconButton,
  Collapse,
  LinearProgress,
  Paper,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { resultsApi } from '../services/api';
import {
  K8sGPTResult,
  getSeverityColor,
  getSeverityIcon,
  getSeverityDisplayName,
} from '../types/k8sgpt';

/**
 * Props for ResultsPanel component
 */
interface ResultsPanelProps {
  /**
   * Auto-refresh interval in milliseconds (default: 60000 = 60 seconds)
   */
  refreshInterval?: number;
}

/**
 * ResultsPanel Component
 * 
 * Displays Cluster Analyzer Results with severity tabs and expandable details.
 * Fetches data from GET /api/results endpoint.
 * 
 * Features:
 * - Display Cluster Analyzer Results with severity indicators
 * - Filter by severity (tabs)
 * - Auto-refresh every 60 seconds
 * - Expandable result details
 */
export const ResultsPanel: React.FC<ResultsPanelProps> = ({
  refreshInterval = 60000,
}) => {
  // State
  const [results, setResults] = useState<K8sGPTResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set());
  
  // Severity tab state (0 = all, 1 = high, 2 = medium, 3 = low)
  const [severityTab, setSeverityTab] = useState<number>(0);

  // Filter results based on severity tabs
  const filteredResults = useMemo(() => {
    return results.filter(result => {
      // Filter by severity tab
      if (severityTab === 1 && result.severity !== 'high') return false;
      if (severityTab === 2 && result.severity !== 'medium') return false;
      if (severityTab === 3 && result.severity !== 'low') return false;
      
      return true;
    });
  }, [results, severityTab]);

  // Fetch results from API
  const fetchResults = async () => {
    try {
      setError(null);
      
      const rawData = await resultsApi.getResults();
      
      // Convert snake_case to camelCase
      const convertedResults: K8sGPTResult[] = rawData.map((item: any) => ({
        name: item.name,
        kind: item.kind,
        namespace: item.namespace,
        severity: item.severity,
        problem: item.problem,
        solution: item.solution,
        analyzer: item.analyzer,
        timestamp: item.timestamp,
        details: item.details,
      }));
      
      setResults(convertedResults);
    } catch (err: any) {
      console.error('Failed to fetch Cluster Analyzer results:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to fetch results');
    } finally {
      setLoading(false);
    }
  };

  // Auto-refresh results
  useEffect(() => {
    fetchResults();
    const interval = setInterval(fetchResults, refreshInterval);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshInterval]);

  // Handle manual refresh
  const handleRefresh = () => {
    setLoading(true);
    fetchResults();
  };

  // Handle expand/collapse result
  const toggleExpanded = (resultName: string) => {
    setExpandedResults(prev => {
      const newSet = new Set(prev);
      if (newSet.has(resultName)) {
        newSet.delete(resultName);
      } else {
        newSet.add(resultName);
      }
      return newSet;
    });
  };

  // Check if any filters are active
  // Format timestamp for display
  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  return (
    <Card>
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6" component="h2">
            Cluster Analyzer Results
          </Typography>
          <IconButton onClick={handleRefresh} disabled={loading} size="small">
            <RefreshIcon />
          </IconButton>
        </Box>

        {/* Severity Tabs */}
        <Tabs
          value={severityTab}
          onChange={(_, newValue) => setSeverityTab(newValue)}
          sx={{ mb: 2, minHeight: 36 }}
          variant="fullWidth"
        >
          <Tab label={`All (${results.length})`} sx={{ minHeight: 36 }} />
          <Tab label={`High`} sx={{ minHeight: 36 }} />
          <Tab label={`Medium`} sx={{ minHeight: 36 }} />
          <Tab label={`Low`} sx={{ minHeight: 36 }} />
        </Tabs>

        {/* Loading indicator */}
        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {/* Error display */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Results count */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {filteredResults.length} {filteredResults.length === 1 ? 'result' : 'results'} shown
          </Typography>
        </Box>

        {/* Results list */}
        {filteredResults.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body2" color="text.secondary">
              {results.length === 0 
                ? 'No Cluster Analyzer results found. Your cluster is healthy!'
                : 'No results match the selected filters.'}
            </Typography>
          </Box>
        ) : (
          <Stack spacing={2}>
            {filteredResults.map((result) => {
              const isExpanded = expandedResults.has(result.name);
              
              return (
                <Paper
                  key={result.name}
                  variant="outlined"
                  sx={{
                    p: 2,
                    borderLeft: 4,
                    borderLeftColor: `${getSeverityColor(result.severity)}.main`,
                  }}
                >
                  {/* Result header */}
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                    <Box sx={{ flex: 1 }}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                        <Chip
                          label={`${getSeverityIcon(result.severity)} ${getSeverityDisplayName(result.severity)}`}
                          size="small"
                          color={getSeverityColor(result.severity)}
                        />
                        <Typography variant="body2" color="text.secondary">
                          {result.kind}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          •
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {result.namespace}
                        </Typography>
                      </Stack>
                      
                      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                        {result.name}
                      </Typography>
                      
                      <Typography variant="caption" color="text.secondary">
                        Analyzer: {result.analyzer} • {formatTimestamp(result.timestamp)}
                      </Typography>
                    </Box>
                    
                    <IconButton
                      size="small"
                      onClick={() => toggleExpanded(result.name)}
                    >
                      {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    </IconButton>
                  </Box>

                  {/* Problem summary (always visible) */}
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    <strong>Problem:</strong> {result.problem}
                  </Typography>

                  {/* Expanded details */}
                  <Collapse in={isExpanded}>
                    <Divider sx={{ my: 1 }} />
                    
                    {result.solution && (
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        <strong>Solution:</strong> {result.solution}
                      </Typography>
                    )}
                    
                    {result.details && Object.keys(result.details).length > 0 && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                          Additional Details:
                        </Typography>
                        <Paper variant="outlined" sx={{ p: 1, bgcolor: 'grey.50' }}>
                          <pre style={{ margin: 0, fontSize: '0.75rem', overflow: 'auto' }}>
                            {JSON.stringify(result.details, null, 2)}
                          </pre>
                        </Paper>
                      </Box>
                    )}
                  </Collapse>
                </Paper>
              );
            })}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};
