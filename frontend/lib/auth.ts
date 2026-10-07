import Cookies from 'js-cookie';

let redirectingToLogin = false;

export class SessionExpiredError extends Error {
  constructor() {
    super('Your session has expired. Redirecting to sign in...');
    this.name = 'SessionExpiredError';
  }
}

export function getLoginUrl(returnPath: string) {
  return `/?redirect=${encodeURIComponent(returnPath)}`;
}

export function getRedirectTarget(value: string | null) {
  if (!value || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u0020]/.test(value)) {
    return '/home';
  }
  const url = new URL(value, 'https://frontend.invalid');
  if (url.origin !== 'https://frontend.invalid' || !/^\/home(?:\/|$)/.test(url.pathname)) {
    return '/home';
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function redirectToLogin() {
  // Group pages load several resources concurrently; only the first failure navigates.
  if (redirectingToLogin) return;
  Cookies.remove('token');
  const { pathname, search, hash } = window.location;
  if (pathname !== '/') {
    redirectingToLogin = true;
    window.location.replace(getLoginUrl(`${pathname}${search}${hash}`));
  }
}

export async function authenticatedFetch(input: RequestInfo | URL, init?: RequestInit) {
  const token = Cookies.get('token');
  if (!token) {
    redirectToLogin();
    throw new SessionExpiredError();
  }
  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401) {
    redirectToLogin();
    throw new SessionExpiredError();
  }
  return response;
}

export function checkGroupResponse(response: Response, action: string) {
  if (response.status === 403) throw new Error('You do not have permission to access this group.');
  if (response.status === 404) throw new Error('Group not found.');
  if (!response.ok) throw new Error(`${action} (HTTP ${response.status}).`);
}
