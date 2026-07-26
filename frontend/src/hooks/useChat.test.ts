import { renderHook, act, waitFor } from '@testing-library/react';
import { useChat, UseChatState } from './useChat';
import apiClient from '../services/api';
import { ChatMessage, ConversationExport } from '../types/chat';

// Mock the API client
jest.mock('../services/api');

const mockApiClient = apiClient as jest.Mocked<typeof apiClient>;

describe('useChat', () => {
  const selectedCluster = 'dev-cluster-1';
  const isAuthenticated = true;
  type UseChatProps = { cluster: string | null; auth: boolean };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('sendMessage', () => {
    it('should send a message and receive a response', async () => {
      const mockResponse = {
        data: {
          content: 'This is a test response',
          citations: [
            {
              documentId: 'doc-1',
              title: 'Test Document',
              snippet: 'Test snippet',
              relevanceScore: 0.95,
            },
          ],
          k8sgpt_findings: [
            {
              name: 'pod-1',
              kind: 'Pod',
              namespace: 'default',
              severity: 'high',
              problem: 'Pod is crashing',
            },
          ],
          safety_notice: 'This operation is destructive',
          query_type: 'pod_issue',
        },
      };

      mockApiClient.post.mockResolvedValue(mockResponse);

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('Why is my pod crashing?');
      });

      expect(mockApiClient.post).toHaveBeenCalledWith('/chat/query', {
        query: 'Why is my pod crashing?',
        session_id: expect.any(String),
        user_id: expect.any(String),
        cluster_name: selectedCluster,
      });

      // Should have user message and assistant response
      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[0].role).toBe('user');
      expect(result.current.messages[0].content).toBe('Why is my pod crashing?');
      expect(result.current.messages[1].role).toBe('assistant');
      expect(result.current.messages[1].content).toBe('This is a test response');
      expect(result.current.messages[1].citations).toHaveLength(1);
      expect(result.current.messages[1].k8sgptFindings).toHaveLength(1);
      expect(result.current.messages[1].safetyNotice).toBe('This operation is destructive');
      expect(result.current.messages[1].queryType).toBe('pod_issue');
    });

    it('should handle empty messages', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('');
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(result.current.messages).toHaveLength(0);
    });

    it('should handle whitespace-only messages', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('   ');
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(result.current.messages).toHaveLength(0);
    });

    it('should not send message when not authenticated', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, false));

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(result.current.messages).toHaveLength(0);
    });

    it('should not send message when no cluster is selected', async () => {
      const { result } = renderHook(() => useChat(null, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(result.current.messages).toHaveLength(0);
    });

    it('should handle API errors gracefully without wiping the thread', async () => {
      mockApiClient.post.mockRejectedValue({
        response: {
          status: 400,
          data: {
            detail: 'Invalid query format',
          },
        },
      });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      // User + error assistant; history preserved for correction
      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[0].role).toBe('user');
      expect(result.current.messages[1].role).toBe('assistant');
      expect(result.current.messages[1].content).toContain('Invalid query format');
      expect(result.current.messages[1].content).toContain('continue');
      expect(result.current.error).toContain('Invalid query format');
      expect(result.current.isLoading).toBe(false);
    });

    it('should allow another send after a recoverable error', async () => {
      mockApiClient.post
        .mockRejectedValueOnce({
          response: { status: 500, data: { detail: 'Server glitch' }, headers: {} },
        })
        .mockResolvedValueOnce({
          data: { response: 'Recovered answer', errors: [] },
        });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('First');
      });
      expect(result.current.isLoading).toBe(false);

      await act(async () => {
        await result.current.sendMessage('Second');
      });

      expect(result.current.messages.length).toBeGreaterThanOrEqual(3);
      const last = result.current.messages[result.current.messages.length - 1];
      expect(last.content).toContain('Recovered answer');
    });

    it('should handle 401 authentication errors', async () => {
      mockApiClient.post.mockRejectedValue({
        response: {
          status: 401,
          data: {
            detail: 'Credentials expired',
          },
        },
      });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      // 401 is not recoverable — no "continue this chat" soft prompt required
      expect(result.current.messages[1].content).toContain('Credentials expired');
      expect(result.current.messages[1].errorType).toBe('auth_error');
    });

    it('should handle 429 rate limit errors', async () => {
      mockApiClient.post.mockRejectedValue({
        response: {
          status: 429,
          data: {
            detail: 'Rate limit exceeded. Try again in 30 seconds.',
          },
        },
      });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      expect(result.current.messages[1].content).toContain(
        'Rate limit exceeded. Try again in 30 seconds.'
      );
    });

    it('should show loading state during message send', async () => {
      mockApiClient.post.mockImplementation(() =>
        new Promise(resolve =>
          setTimeout(
            () =>
              resolve({
                data: {
                  content: 'Response',
                },
              }),
            100
          )
        )
      );

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      act(() => {
        result.current.sendMessage('Test message');
      });

      // Should show loading message
      await waitFor(() => {
        expect(result.current.messages).toHaveLength(2);
      });

      expect(result.current.messages[1].loading).toBe(true);
      expect(result.current.isLoading).toBe(true);

      // Wait for response
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.messages[1].loading).toBeUndefined();
    });

    it('should trim whitespace from messages', async () => {
      mockApiClient.post.mockResolvedValue({
        data: {
          content: 'Response',
        },
      });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.sendMessage('  Test message  ');
      });

      expect(mockApiClient.post).toHaveBeenCalledWith('/chat/query', {
        query: 'Test message',
        session_id: expect.any(String),
        user_id: expect.any(String),
        cluster_name: selectedCluster,
      });
    });
  });

  describe('loadHistory', () => {
    it('should load conversation history', async () => {
      const mockHistory: ChatMessage[] = [
        {
          id: '1',
          role: 'user',
          content: 'Previous question',
          timestamp: '2024-01-01T00:00:00Z',
          cluster: selectedCluster,
        },
        {
          id: '2',
          role: 'assistant',
          content: 'Previous answer',
          timestamp: '2024-01-01T00:00:01Z',
          cluster: selectedCluster,
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: {
          messages: mockHistory,
        },
      });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      await act(async () => {
        await result.current.loadHistory();
      });

      expect(mockApiClient.get).toHaveBeenCalledWith('/chat/history', {
        params: {
          user_id: expect.any(String),
          cluster_name: selectedCluster,
          limit: 5,
        },
      });

      expect(result.current.messages).toEqual(mockHistory);
    });

    it('should not load history when not authenticated', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, false));

      await act(async () => {
        await result.current.loadHistory();
      });

      expect(mockApiClient.get).not.toHaveBeenCalled();
    });

    it('should not load history when no cluster is selected', async () => {
      const { result } = renderHook(() => useChat(null, isAuthenticated));

      await act(async () => {
        await result.current.loadHistory();
      });

      expect(mockApiClient.get).not.toHaveBeenCalled();
    });

    it('should handle history load failures gracefully', async () => {
      mockApiClient.get.mockRejectedValue(new Error('Failed to load history'));

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      // Should not throw error
      await act(async () => {
        await result.current.loadHistory();
      });

      // Messages should remain empty
      expect(result.current.messages).toHaveLength(0);
    });
  });

  describe('exportConversation', () => {
    it('should export conversation summary', async () => {
      const mockExport: ConversationExport = {
        problem: 'Pod crashing',
        investigation: 'Checked logs and events',
        rootCause: 'Out of memory',
        solution: 'Increased memory limits',
        verification: 'Pod is now running',
        timestamp: '2024-01-01T00:00:00Z',
        cluster: selectedCluster,
      };

      mockApiClient.post.mockResolvedValue({
        data: mockExport,
      });

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      // Add some messages first
      result.current.messages.push({
        id: '1',
        role: 'user',
        content: 'Test',
        timestamp: '2024-01-01T00:00:00Z',
      });

      let exportResult: ConversationExport | null = null;

      await act(async () => {
        exportResult = await result.current.exportConversation();
      });

      expect(mockApiClient.post).toHaveBeenCalledWith('/chat/export', {
        user_id: expect.any(String),
        cluster_name: selectedCluster,
      });

      expect(exportResult).toEqual(mockExport);
    });

    it('should return null when not authenticated', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, false));

      let exportResult: ConversationExport | null = null;

      await act(async () => {
        exportResult = await result.current.exportConversation();
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(exportResult).toBeNull();
    });

    it('should return null when no cluster is selected', async () => {
      const { result } = renderHook(() => useChat(null, isAuthenticated));

      let exportResult: ConversationExport | null = null;

      await act(async () => {
        exportResult = await result.current.exportConversation();
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(exportResult).toBeNull();
    });

    it('should return null when no messages exist', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      let exportResult: ConversationExport | null = null;

      await act(async () => {
        exportResult = await result.current.exportConversation();
      });

      expect(mockApiClient.post).not.toHaveBeenCalled();
      expect(exportResult).toBeNull();
    });

    it('should handle export failures gracefully', async () => {
      mockApiClient.post.mockRejectedValue(new Error('Export failed'));

      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      // Add some messages
      result.current.messages.push({
        id: '1',
        role: 'user',
        content: 'Test',
        timestamp: '2024-01-01T00:00:00Z',
      });

      let exportResult: ConversationExport | null = null;

      await act(async () => {
        exportResult = await result.current.exportConversation();
      });

      expect(exportResult).toBeNull();
      expect(result.current.error).toBe('Failed to export conversation');
    });
  });

  describe('clearMessages', () => {
    it('should clear all messages', async () => {
      const { result } = renderHook(() => useChat(selectedCluster, isAuthenticated));

      // Add some messages
      mockApiClient.post.mockResolvedValue({
        data: {
          content: 'Response',
        },
      });

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      expect(result.current.messages).toHaveLength(2);

      // Clear messages
      act(() => {
        result.current.clearMessages();
      });

      expect(result.current.messages).toHaveLength(0);
      expect(result.current.error).toBeNull();
    });
  });

  describe('cluster change effects', () => {
    it('should load history when cluster changes', async () => {
      const mockHistory: ChatMessage[] = [
        {
          id: '1',
          role: 'user',
          content: 'Previous question',
          timestamp: '2024-01-01T00:00:00Z',
          cluster: 'new-cluster',
        },
      ];

      mockApiClient.get.mockResolvedValue({
        data: {
          messages: mockHistory,
        },
      });

      const { rerender } = renderHook(
        ({ cluster, auth }) => useChat(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      // Change cluster
      rerender({ cluster: 'new-cluster', auth: isAuthenticated });

      await waitFor(() => {
        expect(mockApiClient.get).toHaveBeenCalledWith('/chat/history', {
          params: {
            user_id: expect.any(String),
            cluster_name: 'new-cluster',
            limit: 5,
          },
        });
      });
    });

    it('should clear messages when cluster is deselected', async () => {
      mockApiClient.get.mockResolvedValue({
        data: {
          messages: [
            {
              id: '1',
              role: 'user',
              content: 'Test',
              timestamp: '2024-01-01T00:00:00Z',
            },
          ],
        },
      });

      const { result, rerender } = renderHook<UseChatState, UseChatProps>(
        ({ cluster, auth }) => useChat(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(1);
      });

      // Deselect cluster
      rerender({ cluster: null, auth: isAuthenticated });

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(0);
      });
    });

    it('should clear messages when authentication is lost', async () => {
      mockApiClient.get.mockResolvedValue({
        data: {
          messages: [
            {
              id: '1',
              role: 'user',
              content: 'Test',
              timestamp: '2024-01-01T00:00:00Z',
            },
          ],
        },
      });

      const { result, rerender } = renderHook(
        ({ cluster, auth }) => useChat(cluster, auth),
        {
          initialProps: {
            cluster: selectedCluster,
            auth: isAuthenticated,
          },
        }
      );

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(1);
      });

      // Lose authentication
      rerender({ cluster: selectedCluster, auth: false });

      await waitFor(() => {
        expect(result.current.messages).toHaveLength(0);
      });
    });
  });
});
