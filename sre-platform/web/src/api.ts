import { clearToken, getToken } from "./auth";

const BASE = "/";

/**
 * Handle 401 responses globally — clear the expired/invalid token
 * and redirect to login.
 */
function handleUnauthorized(): never {
  clearToken();
  window.location.href = "/login";
  // The redirect won't happen synchronously, but throwing ensures
  // callers don't continue processing.
  throw new Error("Session expired");
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${BASE}auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  const data = await res.json();
  return data.access_token;
}

export async function submitReport(
  description: string,
  image: File,
  logs?: File | null,
): Promise<{ ticket_id: string; ticket_url?: string; action?: string }> {
  const token = getToken();
  if (!token) handleUnauthorized();

  const form = new FormData();
  form.append("description", description);
  form.append("image", image);
  if (logs) form.append("logs", logs);

  const res = await fetch(`${BASE}reports/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (res.status === 401) handleUnauthorized();
  if (!res.ok) throw new Error("Failed to submit report");
  return res.json();
}
