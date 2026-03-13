"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Link from "next/link";
import { Lock, ArrowLeft } from "lucide-react";

type PasswordStrength = "weak" | "medium" | "strong";

function getPasswordStrength(password: string): PasswordStrength {
  if (password.length < 8) return "weak";

  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^a-zA-Z0-9]/.test(password)) score++;

  if (score >= 4) return "strong";
  if (score >= 2) return "medium";
  return "weak";
}

const strengthConfig: Record<
  PasswordStrength,
  { label: string; color: string; width: string }
> = {
  weak: { label: "Weak", color: "bg-danger", width: "w-1/3" },
  medium: { label: "Medium", color: "bg-yellow-500", width: "w-2/3" },
  strong: { label: "Strong", color: "bg-success", width: "w-full" },
};

export default function ResetPasswordForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const strength = password ? getPasswordStrength(password) : null;
  const passwordsMatch =
    confirmPassword.length > 0 && password === confirmPassword;
  const passwordsMismatch =
    confirmPassword.length > 0 && password !== confirmPassword;

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => {
        router.push("/login");
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [success, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const supabase = createClient();
      const { error: updateError } = await supabase.auth.updateUser({
        password,
      });

      if (updateError) {
        setError(updateError.message);
        return;
      }

      setSuccess(true);
    } catch {
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div>
        <div className="flex items-center justify-center w-12 h-12 rounded-full bg-success/10 mb-4">
          <Lock className="w-6 h-6 text-success" />
        </div>
        <h1 className="text-2xl font-bold text-text-primary mb-2">
          Password updated!
        </h1>
        <p className="text-sm text-text-muted mb-8">
          Your password has been reset successfully. Redirecting to login...
        </p>
        <Link
          href="/login"
          className="inline-flex items-center gap-1.5 text-sm text-accent hover:text-accent-hover transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Go to login now
        </Link>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        Reset your password
      </h1>
      <p className="text-sm text-text-muted mb-8">
        Enter your new password below.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="password"
            className="block text-xs font-medium text-text-secondary mb-1.5"
          >
            New Password
          </label>
          <Input
            id="password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
            autoFocus
          />
          {strength && (
            <div className="mt-2">
              <div className="h-1 w-full bg-border rounded-full overflow-hidden">
                <div
                  className={`h-full ${strengthConfig[strength].color} ${strengthConfig[strength].width} rounded-full transition-all duration-300`}
                />
              </div>
              <p className="text-xs text-text-muted mt-1">
                Password strength:{" "}
                <span
                  className={
                    strength === "strong"
                      ? "text-success"
                      : strength === "medium"
                        ? "text-yellow-500"
                        : "text-danger"
                  }
                >
                  {strengthConfig[strength].label}
                </span>
              </p>
            </div>
          )}
        </div>

        <div>
          <label
            htmlFor="confirm-password"
            className="block text-xs font-medium text-text-secondary mb-1.5"
          >
            Confirm Password
          </label>
          <Input
            id="confirm-password"
            type="password"
            placeholder="••••••••"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
          {passwordsMatch && (
            <p className="text-xs text-success mt-1">Passwords match</p>
          )}
          {passwordsMismatch && (
            <p className="text-xs text-danger mt-1">Passwords do not match</p>
          )}
        </div>

        {error && (
          <div className="text-sm text-danger bg-danger-muted rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Updating..." : "Reset Password"}
        </Button>
      </form>

      <p className="text-xs text-text-muted text-center mt-6">
        <Link
          href="/login"
          className="inline-flex items-center gap-1 text-accent hover:text-accent-hover transition-colors"
        >
          <ArrowLeft className="w-3 h-3" />
          Back to login
        </Link>
      </p>
    </div>
  );
}
