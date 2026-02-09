import React, { useMemo } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box, Container, AppBar, Toolbar, Typography, Alert } from '@mui/material';
import LoginForm from './components/LoginForm';
import ClusterSelector from './components/ClusterSelector';
import { CredentialBadge } from './components/CredentialBadge';
import { WeatherWidget } from './components/WeatherWidget';
import { ChatInterface } from './components/ChatInterface';
import { ResultsPanel } from './components/ResultsPanel';
import { useCredentials, useCluster, useChat, useWeather } from './hooks';

/**
 * Main App component for DevOps Chatbot v2
 * 
 * Orchestrates the entire frontend application with:
 * 1. Authentication flow (LoginForm → ClusterSelector → Main Interface)
 * 2. Cluster selection with ClusterSelector
 * 3. Main interface with WeatherWidget, ChatInterface, and ResultsPanel
 * 4. All hooks wired up (useCredentials, useCluster, useChat, useWeather)
 * 
 * Requirements: 14.1, 14.2, 14.3
 */
function App() {
  // Credential management hook
  const credentials = useCredentials();

  // Cluster management hook (depends on authentication)
  const cluster = useCluster(credentials.isAuthenticated);

  // Chat management hook (depends on authentication and cluster selection)
  const chat = useChat(cluster.selectedCluster, credentials.isAuthenticated);

  // Weather monitoring hook (depends on authentication and cluster selection)
  useWeather(cluster.selectedCluster, credentials.isAuthenticated);

  // Create theme
  const theme = useMemo(() => {
    return createTheme({
      palette: {
        mode: 'light',
        primary: {
          main: '#1976d2',
          light: '#42a5f5',
          dark: '#1565c0',
        },
        secondary: {
          main: '#dc004e',
        },
        background: {
          default: '#f5f5f5',
          paper: '#ffffff',
        },
      },
      typography: {
        fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
        h4: {
          fontWeight: 600,
        },
        h6: {
          fontWeight: 500,
        },
      },
    });
  }, []);

  // Render login form if not authenticated
  if (!credentials.isAuthenticated) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box
          sx={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'background.default',
          }}
        >
          <Container maxWidth="sm">
            <Box sx={{ textAlign: 'center', mb: 4 }}>
              <Typography variant="h4" component="h1" gutterBottom>
                DevOps Chatbot v2
              </Typography>
              <Typography variant="body1" color="text.secondary">
                Kubernetes Troubleshooting Assistant
              </Typography>
            </Box>
            <LoginForm onLogin={credentials.login} />
          </Container>
        </Box>
      </ThemeProvider>
    );
  }

  // Render cluster selector if authenticated but no cluster selected
  if (!cluster.selectedCluster) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default' }}>
          <AppBar position="static">
            <Toolbar>
              <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                DevOps Chatbot v2
              </Typography>
              <CredentialBadge />
            </Toolbar>
          </AppBar>
          
          <Container maxWidth="md" sx={{ mt: 8 }}>
            <Box sx={{ textAlign: 'center', mb: 4 }}>
              <Typography variant="h5" gutterBottom>
                Select a Cluster
              </Typography>
              <Typography variant="body1" color="text.secondary">
                Choose an EKS cluster to monitor and troubleshoot
              </Typography>
            </Box>

            {cluster.error && (
              <Alert severity="error" sx={{ mb: 3 }}>
                {cluster.error}
              </Alert>
            )}

            <ClusterSelector
              clusters={cluster.clusters}
              selectedCluster={cluster.selectedCluster}
              onSelectCluster={cluster.selectCluster}
              loading={cluster.isLoading}
            />
          </Container>
        </Box>
      </ThemeProvider>
    );
  }

  // Render main interface with weather, chat, and results
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', backgroundColor: 'background.default' }}>
        {/* App Bar with cluster info and credential badge */}
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              DevOps Chatbot v2
            </Typography>
            
            {/* Cluster selector in header */}
            <Box sx={{ mr: 2, minWidth: 250 }}>
              <ClusterSelector
                clusters={cluster.clusters}
                selectedCluster={cluster.selectedCluster}
                onSelectCluster={cluster.selectCluster}
                loading={cluster.isLoading}
              />
            </Box>

            {/* Credential badge */}
            <CredentialBadge />
          </Toolbar>
        </AppBar>

        {/* Main content area */}
        <Container maxWidth="xl" sx={{ mt: 3, mb: 3 }}>
          {/* Credential expiration warning */}
          {credentials.timeRemaining !== null && credentials.timeRemaining < 600 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Your credentials will expire in {Math.floor(credentials.timeRemaining / 60)} minutes.
              Please prepare to re-authenticate.
            </Alert>
          )}

          {/* Weather widget */}
          <Box sx={{ mb: 3 }}>
            <WeatherWidget
              onAskAboutIssue={(issue) => {
                // Pre-fill chat with question about the issue
                chat.sendMessage(issue);
              }}
            />
          </Box>

          {/* Main content grid: Chat and Results */}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', lg: '2fr 1fr' },
              gap: 3,
            }}
          >
            {/* Chat interface */}
            <Box>
              <ChatInterface
                isAuthenticated={credentials.isAuthenticated}
                selectedCluster={cluster.selectedCluster}
                messages={chat.messages}
                onMessagesChange={(messages) => {
                  // This is handled internally by the ChatInterface
                  // We're just passing the messages for display
                }}
              />
            </Box>

            {/* Results panel */}
            <Box>
              <ResultsPanel />
            </Box>
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default App;
