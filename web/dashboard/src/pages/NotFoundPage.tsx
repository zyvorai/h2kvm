// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: LicenseRef-Zyvor-Production-1.0
// https://zyvor.dev · info@zyvor.dev

import { Link } from 'react-router-dom';
import { ConsolePageHeader } from '../components/console/ConsolePageHeader';
import { AlertCircle, ArrowLeft } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto mb-6">
          <AlertCircle className="h-8 w-8 text-red-400" />
        </div>
      <ConsolePageHeader title="Page not found" subtitle="That view is not in the console." />
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-lg text-sm font-medium hover:bg-blue-600/30 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
