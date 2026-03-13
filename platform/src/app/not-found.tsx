import Link from "next/link";
import { Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-bg-primary flex flex-col items-center justify-center px-4">
      <p className="text-sm font-medium tracking-widest uppercase text-text-muted mb-4">
        CryptoBot
      </p>
      <h1 className="text-8xl font-bold text-text-primary mb-2">404</h1>
      <p className="text-lg text-text-secondary mb-8">
        Page not found
      </p>
      <p className="text-sm text-text-muted mb-8 max-w-sm text-center">
        The page you&apos;re looking for doesn&apos;t exist or has been moved.
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-2 h-10 px-4 text-sm font-medium rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors"
      >
        <Home className="w-4 h-4" />
        Go back home
      </Link>
    </div>
  );
}
