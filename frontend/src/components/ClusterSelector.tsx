import React from 'react';
import {
  Box,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  SelectChangeEvent,
  Chip,
  Typography,
  CircularProgress,
} from '@mui/material';
import {
  ClusterInfo,
  getClusterEnvironment,
  ENVIRONMENT_COLORS,
  ClusterEnvironment,
} from '../types/cluster';

interface ClusterSelectorProps {
  clusters: ClusterInfo[];
  selectedCluster: string | null;
  onSelectCluster: (clusterName: string) => void;
  loading?: boolean;
  disabled?: boolean;
}

/**
 * ClusterSelector component
 * 
 * Dropdown for selecting target EKS cluster with environment-based theming.
 * Displays cluster name, region, and version with color-coded environment indicators.
 * 
 * Features:
 * - Environment-based color theming (dev=green, staging=orange, prod=red)
 * - Cluster metadata display (name, region, version)
 * - Loading and disabled states
 * - Handles cluster selection via POST /api/clusters/select
 * 
 * Requirements: 14.2, 13.5
 */
const ClusterSelector: React.FC<ClusterSelectorProps> = ({
  clusters,
  selectedCluster,
  onSelectCluster,
  loading = false,
  disabled = false,
}) => {
  const handleChange = (event: SelectChangeEvent<string>) => {
    const clusterName = event.target.value;
    if (clusterName) {
      onSelectCluster(clusterName);
    }
  };

  const getEnvironmentChip = (environment: ClusterEnvironment) => {
    const colors = ENVIRONMENT_COLORS[environment];
    return (
      <Chip
        label={environment.toUpperCase()}
        size="small"
        sx={{
          backgroundColor: colors.primary,
          color: 'white',
          fontWeight: 'bold',
          fontSize: '0.7rem',
          height: '20px',
          ml: 1,
        }}
      />
    );
  };

  const renderClusterMenuItem = (cluster: ClusterInfo) => {
    const environment = getClusterEnvironment(cluster.name);
    const colors = ENVIRONMENT_COLORS[environment];

    return (
      <MenuItem
        key={cluster.name}
        value={cluster.name}
        sx={{
          borderLeft: `4px solid ${colors.primary}`,
          '&:hover': {
            backgroundColor: `${colors.light}20`,
          },
          '&.Mui-selected': {
            backgroundColor: `${colors.light}30`,
            '&:hover': {
              backgroundColor: `${colors.light}40`,
            },
          },
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Typography variant="body1" sx={{ fontWeight: 'medium' }}>
              {cluster.name}
            </Typography>
            {getEnvironmentChip(environment)}
          </Box>
          <Typography variant="caption" color="text.secondary">
            {cluster.region} • v{cluster.version} • {cluster.status}
          </Typography>
        </Box>
      </MenuItem>
    );
  };

  const renderSelectedValue = (value: string) => {
    const cluster = clusters.find((c) => c.name === value);
    if (!cluster) return value;

    const environment = getClusterEnvironment(cluster.name);
    const colors = ENVIRONMENT_COLORS[environment];

    return (
      <Box sx={{ display: 'flex', alignItems: 'center' }}>
        <Box
          sx={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: colors.primary,
            mr: 1,
          }}
        />
        <Typography variant="body2" sx={{ fontWeight: 'medium' }}>
          {cluster.name}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
          ({cluster.region})
        </Typography>
      </Box>
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <CircularProgress size={20} />
        <Typography variant="body2" color="text.secondary">
          Discovering clusters...
        </Typography>
      </Box>
    );
  }

  if (clusters.length === 0) {
    return (
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          No clusters found. Please check your credentials and permissions.
        </Typography>
      </Box>
    );
  }

  return (
    <FormControl fullWidth disabled={disabled}>
      <InputLabel id="cluster-selector-label">Select Cluster</InputLabel>
      <Select
        labelId="cluster-selector-label"
        id="cluster-selector"
        value={selectedCluster || ''}
        label="Select Cluster"
        onChange={handleChange}
        renderValue={renderSelectedValue}
        sx={{
          '& .MuiOutlinedInput-notchedOutline': selectedCluster
            ? {
                borderColor: ENVIRONMENT_COLORS[
                  getClusterEnvironment(selectedCluster)
                ].primary,
                borderWidth: 2,
              }
            : undefined,
        }}
      >
        {clusters.map(renderClusterMenuItem)}
      </Select>
    </FormControl>
  );
};

export default ClusterSelector;
