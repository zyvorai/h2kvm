// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
// https://zyvor.dev · info@zyvor.dev

import { useMemo, useState, type FormEvent } from 'react';
import { useAuthStore } from '../stores/auth';

export function LoginPage() {
  const saved = useMemo(() => {
    try {
      const raw = localStorage.getItem('h2kweb-saved-login');
      return raw ? JSON.parse(raw) as { username?: string; password?: string } : null;
    } catch {
      return null;
    }
  }, []);

  const [username, setUsername] = useState(saved?.username || '');
  const [password, setPassword] = useState(saved?.password ? atob(saved.password) : '');
  const [submitting, setSubmitting] = useState(false);
  const [rememberMe, setRememberMe] = useState(!!saved);
  const { login, error } = useAuthStore();

  const where = useMemo(() => {
    if (typeof window === 'undefined') {
      return { host: 'localhost', address: 'localhost', connection: 'HTTP' };
    }
    const { hostname, host, protocol } = window.location;
    return {
      host: hostname || 'localhost',
      address: host || hostname || 'localhost',
      connection: protocol === 'https:' ? 'HTTPS' : 'HTTP',
    };
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(username, password);
      if (rememberMe) {
        localStorage.setItem('h2kweb-saved-login', JSON.stringify({ username, password: btoa(password) }));
      } else {
        localStorage.removeItem('h2kweb-saved-login');
      }
    } catch {
      /* error is set in store */
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-chapters">
        <section className="login-chapter login-chapter-project">
          <p className="login-kicker">Migration console</p>
          <h1 className="login-headline">h2kvm</h1>
          <p className="login-lede">
            Converts disks offline and lands them on KVM and KubeVirt.
          </p>
        </section>

        <section className="login-chapter login-chapter-signin">
          <div className="login-card">
            <h2 className="login-card-title">Sign in</h2>
            <form className="login-form" onSubmit={handleSubmit}>
              <label className="login-field">
                Username
                <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
              </label>
              <label className="login-field">
                Password
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
              </label>
              <label className="login-remember">
                <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} />
                Remember this browser
              </label>
              {error && <p className="login-error">{error}</p>}
              <button className="btn btn-primary login-submit" type="submit" disabled={submitting}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          </div>
        </section>

        <dl className="login-chapter login-where" aria-label="Where you are signing in">
          <div>
            <dt>Project</dt>
            <dd>h2kvm</dd>
          </div>
          <div>
            <dt>Host</dt>
            <dd>{where.host}</dd>
          </div>
          <div>
            <dt>Address</dt>
            <dd>{where.address}</dd>
          </div>
          <div>
            <dt>Connection</dt>
            <dd>{where.connection}</dd>
          </div>
        </dl>

        <section className="login-suite" aria-label="Zyvor tools">
          <a href="https://github.com/zyvorai/guestkit">GuestKit</a>
          <span>repairs the disk offline before power-on</span>
          <a href="https://github.com/zyvorai/zorvia">Zorvia</a>
          <span>shows the VM booting</span>
        </section>
      </div>
    </div>
  );
}
