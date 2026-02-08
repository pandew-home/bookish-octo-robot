import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import LoginForm from './LoginForm';
import { KionCredentials } from '../types/credentials';

describe('LoginForm', () => {
  const mockOnLogin = jest.fn();

  beforeEach(() => {
    mockOnLogin.mockClear();
  });

  describe('Rendering', () => {
    it('should render all form fields', () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      expect(screen.getByLabelText(/access key id/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/secret access key/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/session token/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/aws region/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    it('should render help text for each field', () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      expect(screen.getByText(/AWS access key ID from Kion/i)).toBeInTheDocument();
      expect(screen.getByText(/AWS secret access key from Kion/i)).toBeInTheDocument();
      expect(screen.getByText(/AWS session token from Kion/i)).toBeInTheDocument();
      expect(screen.getByText(/Select the AWS region/i)).toBeInTheDocument();
    });

    it('should render link to Kion console', () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const link = screen.getByText(/Get them from Kion Console/i);
      expect(link).toBeInTheDocument();
      expect(link.closest('a')).toHaveAttribute('href', 'https://kion.example.com');
      expect(link.closest('a')).toHaveAttribute('target', '_blank');
    });

    it('should have us-east-1 as default region', () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      // MUI Select renders the value in a div, not as a select element
      expect(screen.getByText('us-east-1')).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('should show error for invalid access key format', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, 'INVALID_KEY');
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Invalid Access Key ID format/i)).toBeInTheDocument();
      });

      expect(mockOnLogin).not.toHaveBeenCalled();
    });

    it('should show error for invalid secret key format', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, 'AKIAIOSFODNN7EXAMPLE');
      await userEvent.type(secretKeyField, 'short');
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Invalid Secret Access Key format/i)).toBeInTheDocument();
      });

      expect(mockOnLogin).not.toHaveBeenCalled();
    });

    it('should show error for session token that is too short', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, 'AKIAIOSFODNN7EXAMPLE');
      await userEvent.type(secretKeyField, 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY');
      await userEvent.type(sessionTokenField, 'short');
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Session Token is too short/i)).toBeInTheDocument();
      });

      expect(mockOnLogin).not.toHaveBeenCalled();
    });

    it('should show error for empty required fields', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const submitButton = screen.getByRole('button', { name: /login/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Access Key ID is required/i)).toBeInTheDocument();
        expect(screen.getByText(/Secret Access Key is required/i)).toBeInTheDocument();
        expect(screen.getByText(/Session Token is required/i)).toBeInTheDocument();
      });

      expect(mockOnLogin).not.toHaveBeenCalled();
    });

    it('should clear field error when user starts typing', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      // Submit empty form to trigger validation
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Access Key ID is required/i)).toBeInTheDocument();
      });

      // Start typing in the field
      await userEvent.type(accessKeyField, 'A');

      await waitFor(() => {
        expect(screen.queryByText(/Access Key ID is required/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Form Submission', () => {
    const validCredentials: KionCredentials = {
      accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
      secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
      sessionToken: 'A'.repeat(150), // Valid length session token
      region: 'us-east-1',
    };

    it('should call onLogin with valid credentials', async () => {
      mockOnLogin.mockResolvedValue(undefined);
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, validCredentials.accessKeyId);
      await userEvent.type(secretKeyField, validCredentials.secretAccessKey);
      await userEvent.type(sessionTokenField, validCredentials.sessionToken);
      // Note: Region is already set to us-east-1 by default, which matches validCredentials

      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnLogin).toHaveBeenCalledWith(expect.objectContaining({
          accessKeyId: validCredentials.accessKeyId,
          secretAccessKey: validCredentials.secretAccessKey,
          sessionToken: validCredentials.sessionToken,
        }));
      });
    });

    it('should disable form fields during submission', async () => {
      mockOnLogin.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)));
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, validCredentials.accessKeyId);
      await userEvent.type(secretKeyField, validCredentials.secretAccessKey);
      await userEvent.type(sessionTokenField, validCredentials.sessionToken);

      fireEvent.click(submitButton);

      // Check that fields are disabled during submission
      expect(accessKeyField).toBeDisabled();
      expect(secretKeyField).toBeDisabled();
      expect(sessionTokenField).toBeDisabled();
      expect(submitButton).toBeDisabled();

      // Wait for submission to complete
      await waitFor(() => {
        expect(mockOnLogin).toHaveBeenCalled();
      });
    });

    it('should show loading state during submission', async () => {
      mockOnLogin.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)));
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, validCredentials.accessKeyId);
      await userEvent.type(secretKeyField, validCredentials.secretAccessKey);
      await userEvent.type(sessionTokenField, validCredentials.sessionToken);

      fireEvent.click(submitButton);

      // Check for loading text
      expect(screen.getByText(/Authenticating.../i)).toBeInTheDocument();

      await waitFor(() => {
        expect(mockOnLogin).toHaveBeenCalled();
      });
    });
  });

  describe('Error Handling', () => {
    const validCredentials: KionCredentials = {
      accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
      secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
      sessionToken: 'A'.repeat(150),
      region: 'us-east-1',
    };

    it('should display error message when login fails', async () => {
      const errorMessage = 'Invalid credentials';
      mockOnLogin.mockRejectedValue(new Error(errorMessage));
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, validCredentials.accessKeyId);
      await userEvent.type(secretKeyField, validCredentials.secretAccessKey);
      await userEvent.type(sessionTokenField, validCredentials.sessionToken);

      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      });
    });

    it('should display API error message from response', async () => {
      const apiError = {
        response: {
          data: {
            detail: 'STS GetCallerIdentity failed: Invalid security token',
          },
        },
      };
      mockOnLogin.mockRejectedValue(apiError);
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, validCredentials.accessKeyId);
      await userEvent.type(secretKeyField, validCredentials.secretAccessKey);
      await userEvent.type(sessionTokenField, validCredentials.sessionToken);

      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/STS GetCallerIdentity failed/i)).toBeInTheDocument();
      });
    });

    it('should display default error message when error has no message', async () => {
      mockOnLogin.mockRejectedValue({});
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, validCredentials.accessKeyId);
      await userEvent.type(secretKeyField, validCredentials.secretAccessKey);
      await userEvent.type(sessionTokenField, validCredentials.sessionToken);

      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Failed to authenticate/i)).toBeInTheDocument();
      });
    });

    it('should clear error message when user makes changes', async () => {
      mockOnLogin.mockRejectedValue(new Error('Invalid credentials'));
      render(<LoginForm onLogin={mockOnLogin} />);

      const accessKeyField = screen.getByLabelText(/access key id/i);
      const secretKeyField = screen.getByLabelText(/secret access key/i);
      const sessionTokenField = screen.getByLabelText(/session token/i);
      const submitButton = screen.getByRole('button', { name: /login/i });

      await userEvent.type(accessKeyField, 'AKIAIOSFODNN7EXAMPLE');
      await userEvent.type(secretKeyField, 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY');
      await userEvent.type(sessionTokenField, 'A'.repeat(150));

      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Invalid credentials/i)).toBeInTheDocument();
      });

      // Type in a field to clear the error
      await userEvent.type(accessKeyField, 'X');

      await waitFor(() => {
        expect(screen.queryByText(/Invalid credentials/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Region Selection', () => {
    it('should allow selecting different regions', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const regionField = screen.getByLabelText(/aws region/i);

      // Click to open the dropdown
      fireEvent.mouseDown(regionField);

      // Wait for the dropdown to appear and select an option
      const euWest1Option = await screen.findByText('eu-west-1');
      fireEvent.click(euWest1Option);

      // Verify the selection
      await waitFor(() => {
        expect(screen.getByText('eu-west-1')).toBeInTheDocument();
      });
    });

    it('should include all supported regions in dropdown', async () => {
      render(<LoginForm onLogin={mockOnLogin} />);

      const regionField = screen.getByLabelText(/aws region/i);

      // Click to open the dropdown
      fireEvent.mouseDown(regionField);

      // Wait for dropdown to open
      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      // Verify at least some regions are present (using getAllByText since region appears in both the field and dropdown)
      expect(screen.getAllByText('us-east-1').length).toBeGreaterThan(0);
      expect(screen.getAllByText('eu-west-1').length).toBeGreaterThan(0);
      expect(screen.getAllByText('ap-southeast-1').length).toBeGreaterThan(0);
    });
  });
});
