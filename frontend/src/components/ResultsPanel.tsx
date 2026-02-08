import React, { useState, useEffect, useMemo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  Alert,
  Chip,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  OutlinedInput,
  SelectChangeEvent,
  Divider,
  IconButton,
  Collapse,
  LinearProgress,
  Paper,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Help as HelpIcon,
  Refresh as RefreshIcon,
  FilterList as FilterIcon,
} from '@mui/icons-material';
import { resultsApi } from '../services/api';
import {
  K8sGPTResult,
  SeverityLevel,
  getSeverityColor,
  getSeverityIcon,
  getSeverityDisplayName,
} from '../types/k8sgpt';

/**
 * Props for ResultsPanel component
 */
interface ResultsPanelProps {
  /**
   * Callback when user clicks "Ask About This" for a result
   */
  onAskAbout?: (result: K8sGPTResult) => void;
  
  /**
   * Auto-refresh interval in milliseconds (default: 60000 = 60 seconds)
   */
  refreshInterval?: number;
}

/**
 * ResultsPanel Component
 * 
 * Displays K8sGPT Result CRDs with severity indicators, filtering by severity/namespace/kind,
 * and "Ask About This" button for each result. Fetches data from GET /api/results endpoint.
 * 
 * Features:
 * - Display K8sGPT Result CRDs with severity indicators
 * - Filter by severity, namespace, kind
 * - "Ask About This" button for each result
 * - Auto-refresh every 60 seconds
 * - Expandable result details
 */
