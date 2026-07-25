import React, { useMemo } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Box, Container, AppBar, Toolbar, Typography, Alert, CircularProgress } from '@mui/material';
import LoginForm from './components/LoginForm';
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

  // Resolve single cluster context automatically after authentication
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
              <CircularProgress size={36} sx={{ mb: 2 }} />
              <Typography variant="h5" gutterBottom>
                Connecting to Cluster
              </Typography>
              <Typography variant="body1" color="text.secondary">
                Resolving single-cluster context for this session
              </Typography>
            </Box>

            {cluster.error && (
              <Alert severity="error" sx={{ mb: 3 }}>
                {cluster.error}
              </Alert>
            )}
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
            
            <Typography variant="body2" sx={{ mr: 2 }}>
              Cluster: {cluster.selectedCluster}
            </Typography>

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

          {/* Layer 1: Weather widget */}
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

          {/* Layer 2: Chat — full width */}
          <Box sx={{ mb: 3 }}>
            <ChatInterface
              isAuthenticated={credentials.isAuthenticated}
              selectedCluster={cluster.selectedCluster}
              messages={chat.messages}
              onMessagesChange={chat.setMessages}
              onExportConversation={chat.exportConversation}
              onClearConversation={chat.clearMessages}
            />
          </Box>

          {/* Layer 3: Analyzer results — full width */}
          <Box>
            <ResultsPanel />
          </Box>
        </Container>
      </Box>
    </ThemeProvider>
  );
}

export default App;
