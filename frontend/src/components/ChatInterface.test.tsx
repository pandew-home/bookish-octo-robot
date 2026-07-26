import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatInterface } from './ChatInterface';
import { useCredentialStatus } from '../hooks/useCredentialStatus';

// Mock the useCredentialStatus hook
jest.mock('../hooks/useCredentialStatus');

const mockUseCredentialStatus = useCredentialStatus as jest.MockedFunction<
  typeof useCredentialStatus
>;

// Mock fetch
global.fetch = jest.fn();

describe('ChatInterface', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Default mock for credential status
    mockUseCredentialStatus.mockReturnValue({
      status: {
        present: true,
        expired: false,
        account_id: '123456789012',
      },
      loading: false,
      error: null,
      timeRemaining: 3600,
      refresh: jest.fn(),
    });
  });

  it('should show welcome message when no messages', () => {
    render(
      <ChatInterface 
        isAuthenticated={true} 
        selectedCluster="test-cluster"
      />
    );

    expect(screen.getByText('Welcome to DevOps Chatbot v2')).toBeInTheDocument();
    expect(screen.getByText(/Ask me about your cluster issues/)).toBeInTheDocument();
  });

  it('should show login prompt when not authenticated', () => {
    render(
      <ChatInterface 
        isAuthenticated={false}
      />
    );

    expect(screen.getAllByText(/Please log in with Kion credentials/).length).toBeGreaterThan(0);
  });

  it('should show cluster selection prompt when no cluster selected', () => {
    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster={null}
      />
    );

    expect(screen.getAllByText(/Please select a cluster to start chatting/).length).toBeGreaterThan(0);
  });

  it('should display credential badge when authenticated', () => {
    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    expect(screen.getByText(/Active/)).toBeInTheDocument();
  });

  it('should display selected cluster name', () => {
    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    expect(screen.getByText(/Cluster:/)).toBeInTheDocument();
    expect(screen.getByText('test-cluster')).toBeInTheDocument();
  });

  it('should disable input when not authenticated', () => {
    render(
      <ChatInterface 
        isAuthenticated={false}
      />
    );

    const input = screen.getByPlaceholderText('Log in to ask questions');
    expect(input).toBeDisabled();
  });

  it('should disable input when no cluster selected', () => {
    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster={null}
      />
    );

    const input = screen.getByPlaceholderText('Select a cluster to ask questions');
    expect(input).toBeDisabled();
  });

  it('should enable input when authenticated and cluster selected', () => {
    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    expect(input).not.toBeDisabled();
  });

  it('should send message when form is submitted', async () => {
    const mockResponse = {
      content: 'This is a test response',
      citations: [],
      k8sgpt_findings: [],
      query_type: 'general',
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' }); // Send button has no text, just icon

    fireEvent.change(input, { target: { value: 'What is the status of my pods?' } });
    fireEvent.click(sendButton);

    // Should show user message
    await waitFor(() => {
      expect(screen.getByText('What is the status of my pods?')).toBeInTheDocument();
    });

    // Should show assistant response
    await waitFor(() => {
      expect(screen.getByText('This is a test response')).toBeInTheDocument();
    });
  });

  it('should display loading state while waiting for response', async () => {
    (global.fetch as jest.Mock).mockImplementation(() => 
      new Promise(resolve => setTimeout(() => resolve({
        ok: true,
        json: async () => ({ content: 'Response' }),
      }), 100))
    );

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' });

    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(sendButton);

    // Should show thinking message
    await waitFor(() => {
      expect(screen.getByText('Thinking...')).toBeInTheDocument();
    });
  });

  it('should display error message when API call fails', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'));

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' });

    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });

  it('should display citations when present', async () => {
    const mockResponse = {
      content: 'Response with citations',
      citations: [
        {
          documentId: 'doc1',
          title: 'Solution 1',
          snippet: 'This is a solution snippet',
          relevanceScore: 0.95,
        },
      ],
      k8sgpt_findings: [],
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' });

    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText('Citations:')).toBeInTheDocument();
    });

    expect(screen.getByText('Solution 1')).toBeInTheDocument();
  });

  it('should display Cluster Analyzer findings when present', async () => {
    const mockResponse = {
      content: 'Response with findings',
      citations: [],
      k8sgpt_findings: [
        {
          name: 'failing-pod',
          kind: 'Pod',
          namespace: 'default',
          severity: 'high',
          problem: 'Pod is in CrashLoopBackOff',
        },
      ],
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' });

    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText('Cluster Analyzer Findings:')).toBeInTheDocument();
    });

    expect(screen.getByText('Pod/failing-pod')).toBeInTheDocument();
  });

  it('should display safety notice when present', async () => {
    const mockResponse = {
      content: 'Response with safety notice',
      citations: [],
      k8sgpt_findings: [],
      safety_notice: 'This command will delete resources permanently',
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' });

    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText(/Safety Notice:/)).toBeInTheDocument();
    });

    expect(screen.getByText(/This command will delete resources permanently/)).toBeInTheDocument();
  });

  it('should handle suggested queries', () => {
    const suggestedQueries = [
      'Show me failing pods',
      'What is the cluster health?',
    ];

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
        suggestedQueries={suggestedQueries}
      />
    );

    expect(screen.getByText('Show me failing pods')).toBeInTheDocument();
    expect(screen.getByText('What is the cluster health?')).toBeInTheDocument();
  });

  it('should extract and display commands from message content', async () => {
    const mockResponse = {
      content: 'Run this command:\n```bash\nkubectl get pods\n```',
      citations: [],
      k8sgpt_findings: [],
    };

    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    render(
      <ChatInterface 
        isAuthenticated={true}
        selectedCluster="test-cluster"
      />
    );

    const input = screen.getByPlaceholderText('Ask about your cluster...');
    const sendButton = screen.getByRole('button', { name: '' });

    fireEvent.change(input, { target: { value: 'Test query' } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText('Commands:')).toBeInTheDocument();
    });

    expect(screen.getByText('kubectl get pods')).toBeInTheDocument();
  });
});
