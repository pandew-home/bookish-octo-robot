import React from 'react';
import { Box, Chip, Tooltip, CircularProgress } from '@mui/material';
import {
  AccountCircle as AccountCircleIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
} from '@mui/icons-material';
import { useCredentialStatus } from '../hooks/useCredentialStatus';

/**
 * Format seconds into human-readable time (e.g., "5m", "2h 15m")
 */
const formatTimeRemaining = (seconds: number): string => {
  const minutes = Math.floor(seconds / 60);

  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
};

/**
 * Component to display Kion AWS credential status with expiry countdown
 * 
 * Displays:
 * - No credentials (gray): User hasn't submitted Kion credentials yet
 * - Active (green): Credentials valid with >10 minutes remaining
 * - Expiring soon (orange): Credentials valid with <10 minutes remaining
 * - Expired (red): Credentials have expired
 */
export const CredentialBadge: React.FC = () => {
  const { status, loading, error, timeRemaining } = useCredentialStatus();

  if (loading && !status) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <CircularProgress size={16} />
        <Chip size="small" label="Loading..." />
      </Box>
    );
  }

  if (error) {
    return (
      <Tooltip title={`Error: ${error}`}>
        <Chip
          size="small"
          icon={<ErrorIcon />}
          label="Error"
          color="error"
          variant="outlined"
        />
      </Tooltip>
    );
  }

  if (!status) {
    return null;
  }

  // No credentials submitted yet
  if (!status.present) {
    return (
      <Tooltip title="No Kion credentials submitted. Please log in.">
        <Chip
          size="small"
          icon={<AccountCircleIcon />}
          label="No Credentials"
          color="default"
          variant="outlined"
        />
      </Tooltip>
    );
  }

  // Expired credentials
  if (status.expired) {
    return (
      <Tooltip title="Your Kion AWS credentials have expired. Please submit new credentials to continue.">
        <Chip
          size="small"
          icon={<WarningIcon />}
          label="Credentials Expired"
          color="error"
          variant="filled"
        />
      </Tooltip>
    );
  }

  // Active credentials with countdown
  if (timeRemaining !== null) {
    const isExpiringSoon = timeRemaining < 600; // Less than 10 minutes
    const tooltipText = `Kion credentials expire in ${formatTimeRemaining(timeRemaining)}${
      status.account_id ? ` (Account: ${status.account_id})` : ''
    }`;

    return (
      <Tooltip title={tooltipText}>
        <Chip
          size="small"
          icon={isExpiringSoon ? <WarningIcon /> : <AccountCircleIcon />}
          label={`Active (${formatTimeRemaining(timeRemaining)})`}
          color={isExpiringSoon ? 'warning' : 'success'}
          variant="filled"
        />
      </Tooltip>
    );
  }

  // Active credentials without expiry time
  return (
    <Tooltip
      title={`Using Kion AWS credentials${
        status.account_id ? ` (Account: ${status.account_id})` : ''
      }`}
    >
      <Chip
        size="small"
        icon={<AccountCircleIcon />}
        label="Active"
        color="success"
        variant="filled"
      />
    </Tooltip>
  );
};
