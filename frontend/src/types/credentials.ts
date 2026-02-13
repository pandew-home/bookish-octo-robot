/**
 * Authentication mode type
 */
export type AuthMode = 'aws' | 'kubeconfig';

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
 * Kubeconfig credentials interface (legacy - file path based)
 * Used for authenticating with local clusters via kubeconfig file path
 */
export interface KubeconfigCredentials {
  kubeconfigPath: string;
}

/**
 * Kubeconfig context info
 */
export interface KubeconfigContext {
  name: string;
  cluster: string;
}

/**
 * Kubeconfig upload interface
 * Used for streaming kubeconfig content from browser to backend
 */
export interface KubeconfigUpload {
  content: string;  // Raw YAML content of kubeconfig
}

/**
 * Kubeconfig parse response
 * Returned when parsing kubeconfig content to get available contexts
 */
export interface KubeconfigParseResponse {
  contexts: KubeconfigContext[];
  currentContext: string | null;
}

/**
 * Kubeconfig authentication request
 * Used to authenticate with a specific context from uploaded kubeconfig
 */
export interface KubeconfigAuthRequest {
  content: string;  // Raw YAML content of kubeconfig
  context: string;  // Selected context name
}

/**
 * Credential validation errors
 */
export interface CredentialValidationErrors {
  accessKeyId?: string;
  secretAccessKey?: string;
  sessionToken?: string;
  region?: string;
  kubeconfigPath?: string;
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
