const LINKS = [
  { label: "Pricing", href: "#pricing" },
  { label: "Docs", href: "#" },
  { label: "Support", href: "#" },
  { label: "Terms", href: "#" },
];

export default function Footer() {
  return (
    <footer className="border-t border-border px-6 py-12">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          {/* Brand */}
          <div className="flex flex-col items-center md:items-start gap-2">
            <span className="text-lg font-bold text-text-primary">
              CryptoBot Platform
            </span>
            <span className="text-sm text-text-muted">
              Built with AI. Powered by Capital.com.
            </span>
          </div>

          {/* Links */}
          <nav className="flex items-center gap-6">
            {LINKS.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="text-sm text-text-secondary hover:text-text-primary transition-colors"
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>

        {/* Copyright */}
        <div className="mt-8 pt-8 border-t border-border text-center">
          <p className="text-xs text-text-muted">
            &copy; {new Date().getFullYear()} CryptoBot Platform. All rights
            reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
