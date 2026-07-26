import React, { useState, useCallback, useEffect } from 'react';
import { ChatMessage, ConversationExport, ChatErrorType } from '../types/chat';
import apiClient from '../services/api';
import {
  formatApiError,
  normalizeBackendErrors,
  toApiError,
  toChatErrorType,
} from '../utils/apiError';

export interface UseChatState {
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  isLoading: boolean;
  error: string | null;
  sendMessage: (query: string) => Promise<void>;
  loadHistory: () => Promise<void>;
  exportConversation: () => Promise<ConversationExport | null>;
  clearMessages: () => void;
  clearError: () => void;
}

/**
 * Chat hook with turn-scoped errors: failures never wipe the thread and never
 * permanently lock the composer (except auth/cluster prerequisites).
 */
export const useChat = (
  selectedCluster: string | null,
  isAuthenticated: boolean
): UseChatState => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const sendMessage = useCallback(
    async (query: string) => {
      // Only gate on loading + session prerequisites — sticky error must not block retry.
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

      const loadingMessageId = loadingMessage.id;
      // Keep full thread; append this turn only.
      setMessages((prev) => [...prev, userMessage, loadingMessage]);
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.post('/chat/query', {
          query: query.trim(),
          session_id: localStorage.getItem('sessionId') || '',
          user_id: localStorage.getItem('userId') || 'anonymous',
          cluster_name: selectedCluster,
        });

        const data = response.data;
        const backendErrors = normalizeBackendErrors(data.errors);
        let content = data.content || data.response || '';
        if (backendErrors?.length && content) {
          // Soft agent warnings: keep answer usable.
        }

        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content:
            content ||
            'I could not produce a full answer. Try rephrasing—your chat history is intact.',
          citations: data.citations || [],
          k8sgptFindings: data.k8sgpt_findings || [],
          safetyNotice: data.safety_notice,
          timestamp: new Date().toISOString(),
          queryType: data.query_type,
          cluster: selectedCluster,
          backendErrors,
        };

        setMessages((prev) =>
          prev.map((m) => (m.id === loadingMessageId ? assistantMessage : m))
        );
      } catch (err: unknown) {
        const apiErr = toApiError(err);
        const errorType: ChatErrorType | undefined = toChatErrorType(apiErr.code);
        const display = formatApiError(apiErr);
        const continuityHint = apiErr.recoverable
          ? ' You can correct your question and continue this chat.'
          : '';

        const errorMsg: ChatMessage = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: `${apiErr.message}${continuityHint}`,
          timestamp: new Date().toISOString(),
          errorType,
          cluster: selectedCluster || undefined,
        };

        // Replace only the loading bubble; keep the user message and full history.
        setMessages((prev) =>
          prev.map((m) => (m.id === loadingMessageId ? errorMsg : m))
        );
        setError(display);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, isAuthenticated, selectedCluster]
  );

  const loadHistory = useCallback(async () => {
    if (!isAuthenticated || !selectedCluster) {
      return;
    }

    try {
      const response = await apiClient.get('/chat/history', {
        params: {
          user_id: localStorage.getItem('userId') || 'anonymous',
          cluster_name: selectedCluster,
          limit: 5,
        },
      });

      const history: ChatMessage[] = response.data.messages || [];
      setMessages(history);
    } catch (err: unknown) {
      // History failure must not block new messages.
      console.error('Failed to load conversation history:', toApiError(err));
    }
  }, [isAuthenticated, selectedCluster]);

  const exportConversation = useCallback(async (): Promise<ConversationExport | null> => {
    if (!isAuthenticated || !selectedCluster || messages.length === 0) {
      return null;
    }

    try {
      const response = await apiClient.post('/chat/export', {
        user_id: localStorage.getItem('userId') || 'anonymous',
        cluster_name: selectedCluster,
      });

      return response.data as ConversationExport;
    } catch (err: unknown) {
      const apiErr = toApiError(err);
      console.error('Failed to export conversation:', apiErr);
      setError(formatApiError(apiErr));
      return null;
    }
  }, [isAuthenticated, selectedCluster, messages.length]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  useEffect(() => {
    if (selectedCluster && isAuthenticated) {
      loadHistory();
    } else {
      setMessages([]);
    }
  }, [selectedCluster, isAuthenticated, loadHistory]);

  return {
    messages,
    setMessages,
    isLoading,
    error,
    sendMessage,
    loadHistory,
    exportConversation,
    clearMessages,
    clearError,
  };
};
