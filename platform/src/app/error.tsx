"use client";

import Link from "next/link";
import { AlertTriangle, Home } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen bg-bg-primary flex flex-col items-center justify-center px-4">
      <div className="flex items-center justify-center w-16 h-16 rounded-full bg-danger/10 mb-6">
        <AlertTriangle className="w-8 h-8 text-danger" />
      </div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        Something went wrong
      </h1>
      <p className="text-sm text-text-muted mb-8 max-w-sm text-center">
        An unexpected error occurred. Please try again or go back to the home
        page.
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={reset}
          className="inline-flex items-center gap-2 h-10 px-4 text-sm font-medium rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors"
        >
          Try again
        </button>
        <Link
          href="/"
          className="inline-flex items-center gap-2 h-10 px-4 text-sm font-medium rounded-lg border border-border bg-transparent text-text-primary hover:bg-bg-card-hover hover:border-border-hover transition-colors"
        >
          <Home className="w-4 h-4" />
          Go home
        </Link>
      </div>
      {error.digest && (
        <p className="text-xs text-text-muted mt-6">
          Error ID: {error.digest}
        </p>
      )}
    </div>
  );
}
