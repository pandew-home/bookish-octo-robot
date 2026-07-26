import React, { useState, useRef, useEffect } from 'react';
import {
  Card,
  CardContent,
  Box,
  TextField,
  Button,
  Paper,
  Typography,
  Chip,
  IconButton,
  Collapse,
  Alert,
  CircularProgress,
  Stack,
  Divider,
  Tooltip,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  Send as SendIcon,
  ContentCopy as CopyIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Person as PersonIcon,
  SmartToy as BotIcon,
  Warning as WarningIcon,
  MoreVert as MoreVertIcon,
  Download as DownloadIcon,
  DeleteSweep as ClearIcon,
} from '@mui/icons-material';
import { CredentialBadge } from './CredentialBadge';
import { useCredentials } from '../hooks/useCredentials';

// Message interfaces
interface Citation {
  documentId: string;
  title: string;
  snippet: string;
  relevanceScore: number;
  usageCount?: number;
  successRate?: number;
}

interface ClusterAnalyzerFinding {
  name: string;
  kind: string;
  namespace: string;
  severity: string;
  problem: string;
}

type ChatErrorType = 'auth_error' | 'cluster_unreachable' | 'rate_limited' | 'timeout' | 'connection_error' | 'rbac_forbidden';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  k8sgptFindings?: ClusterAnalyzerFinding[];
  safetyNotice?: string;
  timestamp: string;
  queryType?: string;
  loading?: boolean;
  cluster?: string;
  errorType?: ChatErrorType;
  backendErrors?: { type: string; message: string; severity: string }[];
}

