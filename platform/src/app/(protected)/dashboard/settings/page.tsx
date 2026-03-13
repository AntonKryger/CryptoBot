"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { useTheme } from "@/hooks/useTheme";
import { THEMES, THEME_LABELS, type Theme } from "@/lib/constants";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import {
  User,
  Palette,
  AlertTriangle,
  LogOut,
  Save,
  Check,
  Link2,
} from "lucide-react";

const THEME_ACCENT_COLORS: Record<Theme, string> = {
  midnight: "#6366f1",
  matrix: "#22c55e",
  aurora: "#a78bfa",
  stealth: "#e5e5e5",
  solar: "#f59e0b",
};

export default function SettingsPage() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [userEmail, setUserEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data }) => {
      setUserEmail(data.user?.email ?? "");
      setFullName(data.user?.user_metadata?.full_name ?? "");
    });
  }, []);

  function handleSaveProfile() {
    // Mock save -- will connect to Supabase later
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/");
    router.refresh();
  }

  return (
    <DashboardLayout pageTitle="Settings">
      <div className="max-w-2xl space-y-8">
        {/* Account section */}
        <section className="rounded-xl border border-border bg-bg-card p-6 backdrop-blur-sm shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-muted">
              <User className="h-5 w-5 text-accent" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Account</h2>
              <p className="text-sm text-text-muted">Manage your profile information</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Email
              </label>
              <Input
                type="email"
                value={userEmail}
                disabled
                className="opacity-60"
              />
              <p className="text-xs text-text-muted mt-1">
                Email cannot be changed. Contact support if needed.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Full Name
              </label>
              <Input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
              />
            </div>

            <Button onClick={handleSaveProfile} className="mt-2">
              {saved ? (
                <>
                  <Check className="h-4 w-4 mr-2" />
                  Saved
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save Changes
                </>
              )}
            </Button>
          </div>
        </section>

        {/* Exchange Connection section */}
        <section className="rounded-xl border border-border bg-bg-card p-6 backdrop-blur-sm shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-muted">
              <Link2 className="h-5 w-5 text-accent" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Exchange Connection</h2>
              <p className="text-sm text-text-muted">Your connected trading exchange</p>
            </div>
          </div>

          <div className="rounded-lg border border-border p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-bg-secondary flex items-center justify-center">
                <span className="text-lg font-bold text-accent">C</span>
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">Capital.com</p>
                <p className="text-xs text-text-muted">Demo account connected</p>
              </div>
            </div>
            <Badge variant="success">Connected</Badge>
          </div>
        </section>

        {/* Theme section */}
        <section className="rounded-xl border border-border bg-bg-card p-6 backdrop-blur-sm shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-muted">
              <Palette className="h-5 w-5 text-accent" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Theme</h2>
              <p className="text-sm text-text-muted">Customize the look and feel</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {THEMES.map((t) => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                className={cn(
                  "flex items-center gap-3 rounded-lg border p-4 transition-all",
                  t === theme
                    ? "border-accent bg-accent-muted ring-1 ring-accent"
                    : "border-border bg-bg-primary/50 hover:border-border-hover hover:bg-bg-card-hover"
                )}
              >
                <span
                  className="h-8 w-8 rounded-lg shrink-0 border border-border"
                  style={{ backgroundColor: THEME_ACCENT_COLORS[t] }}
                />
                <div className="text-left">
                  <p
                    className={cn(
                      "text-sm font-medium",
                      t === theme ? "text-accent" : "text-text-primary"
                    )}
                  >
                    {THEME_LABELS[t]}
                  </p>
                  <p className="text-xs text-text-muted">
                    {t === "midnight" && "Deep blue with indigo accents"}
                    {t === "matrix" && "Green terminal aesthetic"}
                    {t === "aurora" && "Purple and violet tones"}
                    {t === "stealth" && "Minimal monochrome"}
                    {t === "solar" && "Warm amber and gold"}
                  </p>
                </div>
                {t === theme && (
                  <span className="ml-auto text-accent">
                    <Check className="h-5 w-5" />
                  </span>
                )}
              </button>
            ))}
          </div>
        </section>

        {/* Danger zone */}
        <section className="rounded-xl border border-danger/30 bg-bg-card p-6 backdrop-blur-sm shadow-sm">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-danger-muted">
              <AlertTriangle className="h-5 w-5 text-danger" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Danger Zone</h2>
              <p className="text-sm text-text-muted">Irreversible actions</p>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border p-4">
              <div>
                <p className="text-sm font-medium text-text-primary">Sign Out</p>
                <p className="text-xs text-text-muted">
                  End your current session and return to the login page.
                </p>
              </div>
              <Button variant="danger" size="sm" onClick={handleSignOut}>
                <LogOut className="h-4 w-4 mr-2" />
                Sign Out
              </Button>
            </div>
          </div>
        </section>
      </div>
    </DashboardLayout>
  );
}
