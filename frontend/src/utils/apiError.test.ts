import { toApiError, formatApiError, normalizeBackendErrors, toChatErrorType } from './apiError';

describe('toApiError', () => {
  it('parses standard envelope', () => {
    const err = {
      response: {
        status: 403,
        data: {
          error: {
            code: 'rbac_forbidden',
            message: 'Access denied.',
            request_id: 'abc',
            recoverable: true,
          },
          detail: 'Access denied.',
        },
        headers: { 'x-request-id': 'abc' },
      },
    };
    const api = toApiError(err);
    expect(api.code).toBe('rbac_forbidden');
    expect(api.message).toBe('Access denied.');
    expect(api.requestId).toBe('abc');
    expect(api.recoverable).toBe(true);
  });

  it('parses legacy detail string', () => {
    const api = toApiError({
      response: { status: 400, data: { detail: 'Bad query' }, headers: {} },
    });
    expect(api.message).toBe('Bad query');
    expect(api.code).toBe('validation_error');
  });

  it('parses validation array', () => {
    const api = toApiError({
      response: {
        status: 422,
        data: {
          detail: [{ loc: ['body', 'query'], msg: 'field required', type: 'value_error' }],
        },
        headers: {},
      },
    });
    expect(api.code).toBe('validation_error');
    expect(api.message).toContain('query');
  });

  it('maps timeout', () => {
    const api = toApiError({ code: 'ECONNABORTED', message: 'timeout of 120000ms exceeded' });
    expect(api.code).toBe('timeout');
    expect(api.recoverable).toBe(true);
  });

  it('auth is not recoverable', () => {
    const api = toApiError({
      response: {
        status: 401,
        data: {
          error: { code: 'auth_required', message: 'Login required', recoverable: false },
        },
        headers: {},
      },
    });
    expect(api.recoverable).toBe(false);
  });
});

describe('formatApiError', () => {
  it('includes request id when present', () => {
    expect(
      formatApiError({ code: 'x', message: 'Hi', requestId: 'rid1', recoverable: true })
    ).toBe('Hi (Ref: rid1)');
  });
});

describe('normalizeBackendErrors', () => {
  it('normalizes strings and objects', () => {
    const out = normalizeBackendErrors([
      'Stop condition',
      { code: 'agent_stop', message: 'blocked', severity: 'warning' },
    ]);
    expect(out?.[0].message).toBe('Stop condition');
    expect(out?.[1].type).toBe('agent_stop');
  });
});

describe('toChatErrorType', () => {
  it('maps codes', () => {
    expect(toChatErrorType('auth_required')).toBe('auth_error');
    expect(toChatErrorType('rbac_forbidden')).toBe('rbac_forbidden');
  });
});
