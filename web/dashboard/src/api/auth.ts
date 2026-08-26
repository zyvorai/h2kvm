// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

const BASE_URL = '/api/v1';

export interface AuthSession {
  authenticated: boolean;
  username?: string;
}

export async function login(username: string, password: string): Promise<{ status: string; username: string }> {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: 'Login failed' }));
    throw new Error(body.error || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${BASE_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
}

export async function getSession(): Promise<AuthSession> {
  const res = await fetch(`${BASE_URL}/auth/session`, {
    credentials: 'include',
  });

  if (!res.ok) {
    return { authenticated: false };
  }

  return res.json();
}
