/**
 * AWS Kion credentials interface
 * Used for authenticating with AWS EKS clusters
 */
export interface KionCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken: string;
  region: string;
}

/**
 * Credential validation errors
 */
export interface CredentialValidationErrors {
  accessKeyId?: string;
  secretAccessKey?: string;
  sessionToken?: string;
  region?: string;
}

/**
 * AWS regions supported by the application
 */
export const AWS_REGIONS = [
  'us-east-1',
  'us-east-2',
  'us-west-1',
  'us-west-2',
  'eu-west-1',
  'eu-west-2',
  'eu-central-1',
  'ap-southeast-1',
  'ap-southeast-2',
  'ap-northeast-1',
  'ap-south-1',
] as const;

export type AwsRegion = typeof AWS_REGIONS[number];
