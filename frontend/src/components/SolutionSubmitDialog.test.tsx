import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { SolutionSubmitDialog } from './SolutionSubmitDialog';
import { Solution } from '../types/solution';

describe('SolutionSubmitDialog', () => {
  const mockOnClose = jest.fn();
  const mockOnSubmit = jest.fn();

  beforeEach(() => {
    mockOnClose.mockClear();
    mockOnSubmit.mockClear();
  });

  describe('Rendering', () => {
    it('should render dialog when open', () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByText('Save Solution to Knowledge Base')).toBeInTheDocument();
      expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/tags/i)).toBeInTheDocument();
    });

    it('should not render dialog when closed', () => {
      render(
        <SolutionSubmitDialog
          open={false}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.queryByText('Save Solution to Knowledge Base')).not.toBeInTheDocument();
    });

    it('should render all form fields', () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/tags/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/runbook url/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/estimated fix time/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/automation script/i)).toBeInTheDocument();
    });

    it('should render action buttons', () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /save solution/i })).toBeInTheDocument();
    });

    it('should show info message when conversationId is provided', () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
          conversationId="conv-123"
        />
      );

      expect(screen.getByText(/linked to the conversation/i)).toBeInTheDocument();
    });
  });

  describe('Pre-fill from Conversation', () => {
    it('should pre-fill description with initialContent', () => {
      const initialContent = 'This is a pre-filled description from the conversation.';
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
          initialContent={initialContent}
        />
      );

      const descriptionField = screen.getByLabelText(/description/i) as HTMLTextAreaElement;
      expect(descriptionField.value).toBe(initialContent);
    });

    it('should set sourceConversation when conversationId is provided', async () => {
      mockOnSubmit.mockResolvedValue(undefined);
      const conversationId = 'conv-123';

      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
          conversationId={conversationId}
        />
      );

      // Fill in required fields
      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await userEvent.type(titleField, 'Test Solution Title');
      await userEvent.type(descriptionField, 'This is a detailed description of the solution.');
      await userEvent.type(tagsField, 'pod-issue{enter}');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            sourceConversation: conversationId,
          })
        );
      });
    });

    it('should reset form when dialog reopens', async () => {
      const { rerender } = render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
          initialContent="Initial content"
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      await userEvent.type(titleField, 'Some title');

      // Close dialog
      rerender(
        <SolutionSubmitDialog
          open={false}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
          initialContent="Initial content"
        />
      );

      // Reopen with different content
      rerender(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
          initialContent="New content"
        />
      );

      const descriptionField = screen.getByLabelText(/description/i) as HTMLTextAreaElement;
      expect(descriptionField.value).toBe('New content');
      expect((screen.getByLabelText(/title/i) as HTMLInputElement).value).toBe('');
    });
  });

  describe('Field Validation', () => {
    it('should show error for empty title', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/title is required/i)).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error for title that is too short', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      await userEvent.type(titleField, 'abc');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/title must be at least 5 characters/i)).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error for empty description', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/description is required/i)).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error for description that is too short', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const descriptionField = screen.getByLabelText(/description/i);
      await userEvent.type(descriptionField, 'Too short');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/description must be at least 20 characters/i)).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error for missing tags', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/at least one tag is required/i)).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error for invalid runbook URL', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);
      const runbookField = screen.getByLabelText(/runbook url/i);

      await userEvent.type(titleField, 'Valid Title Here');
      await userEvent.type(descriptionField, 'This is a valid description with enough characters.');
      await userEvent.type(tagsField, 'pod-issue{enter}');
      await userEvent.type(runbookField, 'not-a-valid-url');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/invalid url format/i)).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should clear field error when user starts typing', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const submitButton = screen.getByRole('button', { name: /save solution/i });

      // Submit to trigger validation
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/title is required/i)).toBeInTheDocument();
      });

      // Start typing
      await userEvent.type(titleField, 'T');

      await waitFor(() => {
        expect(screen.queryByText(/title is required/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Tag Management', () => {
    it('should allow adding tags by pressing Enter', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const tagsField = screen.getByLabelText(/tags/i);
      await userEvent.type(tagsField, 'pod-issue{enter}');

      expect(screen.getByText('pod-issue')).toBeInTheDocument();
    });

    it('should allow adding multiple tags', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const tagsField = screen.getByLabelText(/tags/i);
      await userEvent.type(tagsField, 'pod-issue{enter}');
      await userEvent.type(tagsField, 'crashloop{enter}');
      await userEvent.type(tagsField, 'oom{enter}');

      expect(screen.getByText('pod-issue')).toBeInTheDocument();
      expect(screen.getByText('crashloop')).toBeInTheDocument();
      expect(screen.getByText('oom')).toBeInTheDocument();
    });

    it('should allow removing tags', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const tagsField = screen.getByLabelText(/tags/i);
      await userEvent.type(tagsField, 'pod-issue{enter}');

      expect(screen.getByText('pod-issue')).toBeInTheDocument();

      // Find and click the delete button on the chip
      const deleteButton = screen.getByTestId('CancelIcon');
      fireEvent.click(deleteButton);

      await waitFor(() => {
        expect(screen.queryByText('pod-issue')).not.toBeInTheDocument();
      });
    });

    it('should suggest common tags', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByText(/common tags:/i)).toBeInTheDocument();
    });
  });

  describe('Form Submission', () => {
    const validSolution = {
      title: 'Fix CrashLoopBackOff due to missing ConfigMap',
      description: 'The pod was crashing because the ConfigMap was not created. Create the ConfigMap and restart the deployment.',
      tags: ['pod-issue', 'crashloop'],
    };

    it('should call onSubmit with valid solution data', async () => {
      mockOnSubmit.mockResolvedValue(undefined);
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      fireEvent.change(titleField, { target: { value: validSolution.title } });
      fireEvent.change(descriptionField, { target: { value: validSolution.description } });
      await userEvent.type(tagsField, 'pod-issue{enter}');
      await userEvent.type(tagsField, 'crashloop{enter}');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            title: validSolution.title,
            description: validSolution.description,
            tags: validSolution.tags,
          })
        );
      });
    }, 10000);

    it('should include optional fields when provided', async () => {
      mockOnSubmit.mockResolvedValue(undefined);
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);
      const runbookField = screen.getByLabelText(/runbook url/i);
      const fixTimeField = screen.getByLabelText(/estimated fix time/i);
      const scriptField = screen.getByLabelText(/automation script/i);

      fireEvent.change(titleField, { target: { value: validSolution.title } });
      fireEvent.change(descriptionField, { target: { value: validSolution.description } });
      await userEvent.type(tagsField, 'pod-issue{enter}');
      fireEvent.change(runbookField, { target: { value: 'https://wiki.example.com/runbooks/configmap-fix' } });
      fireEvent.change(fixTimeField, { target: { value: '15' } });
      fireEvent.change(scriptField, { target: { value: 'kubectl apply -f configmap.yaml' } });

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            runbookUrl: 'https://wiki.example.com/runbooks/configmap-fix',
            estimatedFixTime: 15,
            automationScript: 'kubectl apply -f configmap.yaml',
          })
        );
      });
    }, 10000);

    it('should disable form fields during submission', async () => {
      mockOnSubmit.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)));
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await userEvent.type(titleField, validSolution.title);
      await userEvent.type(descriptionField, validSolution.description);
      await userEvent.type(tagsField, 'pod-issue{enter}');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      // Check that fields are disabled during submission
      expect(titleField).toBeDisabled();
      expect(descriptionField).toBeDisabled();
      expect(tagsField).toBeDisabled();
      expect(submitButton).toBeDisabled();

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled();
      });
    });

    it('should show loading state during submission', async () => {
      mockOnSubmit.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)));
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await userEvent.type(titleField, validSolution.title);
      await userEvent.type(descriptionField, validSolution.description);
      await userEvent.type(tagsField, 'pod-issue{enter}');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      expect(screen.getByText(/saving.../i)).toBeInTheDocument();

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled();
      });
    });

    it('should show success message after successful submission', async () => {
      mockOnSubmit.mockResolvedValue(undefined);
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await userEvent.type(titleField, validSolution.title);
      await userEvent.type(descriptionField, validSolution.description);
      await userEvent.type(tagsField, 'pod-issue{enter}');

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/solution saved successfully/i)).toBeInTheDocument();
      });
    });

    it('should close dialog after successful submission', async () => {
      jest.useFakeTimers();
      mockOnSubmit.mockResolvedValue(undefined);
      
      const { rerender } = render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await act(async () => {
        fireEvent.change(titleField, { target: { value: validSolution.title } });
        fireEvent.change(descriptionField, { target: { value: validSolution.description } });
        await userEvent.type(tagsField, 'pod-issue{enter}');
      });

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled();
      });

      // Fast-forward time to trigger the close
      act(() => {
        jest.advanceTimersByTime(1500);
      });

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
      });

      jest.useRealTimers();
    }, 15000);
  });

  describe('Error Handling', () => {
    const validSolution = {
      title: 'Fix CrashLoopBackOff due to missing ConfigMap',
      description: 'The pod was crashing because the ConfigMap was not created. Create the ConfigMap and restart the deployment.',
      tags: ['pod-issue', 'crashloop'],
    };

    it('should display error message when submission fails', async () => {
      const errorMessage = 'Failed to save solution to knowledge base';
      mockOnSubmit.mockRejectedValue(new Error(errorMessage));
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await act(async () => {
        fireEvent.change(titleField, { target: { value: validSolution.title } });
        fireEvent.change(descriptionField, { target: { value: validSolution.description } });
        await userEvent.type(tagsField, 'pod-issue{enter}');
      });

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      }, { timeout: 5000 });
    }, 15000);

    it('should display default error message when error has no message', async () => {
      mockOnSubmit.mockRejectedValue({});
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await act(async () => {
        fireEvent.change(titleField, { target: { value: validSolution.title } });
        fireEvent.change(descriptionField, { target: { value: validSolution.description } });
        await userEvent.type(tagsField, 'pod-issue{enter}');
      });

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/failed to submit solution/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    }, 15000);

    it('should re-enable form after submission error', async () => {
      mockOnSubmit.mockRejectedValue(new Error('Submission failed'));
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await act(async () => {
        fireEvent.change(titleField, { target: { value: validSolution.title } });
        fireEvent.change(descriptionField, { target: { value: validSolution.description } });
        await userEvent.type(tagsField, 'pod-issue{enter}');
      });

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/submission failed/i)).toBeInTheDocument();
      }, { timeout: 5000 });

      // Check that fields are re-enabled
      expect(titleField).not.toBeDisabled();
      expect(descriptionField).not.toBeDisabled();
      expect(tagsField).not.toBeDisabled();
      expect(submitButton).not.toBeDisabled();
    }, 15000);
  });

  describe('Dialog Close', () => {
    it('should call onClose when cancel button is clicked', () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      fireEvent.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalled();
    });

    it('should call onClose when close icon is clicked', async () => {
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      // Wait for dialog to be fully rendered
      await waitFor(() => {
        expect(screen.getByText('Save Solution to Knowledge Base')).toBeInTheDocument();
      });

      const closeButtons = screen.getAllByRole('button');
      const closeButton = closeButtons.find(btn => btn.querySelector('[data-testid="CloseIcon"]'));
      
      if (closeButton) {
        fireEvent.click(closeButton);
        expect(mockOnClose).toHaveBeenCalled();
      }
    });

    it('should not allow closing during submission', async () => {
      mockOnSubmit.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)));
      render(
        <SolutionSubmitDialog
          open={true}
          onClose={mockOnClose}
          onSubmit={mockOnSubmit}
        />
      );

      // Wait for dialog to be fully rendered
      await waitFor(() => {
        expect(screen.getByText('Save Solution to Knowledge Base')).toBeInTheDocument();
      });

      const titleField = screen.getByLabelText(/title/i);
      const descriptionField = screen.getByLabelText(/description/i);
      const tagsField = screen.getByLabelText(/tags/i);

      await act(async () => {
        fireEvent.change(titleField, { target: { value: 'Valid Title' } });
        fireEvent.change(descriptionField, { target: { value: 'Valid description with enough characters.' } });
        await userEvent.type(tagsField, 'pod-issue{enter}');
      });

      const submitButton = screen.getByRole('button', { name: /save solution/i });
      
      await act(async () => {
        fireEvent.click(submitButton);
      });

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      expect(cancelButton).toBeDisabled();

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled();
      }, { timeout: 5000 });
    }, 15000);
  });
});
