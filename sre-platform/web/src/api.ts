import { getToken } from "./auth";

const BASE = "/";

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
): Promise<{ report_id: string }> {
  const token = getToken();
  const form = new FormData();
  form.append("description", description);
  form.append("image", image);
  if (logs) form.append("logs", logs);

  const res = await fetch(`${BASE}reports/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) throw new Error("Failed to submit report");
  return res.json();
}
