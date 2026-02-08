# LoginForm Component

## Overview

The `LoginForm` component provides a user interface for authenticating with AWS Kion credentials. It's the entry point for users to access the DevOps Chatbot v2 application.

## Features

- **Credential Input Fields**:
  - Access Key ID (with format validation)
  - Secret Access Key (password field)
  - Session Token (password field)
  - AWS Region (dropdown selector)

- **Format Validation**:
  - Access Key ID: Must match pattern `AKIA[A-Z0-9]{16}` (20 characters total)
  - Secret Access Key: Must be exactly 40 characters
  - Session Token: Must be between 100-2000 characters
  - Region: Must be a valid AWS region from the predefined list

- **User Experience**:
  - Real-time validation feedback
  - Clear error messages
  - Help text for each field
  - Link to Kion console for credential retrieval
  - Loading state during authentication
  - Disabled fields during submission

- **Error Handling**:
  - Client-side validation before submission
  - Server error display
  - Field-specific error messages

## Usage

```tsx
import LoginForm from './components/LoginForm';
import { KionCredentials } from './types/credentials';

function App() {
  const handleLogin = async (credentials: KionCredentials) => {
    // Submit credentials to backend API
    await authApi.login(credentials);
  };

  return <LoginForm onLogin={handleLogin} />;
}
```

## Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `onLogin` | `(credentials: KionCredentials) => Promise<void>` | Yes | Callback function called when form is submitted with valid credentials |

## Validation Rules

### Access Key ID
- Required field
- Must start with "AKIA"
- Must be exactly 20 characters
- Must contain only uppercase letters and numbers

### Secret Access Key
- Required field
- Must be exactly 40 characters
- Can contain letters, numbers, and special characters (/, +, =)

### Session Token
- Required field
- Minimum length: 100 characters
- Maximum length: 2000 characters
- Temporary credential from Kion

### Region
- Required field
- Must be one of the supported AWS regions

## Supported AWS Regions

- us-east-1
- us-east-2
- us-west-1
- us-west-2
- eu-west-1
- eu-west-2
- eu-central-1
- ap-southeast-1
- ap-southeast-2
- ap-northeast-1
- ap-south-1

## API Integration

The component submits credentials to the backend endpoint:

```
POST /api/credentials/aws
```

Request body:
```json
{
  "access_key_id": "AKIAIOSFODNN7EXAMPLE",
  "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "session_token": "FwoGZXIvYXdzEBYaDH...",
  "region": "us-east-1"
}
```

## Related Files

- `src/types/credentials.ts` - TypeScript interfaces and types
- `src/utils/credentialValidator.ts` - Validation logic
- `src/services/api.ts` - API client for backend communication

## Requirements Satisfied

- **Requirement 14.1**: Display login form for Kion credentials
- **Requirement 1.1**: Accept and validate Kion AWS credentials
- **Requirement 8.6**: Validate AWS credential formats before submission