export const ResultsPanel: React.FC<ResultsPanelProps> = ({
  onAskAbout,
  refreshInterval = 60000,
}) => {
  // State
  const [results, setResults] = useState<K8sGPTResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set());
  const [filterOpen, setFilterOpen] = useState(false);
  
  // Filter state
  const [selectedSeverities, setSelectedSeverities] = useState<SeverityLevel[]>([]);
  const [selectedNamespaces, setSelectedNamespaces] = useState<string[]>([]);
  const [selectedKinds, setSelectedKinds] = useState<string[]>([]);

  // Extract unique values for filter dropdowns
  const availableNamespaces = useMemo(() => {
    const namespaces = new Set(results.map(r => r.namespace));
    return Array.from(namespaces).sort();
  }, [results]);

  const availableKinds = useMemo(() => {
    const kinds = new Set(results.map(r => r.kind));
    return Array.from(kinds).sort();
  }, [results]);

  // Filter results based on selected filters
  const filteredResults = useMemo(() => {
    return results.filter(result => {
      // Filter by severity
      if (selectedSeverities.length > 0 && !selectedSeverities.includes(result.severity)) {
        return false;
      }
      
      // Filter by namespace
      if (selectedNamespaces.length > 0 && !selectedNamespaces.includes(result.namespace)) {
        return false;
      }
      
      // Filter by kind
      if (selectedKinds.length > 0 && !selectedKinds.includes(result.kind)) {
        return false;
      }
      
      return true;
    });
  }, [results, selectedSeverities, selectedNamespaces, selectedKinds]);

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
      console.error('Failed to fetch K8sGPT results:', err);
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

  // Handle "Ask About This" button
  const handleAskAbout = (result: K8sGPTResult) => {
    if (onAskAbout) {
      onAskAbout(result);
    }
  };

  // Handle filter changes
  const handleSeverityChange = (event: SelectChangeEvent<SeverityLevel[]>) => {
    const value = event.target.value;
    setSelectedSeverities(typeof value === 'string' ? [] : value);
  };

  const handleNamespaceChange = (event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setSelectedNamespaces(typeof value === 'string' ? [] : value);
  };

  const handleKindChange = (event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setSelectedKinds(typeof value === 'string' ? [] : value);
  };

  // Clear all filters
  const clearFilters = () => {
    setSelectedSeverities([]);
    setSelectedNamespaces([]);
    setSelectedKinds([]);
  };

  // Check if any filters are active
  const hasActiveFilters = selectedSeverities.length > 0 || 
                          selectedNamespaces.length > 0 || 
                          selectedKinds.length > 0;

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
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" component="h2">
            K8sGPT Results
          </Typography>
          <Stack direction="row" spacing={1}>
            <IconButton
              onClick={() => setFilterOpen(!filterOpen)}
              color={hasActiveFilters ? 'primary' : 'default'}
              size="small"
            >
              <FilterIcon />
            </IconButton>
            <IconButton onClick={handleRefresh} disabled={loading} size="small">
              <RefreshIcon />
            </IconButton>
          </Stack>
        </Box>

        {/* Loading indicator */}
        {loading && <LinearProgress sx={{ mb: 2 }} />}

        {/* Error display */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Filter section */}
        <Collapse in={filterOpen}>
          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            <Stack spacing={2}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                Filters
              </Typography>

              {/* Severity filter */}
              <FormControl size="small" fullWidth>
                <InputLabel>Severity</InputLabel>
                <Select
                  multiple
                  value={selectedSeverities}
                  onChange={handleSeverityChange}
                  input={<OutlinedInput label="Severity" />}
                  renderValue={(selected) => (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {selected.map((value) => (
                        <Chip
                          key={value}
                          label={`${getSeverityIcon(value)} ${getSeverityDisplayName(value)}`}
                          size="small"
                          color={getSeverityColor(value)}
                        />
                      ))}
                    </Box>
                  )}
                >
                  <MenuItem value="high">
                    <Chip
                      label={`${getSeverityIcon('high')} High`}
                      size="small"
                      color="error"
                      sx={{ mr: 1 }}
                    />
                  </MenuItem>
                  <MenuItem value="medium">
                    <Chip
                      label={`${getSeverityIcon('medium')} Medium`}
                      size="small"
                      color="warning"
                      sx={{ mr: 1 }}
                    />
                  </MenuItem>
                  <MenuItem value="low">
                    <Chip
                      label={`${getSeverityIcon('low')} Low`}
                      size="small"
                      color="info"
                      sx={{ mr: 1 }}
                    />
                  </MenuItem>
                </Select>
              </FormControl>

              {/* Namespace filter */}
              <FormControl size="small" fullWidth>
                <InputLabel>Namespace</InputLabel>
                <Select
                  multiple
                  value={selectedNamespaces}
                  onChange={handleNamespaceChange}
                  input={<OutlinedInput label="Namespace" />}
                  renderValue={(selected) => (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {selected.map((value) => (
                        <Chip key={value} label={value} size="small" />
                      ))}
                    </Box>
                  )}
                >
                  {availableNamespaces.map((namespace) => (
                    <MenuItem key={namespace} value={namespace}>
                      {namespace}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Kind filter */}
              <FormControl size="small" fullWidth>
                <InputLabel>Kind</InputLabel>
                <Select
                  multiple
                  value={selectedKinds}
                  onChange={handleKindChange}
                  input={<OutlinedInput label="Kind" />}
                  renderValue={(selected) => (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {selected.map((value) => (
                        <Chip key={value} label={value} size="small" />
                      ))}
                    </Box>
                  )}
                >
                  {availableKinds.map((kind) => (
                    <MenuItem key={kind} value={kind}>
                      {kind}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              {/* Clear filters button */}
              {hasActiveFilters && (
                <Button
                  variant="outlined"
                  size="small"
                  onClick={clearFilters}
                  fullWidth
                >
                  Clear Filters
                </Button>
              )}
            </Stack>
          </Paper>
        </Collapse>

        {/* Results count */}
        <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            {filteredResults.length} {filteredResults.length === 1 ? 'result' : 'results'}
            {hasActiveFilters && ` (filtered from ${results.length})`}
          </Typography>
        </Box>

        {/* Results list */}
        {filteredResults.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body2" color="text.secondary">
              {results.length === 0 
                ? 'No K8sGPT results found. Your cluster is healthy! ☀️'
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

                  {/* Action button */}
                  <Box sx={{ mt: 2 }}>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<HelpIcon />}
                      onClick={() => handleAskAbout(result)}
                      disabled={!onAskAbout}
                    >
                      Ask About This
                    </Button>
                  </Box>
                </Paper>
              );
            })}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};
