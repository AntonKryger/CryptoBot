import Link from "next/link";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      {/* Minimal nav */}
      <nav className="h-16 flex items-center px-8">
        <Link
          href="/"
          className="text-sm font-semibold tracking-widest uppercase text-text-secondary hover:text-text-primary transition-colors"
        >
          CryptoBot
        </Link>
      </nav>

      {/* Centered auth card */}
      <div className="flex-1 flex items-center justify-center px-4 pb-16">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
