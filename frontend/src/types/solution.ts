/**
 * Solution interface for knowledge base submissions
 * Represents a troubleshooting solution that can be saved and shared
 */
export interface Solution {
  id?: string;
  title: string;
  description: string;
  tags: string[];
  runbookUrl?: string;
  automationScript?: string;
  estimatedFixTime?: number;
  sourceConversation?: string;
  createdBy?: string;
  createdAt?: string;
  usageCount?: number;
  successCount?: number;
}

/**
 * Solution validation errors
 */
export interface SolutionValidationErrors {
  title?: string;
  description?: string;
  tags?: string;
  runbookUrl?: string;
  estimatedFixTime?: string;
}

/**
 * Validate solution fields
 * @param solution - The solution to validate
 * @returns Validation errors object (empty if valid)
 */
export function validateSolution(solution: Partial<Solution>): SolutionValidationErrors {
  const errors: SolutionValidationErrors = {};

  // Title validation
  if (!solution.title || solution.title.trim().length === 0) {
    errors.title = 'Title is required';
  } else if (solution.title.length < 5) {
    errors.title = 'Title must be at least 5 characters';
  } else if (solution.title.length > 200) {
    errors.title = 'Title must be less than 200 characters';
  }

  // Description validation
  if (!solution.description || solution.description.trim().length === 0) {
    errors.description = 'Description is required';
  } else if (solution.description.length < 20) {
    errors.description = 'Description must be at least 20 characters';
  } else if (solution.description.length > 5000) {
    errors.description = 'Description must be less than 5000 characters';
  }

  // Tags validation
  if (!solution.tags || solution.tags.length === 0) {
    errors.tags = 'At least one tag is required';
  } else if (solution.tags.length > 10) {
    errors.tags = 'Maximum 10 tags allowed';
  } else {
    // Validate individual tags
    const invalidTags = solution.tags.filter(tag => 
      tag.length < 2 || tag.length > 30 || !/^[a-zA-Z0-9-_]+$/.test(tag)
    );
    if (invalidTags.length > 0) {
      errors.tags = 'Tags must be 2-30 characters and contain only letters, numbers, hyphens, and underscores';
    }
  }

  // Runbook URL validation (optional)
  if (solution.runbookUrl && solution.runbookUrl.trim().length > 0) {
    try {
      new URL(solution.runbookUrl);
    } catch {
      errors.runbookUrl = 'Invalid URL format';
    }
  }

  // Estimated fix time validation (optional)
  if (solution.estimatedFixTime !== undefined && solution.estimatedFixTime !== null) {
    if (solution.estimatedFixTime < 1) {
      errors.estimatedFixTime = 'Estimated fix time must be at least 1 minute';
    } else if (solution.estimatedFixTime > 1440) {
      errors.estimatedFixTime = 'Estimated fix time must be less than 1440 minutes (24 hours)';
    }
  }

  return errors;
}

/**
 * Common tags for solutions
 */
export const COMMON_TAGS = [
  'pod-issue',
  'deployment',
  'service',
  'networking',
  'storage',
  'argocd',
  'security',
  'performance',
  'crashloop',
  'oom',
  'imagepull',
  'dns',
  'ingress',
  'pvc',
  'rbac',
  'node',
  'scaling',
  'rollback',
] as const;

export type CommonTag = typeof COMMON_TAGS[number];
