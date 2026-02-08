import { KionCredentials, CredentialValidationErrors, AWS_REGIONS } from '../types/credentials';

/**
 * AWS Access Key ID pattern: AKIA followed by 16 alphanumeric characters
 * Example: AKIAIOSFODNN7EXAMPLE
 */
const ACCESS_KEY_PATTERN = /^AKIA[A-Z0-9]{16}$/;

/**
 * AWS Secret Access Key pattern: 40 characters (base64-like)
 */
const SECRET_KEY_PATTERN = /^[A-Za-z0-9/+]{39}[A-Za-z0-9/+=]$/;

/**
 * AWS Session Token pattern: Variable length, typically 100-1000 characters
 * Contains alphanumeric and special characters
 */
const SESSION_TOKEN_MIN_LENGTH = 100;
const SESSION_TOKEN_MAX_LENGTH = 2000;

/**
 * Validates AWS Kion credentials format
 * @param credentials - The credentials to validate
 * @returns Object containing validation errors, empty if valid
 */
export function validateCredentials(
  credentials: KionCredentials
): CredentialValidationErrors {
  const errors: CredentialValidationErrors = {};

  // Validate Access Key ID
  if (!credentials.accessKeyId) {
    errors.accessKeyId = 'Access Key ID is required';
  } else if (!ACCESS_KEY_PATTERN.test(credentials.accessKeyId)) {
    errors.accessKeyId = 'Invalid Access Key ID format (should start with AKIA and be 20 characters)';
  }

  // Validate Secret Access Key
  if (!credentials.secretAccessKey) {
    errors.secretAccessKey = 'Secret Access Key is required';
  } else if (!SECRET_KEY_PATTERN.test(credentials.secretAccessKey)) {
    errors.secretAccessKey = 'Invalid Secret Access Key format (should be 40 characters)';
  }

  // Validate Session Token
  if (!credentials.sessionToken) {
    errors.sessionToken = 'Session Token is required';
  } else if (credentials.sessionToken.length < SESSION_TOKEN_MIN_LENGTH) {
    errors.sessionToken = `Session Token is too short (minimum ${SESSION_TOKEN_MIN_LENGTH} characters)`;
  } else if (credentials.sessionToken.length > SESSION_TOKEN_MAX_LENGTH) {
    errors.sessionToken = `Session Token is too long (maximum ${SESSION_TOKEN_MAX_LENGTH} characters)`;
  }

  // Validate Region
  if (!credentials.region) {
    errors.region = 'Region is required';
  } else if (!AWS_REGIONS.includes(credentials.region as any)) {
    errors.region = 'Invalid AWS region';
  }

  return errors;
}

/**
 * Checks if credentials object has all required fields filled
 * @param credentials - The credentials to check
 * @returns true if all fields are non-empty
 */
export function hasAllFields(credentials: KionCredentials): boolean {
  return !!(
    credentials.accessKeyId &&
    credentials.secretAccessKey &&
    credentials.sessionToken &&
    credentials.region
  );
}

/**
 * Sanitizes credentials for logging (masks sensitive data)
 * @param credentials - The credentials to sanitize
 * @returns Sanitized credentials object safe for logging
 */
export function sanitizeCredentialsForLogging(credentials: KionCredentials): object {
  return {
    accessKeyId: credentials.accessKeyId ? `${credentials.accessKeyId.substring(0, 8)}...` : '',
    secretAccessKey: '***REDACTED***',
    sessionToken: '***REDACTED***',
    region: credentials.region,
  };
}
