/**
 * Normalize API failures into a stable, user-displayable shape.
 * Supports the backend error envelope plus legacy FastAPI `detail` forms.
 */

export type ErrorCode =
  | 'auth_required'
  | 'rbac_forbidden'
  | 'cluster_unreachable'
  | 'rate_limited'
  | 'validation_error'
  | 'timeout'
  | 'connection_error'
  | 'internal_error'
  | 'unknown';

export interface ApiError {
  code: ErrorCode | string;
  message: string;
  status?: number;
  requestId?: string;
  details?: unknown;
  recoverable: boolean;
}

export class ApiClientError extends Error {
  readonly apiError: ApiError;

  constructor(apiError: ApiError) {
    super(apiError.message);
    this.name = 'ApiClientError';
    this.apiError = apiError;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : null;
}

function formatValidationDetail(detail: unknown): string {
  if (!Array.isArray(detail)) {
    return typeof detail === 'string' ? detail : 'Invalid request. Check your input.';
  }
  const parts = detail.slice(0, 8).map((item) => {
    const rec = asRecord(item);
    if (!rec) return String(item);
    const loc = Array.isArray(rec.loc)
      ? rec.loc.filter((x) => x !== 'body').join('.')
      : '';
    const msg = typeof rec.msg === 'string' ? rec.msg : 'invalid';
    return loc ? `${loc}: ${msg}` : msg;
  });
  return parts.length
    ? `Invalid request. ${parts.join('; ')}`
    : 'Invalid request. Check your input.';
}

function codeFromStatus(status?: number): ErrorCode {
  if (status === 401) return 'auth_required';
  if (status === 403) return 'rbac_forbidden';
  if (status === 429) return 'rate_limited';
  if (status === 503) return 'cluster_unreachable';
  if (status === 422 || status === 400) return 'validation_error';
  if (status && status >= 500) return 'internal_error';
  return 'unknown';
}

/**
 * Convert axios/fetch/unknown errors into ApiError.
 */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiClientError) {
    return err.apiError;
  }

  const anyErr = err as {
    message?: string;
    code?: string;
    response?: {
      status?: number;
      data?: unknown;
      headers?: Record<string, string>;
    };
    config?: { headers?: Record<string, string> };
  };

  // Network / timeout (no response)
  if (anyErr?.code === 'ECONNABORTED' || /timeout/i.test(anyErr?.message || '')) {
    return {
      code: 'timeout',
      message:
        'Request timed out. Your earlier messages are still here—try a narrower question.',
      recoverable: true,
    };
  }
  if (anyErr?.message === 'Network Error' || (anyErr && !anyErr.response && anyErr.message)) {
    if (!anyErr.response) {
      return {
        code: 'connection_error',
        message:
          'Connection failed. Check your network, then continue this chat when ready.',
        recoverable: true,
      };
    }
  }

  const status = anyErr?.response?.status;
  const data = anyErr?.response?.data;
  const dataRec = asRecord(data);
  const headers = anyErr?.response?.headers || {};
  const requestId =
    (typeof headers['x-request-id'] === 'string' && headers['x-request-id']) ||
    (typeof headers['X-Request-Id'] === 'string' && headers['X-Request-Id']) ||
    undefined;

  // Standard envelope: { error: { code, message, ... }, detail? }
  const nested = dataRec && asRecord(dataRec.error);
  if (nested && typeof nested.message === 'string') {
    const code = typeof nested.code === 'string' ? nested.code : codeFromStatus(status);
    return {
      code,
      message: nested.message,
      status,
      requestId:
        (typeof nested.request_id === 'string' && nested.request_id) || requestId,
      details: nested.details,
      recoverable:
        typeof nested.recoverable === 'boolean'
          ? nested.recoverable
          : status !== 401,
    };
  }

  // Legacy detail string or validation array
  if (dataRec && 'detail' in dataRec) {
    const detail = dataRec.detail;
    if (typeof detail === 'string') {
      return {
        code: codeFromStatus(status),
        message: detail,
        status,
        requestId,
        recoverable: status !== 401,
      };
    }
    if (Array.isArray(detail)) {
      return {
        code: 'validation_error',
        message: formatValidationDetail(detail),
        status,
        requestId,
        details: detail,
        recoverable: true,
      };
    }
    // detail may itself be the envelope (from api_error)
    const detailRec = asRecord(detail);
    const detailErr = detailRec && asRecord(detailRec.error);
    if (detailErr && typeof detailErr.message === 'string') {
      return {
        code: typeof detailErr.code === 'string' ? detailErr.code : codeFromStatus(status),
        message: detailErr.message,
        status,
        requestId:
          (typeof detailErr.request_id === 'string' && detailErr.request_id) ||
          requestId,
        recoverable:
          typeof detailErr.recoverable === 'boolean'
            ? detailErr.recoverable
            : status !== 401,
      };
    }
  }

  if (typeof anyErr?.message === 'string' && anyErr.message) {
    return {
      code: codeFromStatus(status),
      message: anyErr.message,
      status,
      requestId,
      recoverable: status !== 401,
    };
  }

  return {
    code: 'unknown',
    message: 'Something went wrong. Please try again.',
    status,
    requestId,
    recoverable: true,
  };
}

export function formatApiError(err: ApiError): string {
  if (err.requestId) {
    return `${err.message} (Ref: ${err.requestId})`;
  }
  return err.message;
}

/** Map API codes onto chat bubble Alert styles. */
export function toChatErrorType(
  code: string
):
  | 'auth_error'
  | 'cluster_unreachable'
  | 'rate_limited'
  | 'timeout'
  | 'connection_error'
  | 'rbac_forbidden'
  | undefined {
  switch (code) {
    case 'auth_required':
      return 'auth_error';
    case 'rbac_forbidden':
      return 'rbac_forbidden';
    case 'cluster_unreachable':
      return 'cluster_unreachable';
    case 'rate_limited':
      return 'rate_limited';
    case 'timeout':
      return 'timeout';
    case 'connection_error':
      return 'connection_error';
    default:
      return undefined;
  }
}

export function normalizeBackendErrors(
  raw: unknown
): { type: string; message: string; severity: string }[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  return raw.map((item) => {
    if (item && typeof item === 'object') {
      const rec = item as Record<string, unknown>;
      return {
        type: String(rec.code || rec.type || 'agent_error'),
        message: String(rec.message || item),
        severity: String(rec.severity || 'warning'),
      };
    }
    return { type: 'agent_error', message: String(item), severity: 'warning' };
  });
}
