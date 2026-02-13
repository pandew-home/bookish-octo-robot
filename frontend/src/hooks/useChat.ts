import { useState, useCallback, useEffect } from 'react';
import { ChatMessage, ConversationExport, ChatErrorType } from '../types/chat';
import apiClient from '../services/api';

export interface UseChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (query: string) => Promise<void>;
  loadHistory: () => Promise<void>;
  exportConversation: () => Promise<ConversationExport | null>;
  clearMessages: () => void;
}

/**
 * React hook to manage chat message submission, history, and export
 * 
 * Features:
 * - Send messages to chat API
 * - Load conversation history (last 5 messages per cluster)
 * - Export conversation summary
 * - Handle conversation state per cluster
 * - Manage loading and error states
 * 
 * Requirements: 7.1, 10.1, 10.2
 */
export const useChat = (
  selectedCluster: string | null,
  isAuthenticated: boolean
): UseChatState => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Send a message to the chat API
   * Handles query classification, enrichment, RAG retrieval, and LLM response
   */
  const sendMessage = useCallback(async (query: string) => {
    if (!query.trim() || isLoading || !isAuthenticated || !selectedCluster) {
      return;
    }

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query.trim(),
      timestamp: new Date().toISOString(),
      cluster: selectedCluster,
    };

    const loadingMessage: ChatMessage = {
      id: `loading-${Date.now()}`,
      role: 'assistant',
      content: 'Thinking...',
      timestamp: new Date().toISOString(),
      loading: true,
    };

    // Add user message and loading indicator
    setMessages(prev => [...prev, userMessage, loadingMessage]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await apiClient.post('/chat', {
        query: query.trim(),
      });

      const data = response.data;

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.content || data.response,
        citations: data.citations || [],
        k8sgptFindings: data.k8sgpt_findings || [],
        safetyNotice: data.safety_notice,
        timestamp: new Date().toISOString(),
        queryType: data.query_type,
        cluster: selectedCluster,
      };

      // Replace loading message with actual response
      setMessages(prev => prev.slice(0, -1).concat(assistantMessage));
    } catch (err: any) {
      let errorMessage = 'Failed to get response. Please try again.';
      let errorType: ChatErrorType | undefined;

      if (err.response?.status === 401) {
        errorMessage = 'Authentication required. Please log in again.';
        errorType = 'auth_error';
      } else if (err.response?.status === 403) {
        errorMessage = err.response.data?.detail || 'Access denied. Check your RBAC permissions.';
        errorType = 'rbac_forbidden';
      } else if (err.response?.status === 503) {
        errorMessage = 'Cluster not responding. Please verify the cluster is accessible.';
        errorType = 'cluster_unreachable';
      } else if (err.response?.status === 429) {
        errorMessage = err.response.data?.detail || 'Rate limit exceeded. Please try again later.';
        errorType = 'rate_limited';
      } else if (err.response?.status === 400) {
        errorMessage = err.response.data?.detail || 'Invalid request. Please check your query.';
      } else if (err.message) {
        errorMessage = err.message;
      }

      // Check for error_type in response metadata
      if (err.response?.data?.metadata?.error_type) {
        errorType = err.response.data.metadata.error_type as ChatErrorType;
      }

      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date().toISOString(),
        errorType,
      };

      // Replace loading message with error
      setMessages(prev => prev.slice(0, -1).concat(errorMsg));
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, isAuthenticated, selectedCluster]);

  /**
   * Load conversation history for the selected cluster
   * Retrieves last 5 messages from backend
   */
  const loadHistory = useCallback(async () => {
    if (!isAuthenticated || !selectedCluster) {
      return;
    }

    try {
      const response = await apiClient.get('/chat/history', {
        params: {
          cluster: selectedCluster,
          limit: 5,
        },
      });

      const history: ChatMessage[] = response.data.messages || [];
      setMessages(history);
    } catch (err: any) {
      console.error('Failed to load conversation history:', err);
      // Don't set error state for history load failures - just log it
      // User can still send new messages
    }
  }, [isAuthenticated, selectedCluster]);

  /**
   * Export conversation as structured summary
   * Returns markdown format with problem, investigation, root cause, solution, verification
   */
  const exportConversation = useCallback(async (): Promise<ConversationExport | null> => {
    if (!isAuthenticated || !selectedCluster || messages.length === 0) {
      return null;
    }

    try {
      const response = await apiClient.post('/chat/export', {
        cluster: selectedCluster,
      });

      return response.data as ConversationExport;
    } catch (err: any) {
      console.error('Failed to export conversation:', err);
      setError('Failed to export conversation');
      return null;
    }
  }, [isAuthenticated, selectedCluster, messages.length]);

  /**
   * Clear all messages
   */
  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  /**
   * Load history when cluster changes
   */
  useEffect(() => {
    if (selectedCluster && isAuthenticated) {
      loadHistory();
    } else {
      // Clear messages when cluster is deselected or user logs out
      setMessages([]);
    }
  }, [selectedCluster, isAuthenticated, loadHistory]);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    loadHistory,
    exportConversation,
    clearMessages,
  };
};
