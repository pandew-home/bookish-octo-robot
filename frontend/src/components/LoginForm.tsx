import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Button,
  Container,
  TextField,
  Typography,
  Paper,
  Alert,
  MenuItem,
  Link,
  CircularProgress,
  Tabs,
  Tab,
  Select,
  FormControl,
  InputLabel,
  SelectChangeEvent,
} from '@mui/material';
import { KionCredentials, CredentialValidationErrors, AWS_REGIONS, AuthMode, KubeconfigContext, KubeconfigParseResponse } from '../types/credentials';
import { validateCredentials } from '../utils/credentialValidator';
import { authApi } from '../services/api';

interface LoginFormProps {
  onLogin: (credentials: KionCredentials) => Promise<void>;
  onKubeconfigLogin?: () => Promise<void>;
}

/**
 * Kubeconfig authentication step
 */
type KubeconfigStep = 'upload' | 'selectContext' | 'authenticating';

const LoginForm: React.FC<LoginFormProps> = ({ onLogin, onKubeconfigLogin }) => {
  const [authMode, setAuthMode] = useState<AuthMode>('aws');
  const [credentials, setCredentials] = useState<KionCredentials>({
    accessKeyId: '',
    secretAccessKey: '',
    sessionToken: '',
    region: 'us-east-1',
  });

  // Kubeconfig streaming state
  const [kubeconfigContent, setKubeconfigContent] = useState<string>('');
  const [kubeconfigStep, setKubeconfigStep] = useState<KubeconfigStep>('upload');
  const [availableContexts, setAvailableContexts] = useState<KubeconfigContext[]>([]);
  const [selectedContext, setSelectedContext] = useState<string>('');
  const [currentContext, setCurrentContext] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [errors, setErrors] = useState<CredentialValidationErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    const input = fileInputRef.current;
    if (!input) return;
    input.removeAttribute('webkitdirectory');
    input.removeAttribute('directory');
    input.removeAttribute('mozdirectory');
  }, [authMode, kubeconfigStep]);

  const handleAuthModeChange = (_event: React.SyntheticEvent, newMode: AuthMode) => {
    setAuthMode(newMode);
    setSubmitError(null);
    setErrors({});
    // Reset kubeconfig state when switching modes
    if (newMode === 'kubeconfig') {
      resetKubeconfigState();
    }
  };

  const resetKubeconfigState = () => {
    setKubeconfigContent('');
    setKubeconfigStep('upload');
    setAvailableContexts([]);
    setSelectedContext('');
    setCurrentContext(null);
  };

  const handleChange = (field: keyof KionCredentials) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    setCredentials({
      ...credentials,
      [field]: event.target.value,
    });
    // Clear error for this field when user starts typing
    if (errors[field]) {
      setErrors({
        ...errors,
        [field]: undefined,
      });
    }
    // Clear submit error when user makes changes
    if (submitError) {
      setSubmitError(null);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    console.log('[LoginForm] File selected:', file.name);
    
    try {
      const content = await file.text();
      console.log('[LoginForm] File content read, length:', content.length);
      setKubeconfigContent(content);
      await parseKubeconfig(content);
    } catch (error: any) {
      console.error('[LoginForm] Error reading file:', error);
      setSubmitError('Failed to read kubeconfig file: ' + error.message);
    }
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handlePaste = async (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const content = event.target.value;
    setKubeconfigContent(content);
    
    if (content.trim()) {
      // Debounce parsing
      clearTimeout((window as any).kubeconfigParseTimeout);
      (window as any).kubeconfigParseTimeout = setTimeout(() => {
        parseKubeconfig(content);
      }, 500);
    }
  };

  const parseKubeconfig = async (content: string) => {
    if (!content.trim()) return;
    
    console.log('[LoginForm] Parsing kubeconfig...');
    setIsSubmitting(true);
    setSubmitError(null);
    
    try {
      const response: KubeconfigParseResponse = await authApi.parseKubeconfig({ content });
      console.log('[LoginForm] Parse response:', response);
      
      setAvailableContexts(response.contexts);
      setCurrentContext(response.currentContext);
      
      // Auto-select current context or first context
      if (response.currentContext && response.contexts.some(c => c.name === response.currentContext)) {
        setSelectedContext(response.currentContext);
      } else if (response.contexts.length > 0) {
        setSelectedContext(response.contexts[0].name);
      }
      
      setKubeconfigStep('selectContext');
    } catch (error: any) {
      console.error('[LoginForm] Parse error:', error);
      setSubmitError(error.response?.data?.detail || error.message || 'Failed to parse kubeconfig');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleContextSelect = (event: SelectChangeEvent) => {
    setSelectedContext(event.target.value);
  };

  const handleKubeconfigAuth = async () => {
    if (!selectedContext || !kubeconfigContent) {
      setSubmitError('Please select a context');
      return;
    }
    
    console.log('[LoginForm] Authenticating with context:', selectedContext);
    setKubeconfigStep('authenticating');
    setIsSubmitting(true);
    setSubmitError(null);
    
    try {
      const response = await authApi.authKubeconfig({
        content: kubeconfigContent,
        context: selectedContext,
      });
      
      console.log('[LoginForm] Auth response:', response);
      
      if (response.success) {
        // Store session ID for subsequent requests
        localStorage.setItem('sessionId', response.sessionId);
        // Notify parent to refresh auth state (no page reload needed)
        if (onKubeconfigLogin) {
          await onKubeconfigLogin();
        }
      } else {
        setSubmitError('Authentication failed');
        setKubeconfigStep('selectContext');
      }
    } catch (error: any) {
      console.error('[LoginForm] Auth error:', error);
      setSubmitError(error.response?.data?.detail || error.message || 'Authentication failed');
      setKubeconfigStep('selectContext');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBackToUpload = () => {
    resetKubeconfigState();
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    if (authMode === 'kubeconfig') {
      // Handle kubeconfig auth based on current step
      if (kubeconfigStep === 'selectContext') {
        await handleKubeconfigAuth();
      } else {
        setSubmitError('Please upload or paste a kubeconfig file first');
      }
      return;
    }

    // Validate AWS credentials
    const validationErrors = validateCredentials(credentials);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onLogin(credentials);
    } catch (error: any) {
      setSubmitError(
        error.response?.data?.detail || 
        error.message || 
        'Failed to authenticate. Please check your credentials and try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Paper elevation={3} sx={{ p: 4, width: '100%', backgroundColor: '#121d20', border: '1px solid #1e2e32' }}>
          <Typography component="h1" variant="h4" align="center" gutterBottom sx={{ color: '#ffffff' }}>
            DevOps Chatbot v2
          </Typography>
          
          {/* Auth Mode Tabs */}
          <Tabs
            value={authMode}
            onChange={handleAuthModeChange}
            variant="fullWidth"
            sx={{
              mb: 3,
              '& .MuiTabs-indicator': { backgroundColor: '#66a16e' },
              '& .MuiTab-root': { color: '#a0b0b5' },
              '& .MuiTab-root.Mui-selected': { color: '#66a16e' },
            }}
          >
            <Tab label="AWS (Kion)" value="aws" />
            <Tab label="Kubeconfig" value="kubeconfig" />
          </Tabs>

          <Typography variant="h6" align="center" sx={{ color: '#a0b015', mb: 2 }}>
            {authMode === 'aws' ? 'AWS Kion Authentication' : 'Local Cluster Authentication'}
          </Typography>

          {submitError && (
            <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
              {submitError}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit} sx={{ mt: 3 }}>
            {authMode === 'aws' ? (
              // AWS Credentials Form
              <>
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  id="accessKeyId"
                  label="Access Key ID"
                  name="accessKeyId"
                  autoComplete="off"
                  autoFocus
                  value={credentials.accessKeyId}
                  onChange={handleChange('accessKeyId')}
                  error={!!errors.accessKeyId}
                  helperText={
                    errors.accessKeyId || 
                    'AWS access key ID from Kion (e.g., AKIAIOSFODNN7EXAMPLE)'
                  }
                  disabled={isSubmitting}
                />

                <TextField
                  margin="normal"
                  required
                  fullWidth
                  name="secretAccessKey"
                  label="Secret Access Key"
                  type="password"
                  id="secretAccessKey"
                  autoComplete="off"
                  value={credentials.secretAccessKey}
                  onChange={handleChange('secretAccessKey')}
                  error={!!errors.secretAccessKey}
                  helperText={
                    errors.secretAccessKey || 
                    'AWS secret access key from Kion (40 characters)'
                  }
                  disabled={isSubmitting}
                />

                <TextField
                  margin="normal"
                  required
                  fullWidth
                  name="sessionToken"
                  label="Session Token"
                  type="password"
                  id="sessionToken"
                  autoComplete="off"
                  value={credentials.sessionToken}
                  onChange={handleChange('sessionToken')}
                  error={!!errors.sessionToken}
                  helperText={
                    errors.sessionToken || 
                    'AWS session token from Kion (temporary credentials)'
                  }
                  disabled={isSubmitting}
                />

                <TextField
                  margin="normal"
                  required
                  fullWidth
                  select
                  id="region"
                  label="AWS Region"
                  name="region"
                  value={credentials.region}
                  onChange={handleChange('region')}
                  error={!!errors.region}
                  helperText={errors.region || 'Select the AWS region for your EKS clusters'}
                  disabled={isSubmitting}
                >
                  {AWS_REGIONS.map((region) => (
                    <MenuItem key={region} value={region}>
                      {region}
                    </MenuItem>
                  ))}
                </TextField>

                <Box sx={{ mt: 2, textAlign: 'center' }}>
                  <Typography variant="body2" sx={{ color: '#a0b0b5' }}>
                    Need credentials?{' '}
                    <Link
                      href="https://kion.example.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      sx={{ color: '#66a16e' }}
                    >
                      Get them from Kion Console
                    </Link>
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#a0b0b5', mt: 1, display: 'block' }}>
                    Credentials are temporary and expire after 1 hour
                  </Typography>
                </Box>
              </>
            ) : (
              // Kubeconfig Form
              <>
                {kubeconfigStep === 'upload' && (
                  <>
                    {/* File Upload */}
                    <input
                      type="file"
                      accept="*/*"
                      multiple={false}
                      style={{ display: 'none' }}
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                    />
                    
                    <Button
                      variant="outlined"
                      fullWidth
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isSubmitting}
                      sx={{ mb: 2, py: 2 }}
                    >
                      {isSubmitting ? (
                        <>
                          <CircularProgress size={20} sx={{ mr: 1 }} />
                          Parsing...
                        </>
                      ) : (
                        'Upload Kubeconfig File'
                      )}
                    </Button>

                    <Typography variant="body2" align="center" sx={{ color: '#a0b0b5', mb: 2 }}>
                      — or paste content below —
                    </Typography>

                    {/* Textarea for paste */}
                    <TextField
                      multiline
                      rows={8}
                      fullWidth
                      placeholder="Paste your kubeconfig YAML content here..."
                      value={kubeconfigContent}
                      onChange={handlePaste}
                      disabled={isSubmitting}
                      sx={{
                        '& .MuiOutlinedInput-root': {
                          fontFamily: 'monospace',
                          fontSize: '0.85rem',
                        },
                      }}
                    />

                    <Box sx={{ mt: 2, textAlign: 'center' }}>
                      <Typography variant="body2" sx={{ color: '#a0b0b5' }}>
                        Upload or paste your kubeconfig file to connect to local clusters
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#a0b0b5', mt: 1, display: 'block' }}>
                        Supports kind, k3s, minikube, Docker Desktop, etc.
                      </Typography>
                    </Box>
                  </>
                )}

                {kubeconfigStep === 'selectContext' && (
                  <>
                    <Alert severity="success" sx={{ mb: 2 }}>
                      Found {availableContexts.length} context(s) in kubeconfig
                    </Alert>

                    <FormControl fullWidth sx={{ mb: 2 }}>
                      <InputLabel id="context-select-label">Select Context</InputLabel>
                      <Select
                        labelId="context-select-label"
                        value={selectedContext}
                        label="Select Context"
                        onChange={handleContextSelect}
                        disabled={isSubmitting}
                      >
                        {availableContexts.map((ctx) => (
                          <MenuItem 
                            key={ctx.name} 
                            value={ctx.name}
                            sx={{ 
                              display: 'flex', 
                              flexDirection: 'column', 
                              alignItems: 'flex-start' 
                            }}
                          >
                            <Box>
                              <Typography variant="body1">{ctx.name}</Typography>
                              <Typography variant="caption" sx={{ color: '#a0b0b5' }}>
                                cluster: {ctx.cluster}
                              </Typography>
                            </Box>
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    {currentContext && (
                      <Typography variant="caption" sx={{ color: '#a0b0b5', display: 'block', mb: 2 }}>
                        Current context: {currentContext}
                      </Typography>
                    )}

                    <Box sx={{ display: 'flex', gap: 2 }}>
                      <Button
                        variant="outlined"
                        onClick={handleBackToUpload}
                        disabled={isSubmitting}
                        sx={{ flex: 1 }}
                      >
                        Back
                      </Button>
                      <Button
                        type="submit"
                        variant="contained"
                        disabled={isSubmitting || !selectedContext}
                        sx={{ flex: 2 }}
                      >
                        {isSubmitting ? (
                          <>
                            <CircularProgress size={20} sx={{ mr: 1 }} />
                            Connecting...
                          </>
                        ) : (
                          'Connect'
                        )}
                      </Button>
                    </Box>
                  </>
                )}

                {kubeconfigStep === 'authenticating' && (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <CircularProgress size={40} sx={{ mb: 2 }} />
                    <Typography variant="body1" sx={{ color: '#a0b0b5' }}>
                      Connecting to cluster with context: {selectedContext}
                    </Typography>
                  </Box>
                )}
              </>
            )}

            {authMode === 'aws' && (
              <Button
                type="submit"
                fullWidth
                variant="contained"
                sx={{ mt: 3, mb: 2 }}
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <CircularProgress size={20} sx={{ mr: 1 }} />
                    Authenticating...
                  </>
                ) : (
                  'Login'
                )}
              </Button>
            )}
          </Box>
        </Paper>
      </Box>
    </Container>
  );
};

export default LoginForm;