// Props interface
interface ChatInterfaceProps {
  isAuthenticated: boolean;
  selectedCluster?: string | null;
  onLogin?: () => void;
  suggestedQueries?: string[];
  messages?: ChatMessage[];
  onMessagesChange?: (messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void;
  onExportConversation?: () => Promise<any>;
  onClearConversation?: () => void;
}

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  isAuthenticated,
  selectedCluster,
  onLogin,
  suggestedQueries = [],
  messages: externalMessages,
  onMessagesChange,
  onExportConversation,
  onClearConversation,
}) => {
  const { accountId } = useCredentials();
  const [internalMessages, setInternalMessages] = useState<ChatMessage[]>([]);
  const [currentQuery, setCurrentQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [expandedCitations, setExpandedCitations] = useState<Set<string>>(new Set());
  const [expandedFindings, setExpandedFindings] = useState<Set<string>>(new Set());
  const [menuAnchorEl, setMenuAnchorEl] = useState<null | HTMLElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Use external messages if provided, otherwise use internal state
  const messages = externalMessages || internalMessages;

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current && typeof messagesEndRef.current.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Send message to backend
  const sendMessage = async (query: string) => {
    if (!query.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query.trim(),
      timestamp: new Date().toISOString(),
      cluster: selectedCluster || undefined,
    };

    const loadingMessage: ChatMessage = {
      id: `loading-${Date.now()}`,
      role: 'assistant',
      content: 'Thinking...',
      timestamp: new Date().toISOString(),
      loading: true,
    };

    // Use functional updates throughout — replace loading message by ID so concurrent sends don't clobber each other
    const loadingMessageId = loadingMessage.id;

    if (onMessagesChange) {
      onMessagesChange(prev => [...prev, userMessage, loadingMessage]);
    } else {
      setInternalMessages(prev => [...prev, userMessage, loadingMessage]);
    }
    setCurrentQuery('');
    setIsLoading(true);

    try {
      const sessionId = localStorage.getItem('sessionId');
      const userId = accountId || sessionId || 'anonymous';

      if (!selectedCluster) {
        throw new Error('No cluster selected. Please select a cluster first.');
      }

      const response = await fetch(`${API_BASE_URL}/api/chat/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          query: query.trim(),
          session_id: sessionId,
          user_id: userId,
          cluster_name: selectedCluster
        }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Authentication required. Please log in with Kion credentials.');
        } else if (response.status === 429) {
          const data = await response.json();
          throw new Error(data.detail || 'Rate limit exceeded. Please try again later.');
        } else if (response.status === 400) {
          const data = await response.json();
          throw new Error(data.detail || 'Invalid request. Please check your query.');
        } else {
          throw new Error(`Chat API error: ${response.status}`);
        }
      }

      const data = await response.json();

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.content || data.response,
        citations: data.citations || [],
        k8sgptFindings: data.k8sgpt_findings || [],
        safetyNotice: data.safety_notice,
        timestamp: new Date().toISOString(),
        queryType: data.query_type,
        cluster: selectedCluster || undefined,
        backendErrors: data.errors?.length ? data.errors : undefined,
      };

      // Replace loading message in-place by ID (not by position)
      if (onMessagesChange) {
        onMessagesChange(prev => prev.map(m => m.id === loadingMessageId ? assistantMessage : m));
      } else {
        setInternalMessages(prev => prev.map(m => m.id === loadingMessageId ? assistantMessage : m));
      }
    } catch (error) {
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: error instanceof Error ? error.message : 'Failed to get response. Please try again.',
        timestamp: new Date().toISOString(),
      };

      // Replace loading message in-place by ID
      if (onMessagesChange) {
        onMessagesChange(prev => prev.map(m => m.id === loadingMessageId ? errorMessage : m));
      } else {
        setInternalMessages(prev => prev.map(m => m.id === loadingMessageId ? errorMessage : m));
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isAuthenticated && selectedCluster) {
      sendMessage(currentQuery);
    } else if (!isAuthenticated) {
      onLogin?.();
    }
  };

  // Handle suggested query click
  const handleSuggestedQuery = (query: string) => {
    if (isAuthenticated && selectedCluster) {
      sendMessage(query);
    } else if (!isAuthenticated) {
      setCurrentQuery(query);
      onLogin?.();
    }
  };

  // Handle chat actions menu
  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setMenuAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setMenuAnchorEl(null);
  };

  const handleExport = async () => {
    handleMenuClose();
    if (onExportConversation) {
      const result = await onExportConversation();
      if (result) {
        const md = [
          `# Conversation Export`,
          `**Cluster:** ${result.cluster}`,
          `**Date:** ${new Date(result.timestamp).toLocaleString()}`,
          '',
          `## Problem`,
          result.problem,
          '',
          `## Investigation`,
          result.investigation,
          '',
          `## Root Cause`,
          result.rootCause,
          '',
          `## Solution`,
          result.solution,
          '',
          `## Verification`,
          result.verification,
        ].join('\n');
        const blob = new Blob([md], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conversation-${result.cluster || selectedCluster || 'export'}.md`;
        a.click();
        URL.revokeObjectURL(url);
      }
    }
  };

  const handleClear = () => {
    handleMenuClose();
    setInternalMessages([]);
    if (onClearConversation) {
      onClearConversation();
    }
  };

  // Copy text to clipboard
  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  // Toggle citation expansion
  const toggleCitationExpansion = (messageId: string) => {
    setExpandedCitations(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  // Toggle Cluster Analyzer findings expansion
  const toggleFindingsExpansion = (messageId: string) => {
    setExpandedFindings(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  // Extract kubectl/helm commands from message content
  const extractCommands = (content: string): string[] => {
    const commandRegex = /```(?:bash|shell)?\n?(kubectl|helm|k9s|docker|aws|eksctl)\s+[^\n`]+/g;
    const matches = content.match(commandRegex);
    return matches ? matches.map(match => match.replace(/```(?:bash|shell)?\n?/, '').trim()) : [];
  };

  // Format message content with command highlighting
  const formatMessageContent = (content: string, messageId: string) => {
    const commands = extractCommands(content);
    
    return (
      <Box>
        <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', mb: commands.length > 0 ? 2 : 0 }}>
          {content}
        </Typography>
        
        {/* Command buttons */}
        {commands.length > 0 && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              Commands:
            </Typography>
            <Stack spacing={1}>
              {commands.map((command, index) => (
                <Paper 
                  key={index} 
                  sx={{ 
                    p: 1, 
                    bgcolor: 'background.default',
                    border: '1px solid',
                    borderColor: 'divider',
                    fontFamily: 'monospace',
                    fontSize: '0.875rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                    {command}
                  </Typography>
                  <Tooltip title="Copy command">
                    <IconButton 
                      size="small" 
                      onClick={() => copyToClipboard(command)}
                    >
                      <CopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Paper>
              ))}
            </Stack>
          </Box>
        )}
      </Box>
    );
  };

  return (
    <>
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 0 }}>
          {/* Credential Status Header */}
          {isAuthenticated && (
            <Box sx={{ 
              p: 1.5, 
              display: 'flex', 
              justifyContent: 'space-between',
              alignItems: 'center',
              borderBottom: '1px solid',
              borderColor: 'divider',
              bgcolor: 'background.default'
            }}>
              {selectedCluster && (
                <Typography variant="body2" color="text.secondary">
                  Cluster: <strong>{selectedCluster}</strong>
                </Typography>
              )}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <CredentialBadge />
                {(onExportConversation || onClearConversation) && messages.length > 0 && (
                  <>
                    <IconButton size="small" onClick={handleMenuOpen}>
                      <MoreVertIcon fontSize="small" />
                    </IconButton>
                    <Menu
                      anchorEl={menuAnchorEl}
                      open={Boolean(menuAnchorEl)}
                      onClose={handleMenuClose}
                    >
                      {onExportConversation && (
                        <MenuItem onClick={handleExport}>
                          <ListItemIcon><DownloadIcon fontSize="small" /></ListItemIcon>
                          <ListItemText>Export Conversation</ListItemText>
                        </MenuItem>
                      )}
                      {onClearConversation && (
                        <MenuItem onClick={handleClear}>
                          <ListItemIcon><ClearIcon fontSize="small" /></ListItemIcon>
                          <ListItemText>Clear Conversation</ListItemText>
                        </MenuItem>
                      )}
                    </Menu>
                  </>
                )}
              </Box>
            </Box>
          )}

        {/* Messages Area */}
        <Box 
          sx={{ 
            maxHeight: '60vh', 
            overflowY: 'auto', 
            p: 2,
            minHeight: '200px',
          }}
        >
          {messages.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Welcome to DevOps Chatbot v2
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {!isAuthenticated 
                  ? 'Please log in with Kion credentials to start chatting.'
                  : !selectedCluster
                  ? 'Please select a cluster to start chatting.'
                  : 'Ask me about your cluster issues, deployments, or troubleshooting.'
                }
              </Typography>
            </Box>
          ) : (
            <Stack spacing={2}>
              {messages.map((message) => (
                <Paper
                  key={message.id}
                  elevation={1}
                  sx={{
                    p: 2,
                    bgcolor: message.role === 'user' ? 'primary.dark' : 'background.paper',
                    alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '85%',
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  {/* Message Header */}
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    {message.role === 'user' ? (
                      <PersonIcon sx={{ mr: 1, fontSize: '1.2rem' }} />
                    ) : (
                      <BotIcon sx={{ mr: 1, fontSize: '1.2rem' }} />
                    )}
                    <Typography variant="caption" color="text.secondary">
                      {message.role === 'user' ? 'You' : 'Assistant'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                      {new Date(message.timestamp).toLocaleTimeString()}
                    </Typography>
                  </Box>

                  {/* Message Content */}
                  {message.loading ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <CircularProgress size={16} />
                      <Typography variant="body2" color="text.secondary">
                        {message.content}
                      </Typography>
                    </Box>
                  ) : (
                    formatMessageContent(message.content, message.id)
                  )}

                  {/* Turn-scoped hard error (thread continues; composer stays usable) */}
                  {message.errorType && (
                    <Alert
                      severity={message.errorType === 'auth_error' ? 'error' : 'warning'}
                      icon={<WarningIcon />}
                      sx={{
                        mt: 2,
                        bgcolor: 'rgba(255, 152, 0, 0.15)',
                        borderColor: '#ff9800',
                        border: '1px solid',
                        '& .MuiAlert-icon': {
                          color: '#ffb74d'
                        }
                      }}
                    >
                      <Typography variant="body2">
                        {message.errorType === 'auth_error' && 'Authentication failed. Please check your credentials and try again.'}
                        {message.errorType === 'cluster_unreachable' && 'Cluster is not responding. Please verify the cluster is accessible, then continue this chat.'}
                        {message.errorType === 'rate_limited' && 'Rate limit exceeded. Wait a moment, then send another message.'}
                        {message.errorType === 'timeout' && 'Request timed out. Try a narrower question—your history is intact.'}
                        {message.errorType === 'connection_error' && 'Connection failed. Check your network, then continue this chat.'}
                        {message.errorType === 'rbac_forbidden' && 'Permission denied for that action. Rephrase or ask for a read-only diagnosis.'}
                      </Typography>
                    </Alert>
                  )}

                  {/* Soft agent warnings on HTTP 200 turns */}
                  {message.backendErrors && message.backendErrors.length > 0 && (
                    <Alert severity="warning" sx={{ mt: 2 }}>
                      <Typography variant="caption" display="block" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                        Notes from this turn ({message.backendErrors.length}):
                      </Typography>
                      {message.backendErrors.map((err, idx) => (
                        <Typography key={idx} variant="caption" display="block">
                          {err.message}
                        </Typography>
                      ))}
                    </Alert>
                  )}

                  {/* Safety Notice */}
                  {message.safetyNotice && (
                    <Alert severity="warning" icon={<WarningIcon />} sx={{ mt: 2 }}>
                      <Typography variant="body2">
                        <strong>Safety Notice:</strong> {message.safetyNotice}
                      </Typography>
                    </Alert>
                  )}

                  {/* Cluster Analyzer Findings */}
                  {message.k8sgptFindings && message.k8sgptFindings.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                          Cluster Analyzer Findings:
                        </Typography>
                        <Button
                          size="small"
                          onClick={() => toggleFindingsExpansion(message.id)}
                          endIcon={expandedFindings.has(message.id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                          sx={{ ml: 1, minWidth: 'auto', p: 0.5 }}
                        >
                          {expandedFindings.has(message.id) ? 'Hide' : 'Show'} Details
                        </Button>
                      </Box>
                      
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                        {message.k8sgptFindings.map((finding, index) => (
                          <Chip
                            key={index}
                            label={`${finding.kind}/${finding.name}`}
                            size="small"
                            variant="outlined"
                            color={finding.severity === 'high' ? 'error' : finding.severity === 'medium' ? 'warning' : 'info'}
                          />
                        ))}
                      </Stack>

                      <Collapse in={expandedFindings.has(message.id)}>
                        <Stack spacing={1}>
                          {message.k8sgptFindings.map((finding, index) => (
                            <Paper key={index} sx={{ p: 1, bgcolor: 'background.default' }}>
                              <Typography variant="caption" color="text.secondary" display="block">
                                {finding.kind}/{finding.name} ({finding.namespace}) - {finding.severity}
                              </Typography>
                              <Typography variant="body2" sx={{ fontSize: '0.8rem' }}>
                                {finding.problem}
                              </Typography>
                            </Paper>
                          ))}
                        </Stack>
                      </Collapse>
                    </Box>
                  )}

                  {/* Citations */}
                  {message.citations && message.citations.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Typography variant="caption" color="text.secondary">
                          Citations:
                        </Typography>
                        <Button
                          size="small"
                          onClick={() => toggleCitationExpansion(message.id)}
                          endIcon={expandedCitations.has(message.id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                          sx={{ ml: 1, minWidth: 'auto', p: 0.5 }}
                        >
                          {expandedCitations.has(message.id) ? 'Hide' : 'Show'} Details
                        </Button>
                      </Box>
                      
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
                        {message.citations.map((citation, index) => (
                          <Chip
                            key={index}
                            label={citation.title}
                            size="small"
                            variant="outlined"
                            color="primary"
                          />
                        ))}
                      </Stack>

                      <Collapse in={expandedCitations.has(message.id)}>
                        <Stack spacing={1}>
                          {message.citations.map((citation, index) => (
                            <Paper key={index} sx={{ p: 1, bgcolor: 'background.default' }}>
                              <Typography variant="caption" color="text.secondary" display="block">
                                {citation.title} (Relevance: {Math.round(citation.relevanceScore * 100)}%)
                              </Typography>
                              <Typography variant="body2" sx={{ fontSize: '0.8rem' }}>
                                {citation.snippet}
                              </Typography>
                              {citation.usageCount !== undefined && (
                                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                                  Used {citation.usageCount} times
                                  {citation.successRate !== undefined && ` • ${Math.round(citation.successRate * 100)}% success rate`}
                                </Typography>
                              )}
                            </Paper>
                          ))}
                        </Stack>
                      </Collapse>
                    </Box>
                  )}

                </Paper>
              ))}
            </Stack>
          )}
          <div ref={messagesEndRef} />
        </Box>

        <Divider />

        {/* Suggested Queries */}
        {suggestedQueries.length > 0 && (
          <Box sx={{ p: 2, pb: 1 }}>
            <Typography variant="caption" color="text.secondary" gutterBottom display="block">
              Suggested queries:
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {suggestedQueries.map((query, index) => (
                <Chip
                  key={index}
                  label={query}
                  size="small"
                  variant="outlined"
                  onClick={() => handleSuggestedQuery(query)}
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Stack>
          </Box>
        )}

        {/* Input Area */}
        <Box sx={{ p: 2, pt: 1 }}>
          {!isAuthenticated ? (
            <Alert severity="info" sx={{ mb: 2 }}>
              Please log in with Kion credentials to start chatting.
            </Alert>
          ) : !selectedCluster ? (
            <Alert severity="info" sx={{ mb: 2 }}>
              Please select a cluster to start chatting.
            </Alert>
          ) : null}
          
          <form onSubmit={handleSubmit}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
              <TextField
                fullWidth
                variant="outlined"
                placeholder={
                  !isAuthenticated 
                    ? "Log in to ask questions" 
                    : !selectedCluster
                    ? "Select a cluster to ask questions"
                    : "Ask about your cluster..."
                }
                value={currentQuery}
                onChange={(e) => setCurrentQuery(e.target.value)}
                disabled={isLoading || !isAuthenticated || !selectedCluster}
                multiline
                maxRows={4}
                sx={{ flex: 1 }}
              />
              <Button
                type="submit"
                variant="contained"
                disabled={!currentQuery.trim() || isLoading || !isAuthenticated || !selectedCluster}
                sx={{ minWidth: 'auto', px: 2, py: 1.5 }}
              >
                {isLoading ? (
                  <CircularProgress size={20} color="inherit" />
                ) : (
                  <SendIcon />
                )}
              </Button>
            </Box>
          </form>
        </Box>
      </CardContent>
    </Card>

  </>
  );
};
