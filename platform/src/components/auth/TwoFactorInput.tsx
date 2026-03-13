"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";

export default function TwoFactorInput() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/dashboard";

  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    inputRefs.current[0]?.focus();
  }, []);

  function handleChange(index: number, value: string) {
    // Only allow digits
    const digit = value.replace(/\D/g, "").slice(-1);
    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);

    // Auto-advance to next input
    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    // Auto-submit when all 6 digits entered
    if (digit && index === 5) {
      const fullCode = newCode.join("");
      if (fullCode.length === 6) {
        handleVerify(fullCode);
      }
    }
  }

  function handleKeyDown(index: number, e: React.KeyboardEvent) {
    if (e.key === "Backspace" && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 0) return;

    const newCode = [...code];
    for (let i = 0; i < pasted.length; i++) {
      newCode[i] = pasted[i];
    }
    setCode(newCode);

    // Focus last filled input or next empty
    const focusIndex = Math.min(pasted.length, 5);
    inputRefs.current[focusIndex]?.focus();

    // Auto-submit if all 6 digits
    if (pasted.length === 6) {
      handleVerify(pasted);
    }
  }

  async function handleVerify(verifyCode?: string) {
    const codeStr = verifyCode || code.join("");
    if (codeStr.length !== 6) {
      setError("Enter all 6 digits.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const supabase = createClient();

      // Get the TOTP factor
      const { data: factorsData } = await supabase.auth.mfa.listFactors();
      const totpFactor = factorsData?.totp?.find(
        (f) => f.status === "verified"
      );

      if (!totpFactor) {
        setError("No 2FA factor found. Please log in again.");
        return;
      }

      // Create challenge
      const { data: challengeData, error: challengeError } =
        await supabase.auth.mfa.challenge({
          factorId: totpFactor.id,
        });

      if (challengeError) {
        setError(challengeError.message);
        return;
      }

      // Verify
      const { error: verifyError } = await supabase.auth.mfa.verify({
        factorId: totpFactor.id,
        challengeId: challengeData.id,
        code: codeStr,
      });

      if (verifyError) {
        setError("Invalid code. Please try again.");
        setCode(["", "", "", "", "", ""]);
        inputRefs.current[0]?.focus();
        return;
      }

      // Success — session is now AAL2
      router.push(redirect);
      router.refresh();
    } catch {
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-2">
        Two-factor authentication
      </h1>
      <p className="text-sm text-text-muted mb-8">
        Enter the 6-digit code from your authenticator app
      </p>

      <div className="flex gap-2 justify-center mb-6" onPaste={handlePaste}>
        {code.map((digit, i) => (
          <input
            key={i}
            ref={(el) => { inputRefs.current[i] = el; }}
            type="text"
            inputMode="numeric"
            maxLength={1}
            value={digit}
            onChange={(e) => handleChange(i, e.target.value)}
            onKeyDown={(e) => handleKeyDown(i, e)}
            className="w-11 h-13 text-center text-lg font-mono font-bold rounded-lg border border-border bg-bg-input text-text-primary focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-colors"
            disabled={loading}
          />
        ))}
      </div>

      {error && (
        <div className="text-sm text-danger bg-danger-muted rounded-lg px-3 py-2 mb-4">
          {error}
        </div>
      )}

      <Button
        className="w-full"
        onClick={() => handleVerify()}
        disabled={loading || code.join("").length !== 6}
      >
        {loading ? "Verifying..." : "Verify"}
      </Button>

      <p className="text-xs text-text-muted text-center mt-6">
        Lost access to your authenticator?{" "}
        <button
          onClick={() => router.push("/login")}
          className="text-accent hover:text-accent-hover transition-colors"
        >
          Sign in again
        </button>
      </p>
    </div>
  );
}
