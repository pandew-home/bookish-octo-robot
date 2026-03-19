import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  LinearProgress,
  Chip,
  Divider,
  IconButton,
  Collapse,
  Stack,
  CircularProgress,
} from '@mui/material';
import {
  Close as CloseIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Visibility as ViewIcon,
  Event as EventIcon,
  Help as HelpIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';

// Weather state type
type WeatherState = 'sunny' | 'partly-cloudy' | 'cloudy' | 'rainy' | 'stormy';

// Weather icons mapping
const weatherIcons: Record<WeatherState, string> = {
  sunny: '☀️',
  'partly-cloudy': '🌤️',
  cloudy: '☁️',
  rainy: '🌧️',
  stormy: '⛈️',
};

// Weather display names
const weatherNames: Record<WeatherState, string> = {
  sunny: 'Sunny',
  'partly-cloudy': 'Partly Cloudy',
  cloudy: 'Cloudy',
  rainy: 'Rainy',
  stormy: 'Stormy',
};

// Cluster tool info interface
interface ClusterToolInfo {
  name: string;
  version: string;
  category: string;
  deploymentAgeDays?: number;
  status: 'healthy' | 'degraded' | 'unknown';
}

// K8sGPT Result summary interface
interface K8sGPTResultSummary {
  name: string;
  kind: string;
  namespace: string;
  severity: 'low' | 'medium' | 'high';
  problem: string;
  solution?: string;
  analyzer?: string;
  timestamp?: string;
}

// K8sGPT status type
type K8sGPTStatus = 'available' | 'not_installed' | 'unreachable';

// Weather data interface
interface WeatherData {
  state: WeatherState;
  clusterName: string;
  clusterVersion: string;
  k8sgptResultCount: number;
  topIssues?: K8sGPTResultSummary[];
  clusterTools: ClusterToolInfo[];
  timestamp: string;
  k8sgptStatus?: K8sGPTStatus;
  k8sgptMessage?: string;
}

// Props interface
interface WeatherWidgetProps {
  onAskAboutIssue?: (issue: string) => void;
}

const WEATHER_POLL_INTERVAL = 60000; // 60 seconds
const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export const WeatherWidget: React.FC<WeatherWidgetProps> = ({ onAskAboutIssue }) => {
  const [weatherData, setWeatherData] = useState<WeatherData | null>(null);
  const [previousWeatherData, setPreviousWeatherData] = useState<WeatherData | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Compare weather data for changes
  const hasDataChanged = (newData: WeatherData, oldData: WeatherData | null): boolean => {
    if (!oldData) return true;

    // Compare all relevant fields
    return (
      newData.state !== oldData.state ||
      newData.clusterName !== oldData.clusterName ||
      newData.clusterVersion !== oldData.clusterVersion ||
      newData.k8sgptResultCount !== oldData.k8sgptResultCount ||
      JSON.stringify(newData.topIssues) !== JSON.stringify(oldData.topIssues) ||
      JSON.stringify(newData.clusterTools) !== JSON.stringify(oldData.clusterTools)
    );
  };

  // Fetch weather data from backend
  const fetchWeatherData = async () => {
    try {
      setError(null);

      // Only show loading spinner on initial load
      if (isInitialLoad) {
        setIsRefreshing(true);
      }

      const sessionId = localStorage.getItem('sessionId');
      const response = await fetch(`${API_BASE_URL}/api/weather`, {
        method: 'GET',
        credentials: 'include',
        headers: sessionId ? { 'x-session-id': sessionId } : {},
      });

      if (!response.ok) {
        throw new Error(`Weather API error: ${response.status}`);
      }

      const rawData = await response.json();

      // Convert snake_case to camelCase
      const data: WeatherData = {
        state: rawData.weather_state || rawData.state,
        clusterName: rawData.cluster_name,
        clusterVersion: rawData.cluster_version,
        k8sgptResultCount: rawData.k8sgpt_result_count || 0,
        topIssues: rawData.top_issues?.map((issue: any) => ({
          name: issue.name,
          kind: issue.kind,
          namespace: issue.namespace,
          severity: issue.severity,
          problem: issue.problem,
          solution: issue.solution,
        })),
        clusterTools: rawData.cluster_tools?.map((tool: any) => ({
          name: tool.name,
          version: tool.version,
          category: tool.category,
          deploymentAgeDays: tool.deployment_age_days,
          status: tool.status,
        })) || [],
        timestamp: rawData.timestamp,
        k8sgptStatus: rawData.k8sgpt_status,
        k8sgptMessage: rawData.k8sgpt_message,
      };

      // Only update if data actually changed
      if (hasDataChanged(data, weatherData)) {
        // Store previous data before updating
        if (weatherData) {
          setPreviousWeatherData(weatherData);
        }
        setWeatherData(data);
      }

      setIsInitialLoad(false);
    } catch (err: any) {
      console.error('Weather fetch error:', err);
      let errorMsg = 'Failed to fetch weather data';
      if (err.message) {
        errorMsg = err.message;
      }
      setError(errorMsg);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Poll for weather updates every 60 seconds
  useEffect(() => {
    fetchWeatherData();
    const interval = setInterval(fetchWeatherData, WEATHER_POLL_INTERVAL);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Get status chip color
  const getStatusColor = (status: ClusterToolInfo['status']) => {
    switch (status) {
      case 'healthy': return 'success';
      case 'degraded': return 'warning';
      case 'unknown': return 'default';
      default: return 'default';
    }
  };

  // Get status icon
  const getStatusIcon = (status: ClusterToolInfo['status']) => {
    switch (status) {
      case 'healthy': return '✅';
      case 'degraded': return '⚠️';
      case 'unknown': return '❓';
      default: return '❓';
    }
  };

  // Get severity color
  const getSeverityColor = (severity: 'low' | 'medium' | 'high') => {
    switch (severity) {
      case 'high': return 'error';
      case 'medium': return 'warning';
      case 'low': return 'info';
      default: return 'info';
    }
  };

  // Handle quick action buttons
  const handleQuickAction = (action: string, issue?: K8sGPTResultSummary) => {
    switch (action) {
      case 'view-pods':
        onAskAboutIssue?.('Show me the failing pods and their status');
        break;
      case 'check-events':
        onAskAboutIssue?.('What recent events happened in the cluster?');
        break;
      case 'ask-about-this':
        if (issue) {
          onAskAboutIssue?.(
            `Help me understand this issue: ${issue.kind}/${issue.name} in ${issue.namespace} - ${issue.problem}`
          );
        } else {
          onAskAboutIssue?.('Help me understand the current cluster issues');
        }
        break;
    }
  };

  if (isInitialLoad && isRefreshing) {
    return (
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ textAlign: 'center', py: 4 }}>
          <Typography variant="h6" color="text.secondary">
            Loading cluster health...
          </Typography>
          <LinearProgress sx={{ mt: 2, maxWidth: 200, mx: 'auto' }} />
        </CardContent>
      </Card>
    );
  }

  if (error && !weatherData && !previousWeatherData) {
    return (
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ textAlign: 'center', py: 4 }}>
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
          <Button variant="outlined" onClick={fetchWeatherData} disabled={isRefreshing}>
            {isRefreshing ? 'Retrying...' : 'Retry'}
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Use current data or fall back to previous data
  const displayData = weatherData || previousWeatherData;

  if (!displayData) {
    return (
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ textAlign: 'center', py: 4 }}>
          <Typography variant="body2" color="text.secondary">
            No cluster data available
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const hasIssues = displayData.topIssues && displayData.topIssues.length > 0;

  return (
    <>
      <Card sx={{ mb: 2, position: 'relative' }}>
        {/* Subtle refresh indicator */}
        {isRefreshing && !isInitialLoad && (
          <Box
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              zIndex: 1,
            }}
          >
            <CircularProgress size={20} thickness={4} />
          </Box>
        )}

        {/* Error indicator (if error but showing previous data) */}
        {error && displayData && (
          <Box
            sx={{
              position: 'absolute',
              top: 8,
              left: 8,
              zIndex: 1,
            }}
          >
            <Chip
              label="Update failed"
              color="warning"
              size="small"
              icon={<WarningIcon />}
            />
          </Box>
        )}

        <CardContent sx={{ textAlign: 'center', py: 3 }}>
          {/* K8sGPT Status Banner */}
          {displayData.k8sgptStatus && displayData.k8sgptStatus !== 'available' && (
            <Alert
              severity={displayData.k8sgptStatus === 'not_installed' ? 'info' : 'warning'}
              sx={{ mb: 2, textAlign: 'left' }}
            >
              {displayData.k8sgptStatus === 'not_installed' ? (
                <>K8sGPT operator is not installed on this cluster. Weather data may be incomplete.</>
              ) : (
                <>{displayData.k8sgptMessage || 'Unable to reach K8sGPT. Some data may be unavailable.'}</>
              )}
            </Alert>
          )}

          {/* Cluster Name */}
          <Typography variant="h5" component="h2" gutterBottom sx={{ fontWeight: 600 }}>
            {displayData.clusterName}
          </Typography>

          {/* Weather Icon and State */}
          <Box sx={{ my: 2 }}>
            <Typography variant="h1" component="div" sx={{ fontSize: '4rem', mb: 1 }}>
              {weatherIcons[displayData.state]}
            </Typography>
            <Typography variant="h6" component="div" sx={{ fontWeight: 600 }}>
              {weatherNames[displayData.state]}
            </Typography>
          </Box>

          {/* K8sGPT Result Count */}
          <Typography variant="body2" color="text.secondary" gutterBottom>
            {displayData.k8sgptResultCount} K8sGPT {displayData.k8sgptResultCount === 1 ? 'result' : 'results'}
          </Typography>

          {/* Last Updated */}
          <Typography variant="caption" color="text.secondary">
            Updated {formatTimestamp(displayData.timestamp)}
          </Typography>

          {/* Top Issues (only when weather is cloudy or worse) */}
          {hasIssues && (
            <Box sx={{ mt: 3 }}>
              <Stack spacing={1}>
                {displayData.topIssues!.map((issue, index) => (
                  <Alert
                    key={index}
                    severity={getSeverityColor(issue.severity)}
                    sx={{ textAlign: 'left' }}
                    action={
                      <Stack direction="row" spacing={1}>
                        <Button
                          size="small"
                          startIcon={<ViewIcon />}
                          onClick={() => handleQuickAction('view-pods')}
                        >
                          View Pods
                        </Button>
                        <Button
                          size="small"
                          startIcon={<EventIcon />}
                          onClick={() => handleQuickAction('check-events')}
                        >
                          Check Events
                        </Button>
                        <Button
                          size="small"
                          startIcon={<HelpIcon />}
                          onClick={() => handleQuickAction('ask-about-this', issue)}
                        >
                          Ask About This
                        </Button>
                      </Stack>
                    }
                  >
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {issue.kind}/{issue.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {issue.namespace} • {issue.severity}
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 0.5 }}>
                      {issue.problem}
                    </Typography>
                  </Alert>
                ))}
              </Stack>
            </Box>
          )}

          {/* View Details Button */}
          <Box sx={{ mt: 3 }}>
            <Button
              variant="outlined"
              onClick={() => setDetailsOpen(true)}
              size="large"
            >
              View Details
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Details Dialog */}
      <Dialog
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Cluster Health Details
          <IconButton
            aria-label="close"
            onClick={() => setDetailsOpen(false)}
            sx={{ position: 'absolute', right: 8, top: 8 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>

        <DialogContent>
          {/* Cluster Info */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="body1" gutterBottom>
              <strong>Cluster:</strong> {displayData.clusterName}
            </Typography>
            <Typography variant="body1" gutterBottom>
              <strong>Kubernetes:</strong> {displayData.clusterVersion}
            </Typography>
            <Typography variant="body1" gutterBottom>
              <strong>Weather:</strong> {weatherIcons[displayData.state]} {weatherNames[displayData.state]}
            </Typography>
            <Typography variant="body1" gutterBottom>
              <strong>K8sGPT Results:</strong> {displayData.k8sgptResultCount}
            </Typography>
          </Box>

          <Divider sx={{ my: 2 }} />

          {/* Top Issues Section */}
          {hasIssues && (
            <>
              <Typography variant="h6" gutterBottom>
                TOP ISSUES
              </Typography>
              <Box sx={{ mb: 3 }}>
                <Stack spacing={1}>
                  {displayData.topIssues!.map((issue, index) => (
                    <Alert
                      key={index}
                      severity={getSeverityColor(issue.severity)}
                      sx={{ textAlign: 'left' }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {issue.kind}/{issue.name}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {issue.namespace} • {issue.severity}
                      </Typography>
                      <Typography variant="body2" sx={{ mt: 0.5 }}>
                        <strong>Problem:</strong> {issue.problem}
                      </Typography>
                      {issue.solution && (
                        <Typography variant="body2" sx={{ mt: 0.5 }}>
                          <strong>Solution:</strong> {issue.solution}
                        </Typography>
                      )}
                    </Alert>
                  ))}
                </Stack>
              </Box>

              <Divider sx={{ my: 2 }} />
            </>
          )}

          {/* Cluster Tools */}
          <Box sx={{ mb: 2 }}>
            <Button
              onClick={() => setToolsExpanded(!toolsExpanded)}
              endIcon={toolsExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              sx={{ mb: 1 }}
            >
              <Typography variant="h6">
                CLUSTER TOOLS & VERSIONS
              </Typography>
            </Button>

            <Collapse in={toolsExpanded}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell><strong>Tool</strong></TableCell>
                    <TableCell><strong>Version</strong></TableCell>
                    <TableCell><strong>Category</strong></TableCell>
                    <TableCell><strong>Status</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {displayData.clusterTools.map((tool, index) => (
                    <TableRow key={index}>
                      <TableCell>{tool.name}</TableCell>
                      <TableCell>{tool.version}</TableCell>
                      <TableCell>{tool.category}</TableCell>
                      <TableCell>
                        <Chip
                          label={`${getStatusIcon(tool.status)} ${tool.status}`}
                          color={getStatusColor(tool.status)}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Collapse>
          </Box>
        </DialogContent>

        <DialogActions>
          <Button onClick={() => setDetailsOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
