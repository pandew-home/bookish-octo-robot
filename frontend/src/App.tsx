import React, { useMemo, useState } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box, Container, AppBar, Toolbar, Typography, Alert, useMediaQuery, IconButton, Drawer, Badge } from '@mui/material';
import { Analytics as AnalyticsIcon } from '@mui/icons-material';
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

  // Create theme - Deep Space / Obsidian dark theme
  const theme = useMemo(() => createTheme({
    palette: {
      mode: 'dark',
      primary: {
        main: '#66a16e',
        light: '#88c490',
        dark: '#4e8055',
        contrastText: '#ffffff',
      },
      secondary: {
        main: '#4fc3f7',
      },
      background: {
        default: '#0a1214',
        paper: '#121d20',
      },
      text: {
        primary: '#ffffff',
        secondary: '#a0b0b5',
      },
      divider: '#1e2e32',
      error: { main: '#f44336' },
      warning: { main: '#ff9800' },
      info: { main: '#4fc3f7' },
      success: { main: '#66bb6a' },
    },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            border: '1px solid #1e2e32',
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: '#0d1618',
            backgroundImage: 'none',
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          containedPrimary: {
            '&:hover': { backgroundColor: '#4e8055' },
          },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              '& fieldset': { borderColor: '#1e2e32' },
              '&:hover fieldset': { borderColor: '#66a16e' },
            },
          },
        },
      },
    },
    typography: {
      fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
      fontSize: 14,
      h1: { fontSize: '2.5rem' },
      h2: { fontSize: '2rem' },
      h3: { fontSize: '1.75rem' },
      h4: { fontSize: '1.5rem', fontWeight: 600 },
      h5: { fontSize: '1.25rem' },
      h6: { fontSize: '1rem', fontWeight: 500 },
      body1: { fontSize: '0.875rem' },
      body2: { fontSize: '0.75rem' },
      caption: { fontSize: '0.6875rem' },
    },
  }), []);

  // Responsive breakpoints
  const isLargeScreen = useMediaQuery(theme.breakpoints.up('lg'));
  const isMediumScreen = useMediaQuery(theme.breakpoints.between('sm', 'lg'));
  const [resultsDrawerOpen, setResultsDrawerOpen] = useState(false);

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
            <LoginForm onLogin={credentials.login} onKubeconfigLogin={credentials.refresh} />
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
                chat.sendMessage(issue);
              }}
              onCheckEvents={() => {
                chat.sendMessage('What recent events happened in the cluster?');
              }}
            />
          </Box>

          {/* Main content grid: Chat and Results */}
          {isLargeScreen ? (
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: '2fr 1fr',
                gap: 3,
              }}
            >
              <Box>
                <ChatInterface
                  isAuthenticated={credentials.isAuthenticated}
                  selectedCluster={cluster.selectedCluster}
                  messages={chat.messages}
                  onMessagesChange={chat.setMessages}
                  onExportConversation={chat.exportConversation}
                  onClearConversation={chat.clearMessages}
                />
              </Box>
              <Box>
                <ResultsPanel />
              </Box>
            </Box>
          ) : (
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <ChatInterface
                  isAuthenticated={credentials.isAuthenticated}
                  selectedCluster={cluster.selectedCluster}
                  messages={chat.messages}
                  onMessagesChange={chat.setMessages}
                  onExportConversation={chat.exportConversation}
                  onClearConversation={chat.clearMessages}
                />
              </Box>
              {isMediumScreen && (
                <IconButton
                  onClick={() => setResultsDrawerOpen(true)}
                  color="primary"
                  sx={{ position: 'fixed', bottom: 16, right: 16, zIndex: 1000 }}
                >
                  <Badge color="primary">
                    <AnalyticsIcon />
                  </Badge>
                </IconButton>
              )}
              <Drawer
                anchor="right"
                open={resultsDrawerOpen}
                onClose={() => setResultsDrawerOpen(false)}
                PaperProps={{ sx: { width: '85%', maxWidth: 400 } }}
              >
                {resultsDrawerOpen && (
                  <Box sx={{ p: 2 }}>
                    <ResultsPanel />
                  </Box>
                )}
              </Drawer>
            </Box>
          )}
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default App;
