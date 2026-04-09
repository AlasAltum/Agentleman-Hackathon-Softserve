const TOKEN_KEY = "sre_token";

export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return null;

  // Drop the token if it's expired
  if (isTokenExpired(token)) {
    clearToken();
    return null;
  }
  return token;
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

/**
 * Decode the JWT payload and check the `exp` claim.
 * Returns true when the token is expired or unparseable.
 */
function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (typeof payload.exp !== "number") return true;
    // 5-second buffer so we don't send a request that'll be rejected
    return payload.exp * 1000 <= Date.now() - 5000;
  } catch {
    return true;
  }
}
