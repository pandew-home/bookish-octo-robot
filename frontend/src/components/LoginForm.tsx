import React, { useState } from 'react';
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
} from '@mui/material';
import { KionCredentials, CredentialValidationErrors, AWS_REGIONS } from '../types/credentials';
import { validateCredentials } from '../utils/credentialValidator';

interface LoginFormProps {
  onLogin: (credentials: KionCredentials) => Promise<void>;
}

const LoginForm: React.FC<LoginFormProps> = ({ onLogin }) => {
  const [credentials, setCredentials] = useState<KionCredentials>({
    accessKeyId: '',
    secretAccessKey: '',
    sessionToken: '',
    region: 'us-east-1',
  });

  const [errors, setErrors] = useState<CredentialValidationErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

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

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    // Validate credentials
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
        <Paper elevation={3} sx={{ p: 4, width: '100%' }}>
          <Typography component="h1" variant="h4" align="center" gutterBottom>
            DevOps Chatbot v2
          </Typography>
          <Typography variant="h6" align="center" color="text.secondary" gutterBottom>
            AWS Kion Authentication
          </Typography>

          {submitError && (
            <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
              {submitError}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit} sx={{ mt: 3 }}>
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

            <Box sx={{ mt: 2, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                Need credentials?{' '}
                <Link
                  href="https://kion.example.com"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Get them from Kion Console
                </Link>
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                Credentials are temporary and expire after 1 hour
              </Typography>
            </Box>
          </Box>
        </Paper>
      </Box>
    </Container>
  );
};

export default LoginForm;
