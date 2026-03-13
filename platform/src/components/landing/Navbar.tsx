"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
        scrolled
          ? "bg-bg-primary/80 backdrop-blur-lg border-b border-border"
          : "bg-transparent"
      )}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <a href="/" className="text-lg font-bold text-text-primary">
          CryptoBot
        </a>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <a
            href="#"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors px-4 py-2"
          >
            Login
          </a>
          <a
            href="#pricing"
            className="inline-flex items-center justify-center h-9 px-5 rounded-lg bg-accent text-white text-sm font-semibold transition-all hover:bg-accent-hover"
          >
            Get Started
          </a>
        </div>
      </div>
    </nav>
  );
}
