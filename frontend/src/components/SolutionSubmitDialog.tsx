import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Chip,
  Stack,
  Typography,
  Alert,
  CircularProgress,
  Autocomplete,
  InputAdornment,
} from '@mui/material';
import {
  Save as SaveIcon,
  Close as CloseIcon,
  Timer as TimerIcon,
  Link as LinkIcon,
  Code as CodeIcon,
} from '@mui/icons-material';
import { Solution, SolutionValidationErrors, validateSolution, COMMON_TAGS } from '../types/solution';

/**
 * Props for SolutionSubmitDialog component
 */
interface SolutionSubmitDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (solution: Solution) => Promise<void>;
  initialContent?: string;
  conversationId?: string;
}

/**
 * SolutionSubmitDialog Component
 * 
 * Dialog for submitting solutions to the knowledge base.
 * Users can save successful troubleshooting conversations to the shared knowledge base for team benefit.
 * 
 * Features:
 * - Pre-fill from chat conversation context
 * - Validation for required fields
 * - Tag suggestions and custom tags
 * - Optional runbook URL and automation script
 * - Estimated fix time input
 * - Submission to POST /api/solutions
 */
export const SolutionSubmitDialog: React.FC<SolutionSubmitDialogProps> = ({
  open,
  onClose,
  onSubmit,
  initialContent,
  conversationId,
}) => {
  const [solution, setSolution] = useState<Partial<Solution>>({
    title: '',
    description: initialContent || '',
    tags: [],
    runbookUrl: '',
    automationScript: '',
    estimatedFixTime: undefined,
    sourceConversation: conversationId,
  });

  const [errors, setErrors] = useState<SolutionValidationErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [tagInput, setTagInput] = useState('');

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (open) {
      setSolution({
        title: '',
        description: initialContent || '',
        tags: [],
        runbookUrl: '',
        automationScript: '',
        estimatedFixTime: undefined,
        sourceConversation: conversationId,
      });
      setErrors({});
      setSubmitError(null);
      setSubmitSuccess(false);
    }
  }, [open, initialContent, conversationId]);

  // Handle field changes
  const handleChange = (field: keyof Solution, value: any) => {
    setSolution(prev => ({ ...prev, [field]: value }));
    // Clear error for this field
    if (errors[field as keyof SolutionValidationErrors]) {
      setErrors(prev => ({ ...prev, [field]: undefined }));
    }
  };

  // Handle tag removal
  const handleRemoveTag = (tagToRemove: string) => {
    handleChange('tags', solution.tags?.filter(tag => tag !== tagToRemove) || []);
  };

  // Handle form submission
  const handleSubmit = async () => {
    // Validate solution
    const validationErrors = validateSolution(solution);
    
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await onSubmit(solution as Solution);
      setSubmitSuccess(true);
      
      // Close dialog after short delay to show success message
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to submit solution');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle dialog close
  const handleClose = () => {
    if (!isSubmitting) {
      onClose();
    }
  };

  return (
    <Dialog 
      open={open} 
      onClose={handleClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { minHeight: '60vh' }
      }}
    >
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="h6">Save Solution to Knowledge Base</Typography>
          <Button
            onClick={handleClose}
            disabled={isSubmitting}
            sx={{ minWidth: 'auto', p: 0.5 }}
          >
            <CloseIcon />
          </Button>
        </Box>
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={3}>
          {/* Success Message */}
          {submitSuccess && (
            <Alert severity="success">
              Solution saved successfully! It will be available to all team members.
            </Alert>
          )}

          {/* Error Message */}
          {submitError && (
            <Alert severity="error">
              {submitError}
            </Alert>
          )}

          {/* Info Message */}
          {conversationId && (
            <Alert severity="info">
              This solution will be linked to the conversation for future reference.
            </Alert>
          )}

          {/* Title Field */}
          <TextField
            label="Title"
            required
            fullWidth
            value={solution.title}
            onChange={(e) => handleChange('title', e.target.value)}
            error={!!errors.title}
            helperText={errors.title || 'A concise title describing the solution (5-200 characters)'}
            disabled={isSubmitting || submitSuccess}
            placeholder="e.g., Fix CrashLoopBackOff due to missing ConfigMap"
          />

          {/* Description Field */}
          <TextField
            label="Description"
            required
            fullWidth
            multiline
            rows={8}
            value={solution.description}
            onChange={(e) => handleChange('description', e.target.value)}
            error={!!errors.description}
            helperText={errors.description || 'Detailed description of the problem and solution (20-5000 characters)'}
            disabled={isSubmitting || submitSuccess}
            placeholder="Describe the problem, root cause, and step-by-step solution..."
          />

          {/* Tags Field */}
          <Box>
            <Autocomplete
              multiple
              freeSolo
              options={COMMON_TAGS.filter(tag => !solution.tags?.includes(tag))}
              value={solution.tags || []}
              onChange={(_, newValue) => handleChange('tags', newValue)}
              inputValue={tagInput}
              onInputChange={(_, newInputValue) => setTagInput(newInputValue)}
              renderTags={(value, getTagProps) =>
                value.map((option, index) => (
                  <Chip
                    label={option}
                    {...getTagProps({ index })}
                    onDelete={() => handleRemoveTag(option)}
                    disabled={isSubmitting || submitSuccess}
                  />
                ))
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Tags"
                  required
                  error={!!errors.tags}
                  helperText={errors.tags || 'Add tags to categorize this solution (press Enter to add)'}
                  placeholder="Select or type tags..."
                  disabled={isSubmitting || submitSuccess}
                  InputProps={{
                    ...params.InputProps,
                    startAdornment: (
                      <>
                        {params.InputProps.startAdornment}
                      </>
                    ),
                  }}
                />
              )}
              disabled={isSubmitting || submitSuccess}
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
              Common tags: {COMMON_TAGS.slice(0, 5).join(', ')}, and more...
            </Typography>
          </Box>

          {/* Runbook URL Field (Optional) */}
          <TextField
            label="Runbook URL (Optional)"
            fullWidth
            value={solution.runbookUrl}
            onChange={(e) => handleChange('runbookUrl', e.target.value)}
            error={!!errors.runbookUrl}
            helperText={errors.runbookUrl || 'Link to detailed runbook or documentation'}
            disabled={isSubmitting || submitSuccess}
            placeholder="https://wiki.example.com/runbooks/..."
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <LinkIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />

          {/* Estimated Fix Time Field (Optional) */}
          <TextField
            label="Estimated Fix Time (Optional)"
            type="number"
            fullWidth
            value={solution.estimatedFixTime || ''}
            onChange={(e) => handleChange('estimatedFixTime', e.target.value ? parseInt(e.target.value) : undefined)}
            error={!!errors.estimatedFixTime}
            helperText={errors.estimatedFixTime || 'Estimated time to implement this solution (in minutes)'}
            disabled={isSubmitting || submitSuccess}
            placeholder="e.g., 15"
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <TimerIcon fontSize="small" />
                </InputAdornment>
              ),
              endAdornment: (
                <InputAdornment position="end">
                  <Typography variant="caption" color="text.secondary">
                    minutes
                  </Typography>
                </InputAdornment>
              ),
            }}
            inputProps={{
              min: 1,
              max: 1440,
            }}
          />

          {/* Automation Script Field (Optional) */}
          <TextField
            label="Automation Script (Optional)"
            fullWidth
            multiline
            rows={4}
            value={solution.automationScript}
            onChange={(e) => handleChange('automationScript', e.target.value)}
            helperText="Shell script or commands to automate this solution"
            disabled={isSubmitting || submitSuccess}
            placeholder="#!/bin/bash&#10;kubectl apply -f fix.yaml&#10;kubectl rollout restart deployment/app"
            InputProps={{
              startAdornment: (
                <InputAdornment position="start" sx={{ alignSelf: 'flex-start', mt: 1 }}>
                  <CodeIcon fontSize="small" />
                </InputAdornment>
              ),
              sx: { fontFamily: 'monospace', fontSize: '0.875rem' }
            }}
          />
        </Stack>
      </DialogContent>

      <DialogActions sx={{ p: 2 }}>
        <Button
          onClick={handleClose}
          disabled={isSubmitting}
          variant="outlined"
        >
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={isSubmitting || submitSuccess}
          variant="contained"
          startIcon={isSubmitting ? <CircularProgress size={16} /> : <SaveIcon />}
        >
          {isSubmitting ? 'Saving...' : submitSuccess ? 'Saved!' : 'Save Solution'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
