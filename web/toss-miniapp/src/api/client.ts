/**
 * Toss 미니앱 HTTP 클라이언트.
 *
 * fetch 기반 — RN 표준 API. axios 미사용.
 * 식별자 헤더(x-anon-key) 는 Phase 4 에서 useTossAuth 가 setAuthHeader() 로 주입.
 */

// 백엔드 API 베이스 URL.
// Phase 4 에서 plugin-env 도입 후 import.meta.env.API_BASE 로 교체할 것.
const API_BASE = 'https://api.apt-recom.kr';

// 모든 요청에 자동 부착되는 헤더. 인증/식별 헤더는 setAuthHeader() 로 변경.
const defaultHeaders: Record<string, string> = {
  'content-type': 'application/json',
  accept: 'application/json',
};

export function setAuthHeader(name: string, value: string | null): void {
  if (value) {
    defaultHeaders[name.toLowerCase()] = value;
  } else {
    delete defaultHeaders[name.toLowerCase()];
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public path: string,
    message?: string
  ) {
    super(message ?? `API ${status} ${path}`);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const search = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(
      ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`
    )
    .join('&');
  return search ? `${url}?${search}` : url;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = 'GET', query, body, signal } = options;
  const url = buildUrl(path, query);
  // RN 타입의 fetch 시그니처가 글로벌 AbortSignal 과 호환되지 않아 RequestInit 캐스팅.
  const init: RequestInit = {
    method,
    headers: defaultHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: signal as RequestInit['signal'],
  };
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const errBody = await res.text();
      detail = errBody.slice(0, 200);
    } catch {
      // ignore body read errors
    }
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}
