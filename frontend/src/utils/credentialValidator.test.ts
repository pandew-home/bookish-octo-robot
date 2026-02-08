import {
  validateCredentials,
  hasAllFields,
  sanitizeCredentialsForLogging,
} from './credentialValidator';
import { KionCredentials } from '../types/credentials';

describe('credentialValidator', () => {
  describe('validateCredentials', () => {
    const validCredentials: KionCredentials = {
      accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
      secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
      sessionToken: 'A'.repeat(150),
      region: 'us-east-1',
    };

    it('should return no errors for valid credentials', () => {
      const errors = validateCredentials(validCredentials);
      expect(Object.keys(errors)).toHaveLength(0);
    });

    describe('Access Key ID validation', () => {
      it('should reject empty access key', () => {
        const credentials = { ...validCredentials, accessKeyId: '' };
        const errors = validateCredentials(credentials);
        expect(errors.accessKeyId).toBe('Access Key ID is required');
      });

      it('should reject access key not starting with AKIA', () => {
        const credentials = { ...validCredentials, accessKeyId: 'INVALID123456789012' };
        const errors = validateCredentials(credentials);
        expect(errors.accessKeyId).toContain('Invalid Access Key ID format');
      });

      it('should reject access key with wrong length', () => {
        const credentials = { ...validCredentials, accessKeyId: 'AKIA123' };
        const errors = validateCredentials(credentials);
        expect(errors.accessKeyId).toContain('Invalid Access Key ID format');
      });

      it('should reject access key with lowercase letters', () => {
        const credentials = { ...validCredentials, accessKeyId: 'AKIAiosfodnn7example' };
        const errors = validateCredentials(credentials);
        expect(errors.accessKeyId).toContain('Invalid Access Key ID format');
      });

      it('should reject access key with special characters', () => {
        const credentials = { ...validCredentials, accessKeyId: 'AKIA@#$%^&*()12345' };
        const errors = validateCredentials(credentials);
        expect(errors.accessKeyId).toContain('Invalid Access Key ID format');
      });

      it('should accept valid access key with numbers', () => {
        const credentials = { ...validCredentials, accessKeyId: 'AKIA1234567890ABCDEF' };
        const errors = validateCredentials(credentials);
        expect(errors.accessKeyId).toBeUndefined();
      });
    });

    describe('Secret Access Key validation', () => {
      it('should reject empty secret key', () => {
        const credentials = { ...validCredentials, secretAccessKey: '' };
        const errors = validateCredentials(credentials);
        expect(errors.secretAccessKey).toBe('Secret Access Key is required');
      });

      it('should reject secret key with wrong length', () => {
        const credentials = { ...validCredentials, secretAccessKey: 'short' };
        const errors = validateCredentials(credentials);
        expect(errors.secretAccessKey).toContain('Invalid Secret Access Key format');
      });

      it('should reject secret key longer than 40 characters', () => {
        const credentials = { ...validCredentials, secretAccessKey: 'A'.repeat(41) };
        const errors = validateCredentials(credentials);
        expect(errors.secretAccessKey).toContain('Invalid Secret Access Key format');
      });

      it('should accept secret key with special characters', () => {
        const credentials = {
          ...validCredentials,
          secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKY+',
        };
        const errors = validateCredentials(credentials);
        expect(errors.secretAccessKey).toBeUndefined();
      });

      it('should accept secret key with equals sign at end', () => {
        const credentials = {
          ...validCredentials,
          secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKE=',
        };
        const errors = validateCredentials(credentials);
        expect(errors.secretAccessKey).toBeUndefined();
      });
    });

    describe('Session Token validation', () => {
      it('should reject empty session token', () => {
        const credentials = { ...validCredentials, sessionToken: '' };
        const errors = validateCredentials(credentials);
        expect(errors.sessionToken).toBe('Session Token is required');
      });

      it('should reject session token shorter than minimum length', () => {
        const credentials = { ...validCredentials, sessionToken: 'A'.repeat(50) };
        const errors = validateCredentials(credentials);
        expect(errors.sessionToken).toContain('Session Token is too short');
      });

      it('should reject session token longer than maximum length', () => {
        const credentials = { ...validCredentials, sessionToken: 'A'.repeat(2001) };
        const errors = validateCredentials(credentials);
        expect(errors.sessionToken).toContain('Session Token is too long');
      });

      it('should accept session token at minimum length', () => {
        const credentials = { ...validCredentials, sessionToken: 'A'.repeat(100) };
        const errors = validateCredentials(credentials);
        expect(errors.sessionToken).toBeUndefined();
      });

      it('should accept session token at maximum length', () => {
        const credentials = { ...validCredentials, sessionToken: 'A'.repeat(2000) };
        const errors = validateCredentials(credentials);
        expect(errors.sessionToken).toBeUndefined();
      });

      it('should accept session token with typical length', () => {
        const credentials = { ...validCredentials, sessionToken: 'A'.repeat(500) };
        const errors = validateCredentials(credentials);
        expect(errors.sessionToken).toBeUndefined();
      });
    });

    describe('Region validation', () => {
      it('should reject empty region', () => {
        const credentials = { ...validCredentials, region: '' };
        const errors = validateCredentials(credentials);
        expect(errors.region).toBe('Region is required');
      });

      it('should reject invalid region', () => {
        const credentials = { ...validCredentials, region: 'invalid-region' };
        const errors = validateCredentials(credentials);
        expect(errors.region).toBe('Invalid AWS region');
      });

      it('should accept all valid regions', () => {
        const validRegions = [
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
        ];

        validRegions.forEach((region) => {
          const credentials = { ...validCredentials, region };
          const errors = validateCredentials(credentials);
          expect(errors.region).toBeUndefined();
        });
      });
    });

    describe('Multiple field validation', () => {
      it('should return errors for all invalid fields', () => {
        const credentials: KionCredentials = {
          accessKeyId: '',
          secretAccessKey: '',
          sessionToken: '',
          region: '',
        };
        const errors = validateCredentials(credentials);

        expect(errors.accessKeyId).toBeDefined();
        expect(errors.secretAccessKey).toBeDefined();
        expect(errors.sessionToken).toBeDefined();
        expect(errors.region).toBeDefined();
      });

      it('should return errors only for invalid fields', () => {
        const credentials: KionCredentials = {
          accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
          secretAccessKey: 'short',
          sessionToken: 'A'.repeat(150),
          region: 'us-east-1',
        };
        const errors = validateCredentials(credentials);

        expect(errors.accessKeyId).toBeUndefined();
        expect(errors.secretAccessKey).toBeDefined();
        expect(errors.sessionToken).toBeUndefined();
        expect(errors.region).toBeUndefined();
      });
    });
  });

  describe('hasAllFields', () => {
    it('should return true when all fields are filled', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: 'us-east-1',
      };
      expect(hasAllFields(credentials)).toBe(true);
    });

    it('should return false when access key is empty', () => {
      const credentials: KionCredentials = {
        accessKeyId: '',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: 'us-east-1',
      };
      expect(hasAllFields(credentials)).toBe(false);
    });

    it('should return false when secret key is empty', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: '',
        sessionToken: 'A'.repeat(150),
        region: 'us-east-1',
      };
      expect(hasAllFields(credentials)).toBe(false);
    });

    it('should return false when session token is empty', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: '',
        region: 'us-east-1',
      };
      expect(hasAllFields(credentials)).toBe(false);
    });

    it('should return false when region is empty', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: '',
      };
      expect(hasAllFields(credentials)).toBe(false);
    });

    it('should return false when all fields are empty', () => {
      const credentials: KionCredentials = {
        accessKeyId: '',
        secretAccessKey: '',
        sessionToken: '',
        region: '',
      };
      expect(hasAllFields(credentials)).toBe(false);
    });
  });

  describe('sanitizeCredentialsForLogging', () => {
    it('should mask secret access key', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: 'us-east-1',
      };
      const sanitized = sanitizeCredentialsForLogging(credentials);
      expect(sanitized).toHaveProperty('secretAccessKey', '***REDACTED***');
    });

    it('should mask session token', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: 'us-east-1',
      };
      const sanitized = sanitizeCredentialsForLogging(credentials);
      expect(sanitized).toHaveProperty('sessionToken', '***REDACTED***');
    });

    it('should partially show access key ID', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: 'us-east-1',
      };
      const sanitized = sanitizeCredentialsForLogging(credentials);
      expect(sanitized).toHaveProperty('accessKeyId', 'AKIAIOSF...');
    });

    it('should preserve region', () => {
      const credentials: KionCredentials = {
        accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
        secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        sessionToken: 'A'.repeat(150),
        region: 'us-west-2',
      };
      const sanitized = sanitizeCredentialsForLogging(credentials);
      expect(sanitized).toHaveProperty('region', 'us-west-2');
    });

    it('should handle empty credentials', () => {
      const credentials: KionCredentials = {
        accessKeyId: '',
        secretAccessKey: '',
        sessionToken: '',
        region: '',
      };
      const sanitized = sanitizeCredentialsForLogging(credentials);
      expect(sanitized).toHaveProperty('accessKeyId', '');
      expect(sanitized).toHaveProperty('secretAccessKey', '***REDACTED***');
      expect(sanitized).toHaveProperty('sessionToken', '***REDACTED***');
      expect(sanitized).toHaveProperty('region', '');
    });
  });
});
