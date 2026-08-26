// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useState } from 'react';
import {
  Lock,
  User,
  Loader2,
  Eye,
  EyeOff,
  ArrowRight,
  Zap,
  Wrench,
  LayoutDashboard,
  Ship,
  CheckCircle,
  Server,
} from 'lucide-react';
import { useAuthStore } from '../stores/auth';
import { ZyvorInline } from '../components/ZyvorBrand';
import {
  PremiumLoginShell,
  LoginField,
  LoginSubmit,
  LoginRemember,
  LoginError,
} from '../components/PremiumLoginShell';

const features = [
  {
    icon: <Zap className="w-5 h-5 text-blue-100" />,
    gradient: 'from-blue-500/95 to-indigo-700/95',
    glow: 'shadow-blue-500/25',
    title: 'Multi-Platform Import',
    description: 'VMware, Hyper-V, Azure, AWS, OVA/OVF',
  },
  {
    icon: <Wrench className="w-5 h-5 text-sky-100" />,
    gradient: 'from-sky-500/95 to-indigo-800/95',
    glow: 'shadow-sky-500/25',
    title: 'Offline Guest Fixes',
    description: 'VMCraft engine, driver injection, GRUB repair',
  },
  {
    icon: <LayoutDashboard className="w-5 h-5 text-violet-100" />,
    gradient: 'from-violet-500/95 to-purple-800/95',
    glow: 'shadow-violet-500/25',
    title: '20+ VM Panels',
    description: 'Guest agent, security, storage, processes, network',
  },
  {
    icon: <Ship className="w-5 h-5 text-cyan-100" />,
    gradient: 'from-cyan-500/95 to-blue-800/95',
    glow: 'shadow-cyan-500/25',
    title: 'KubeVirt Deploy',
    description: 'Migrate VMs to Kubernetes with live monitoring',
  },
];

function BoltLogo({ className = 'w-7 h-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z" />
    </svg>
  );
}

export function LoginPage() {
  const saved = (() => {
    try {
      const raw = localStorage.getItem('h2kweb-saved-login');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  })();

  const [username, setUsername] = useState(saved?.username || '');
  const [password, setPassword] = useState(saved?.password ? atob(saved.password) : '');
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(!!saved);
  const { login, error } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(username, password);
      if (rememberMe) {
        localStorage.setItem(
          'h2kweb-saved-login',
          JSON.stringify({ username, password: btoa(password) }),
        );
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
    <PremiumLoginShell
      variant="macos"
      accent="blue"
      heroWidth="55"
      logo={
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-600/30 border border-white/20">
          <BoltLogo className="w-7 h-7 text-white" />
        </div>
      }
      productName="hyper2kvm"
      productSubtitle="VM Migration Dashboard"
      heroHeadline={
        <>
          Production-grade
          <br />
          <span className="login-text-gradient">VM migration</span>
        </>
      }
      heroSubheadline="Move workloads from any hypervisor to KVM, KubeVirt, or libvirt — with offline fixes baked in."
      pills={[
        { icon: <Server className="w-3 h-3" />, label: '140+ APIs' },
        { label: 'PAM auth' },
        { label: 'Windows + Linux' },
      ]}
      features={features}
      heroFooter={
        <div className="flex items-center gap-2 text-blue-100/40 text-sm">
          <span>140+ API endpoints</span>
          <span className="text-blue-200/30">·</span>
          <span>PAM authentication</span>
          <span className="text-blue-200/30">·</span>
          <span>hypersdk.cloud</span>
        </div>
      }
      mobileSubtitle="VM Migration Dashboard"
      panelTitle="Welcome back"
      panelSubtitle="Sign in with your system account"
      footer={<ZyvorInline className="block text-center py-3" />}
    >
      <form onSubmit={handleSubmit}>
        {error ? <LoginError message={error} /> : null}

        <div className="space-y-5">
          <LoginField label="Username" id="username">
            <User className="login-field-icon" />
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="System username"
              autoComplete="username"
              autoFocus
              required
              className="login-input"
            />
          </LoginField>

          <LoginField label="Password" id="password">
            <Lock className="login-field-icon" />
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
              className="login-input pr-11"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/45 hover:text-white/75 transition-colors"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </LoginField>
        </div>

        <LoginRemember
          checked={rememberMe}
          onChange={(checked) => {
            setRememberMe(checked);
            if (!checked) localStorage.removeItem('h2kweb-saved-login');
          }}
        />

        <LoginSubmit loading={submitting} disabled={!username || !password}>
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin relative z-10" />
              <span className="relative z-10">Signing in…</span>
            </>
          ) : (
            <>
              <span className="relative z-10">Sign in</span>
              <ArrowRight className="h-4 w-4 relative z-10" />
            </>
          )}
        </LoginSubmit>

        <div className="mt-6 pt-5 border-t border-white/[0.08] flex items-center justify-center gap-2 text-xs text-white/45">
          <CheckCircle className="h-3.5 w-3.5 text-blue-400/80" />
          <span>Secured with system PAM authentication</span>
        </div>
      </form>
    </PremiumLoginShell>
  );
}
