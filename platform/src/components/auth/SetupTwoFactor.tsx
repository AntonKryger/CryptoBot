"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Shield, CheckCircle, Copy, Loader2 } from "lucide-react";

type Step = 1 | 2 | 3;

interface EnrollData {
  factorId: string;
  qrCode: string;
  secret: string;
}

export default function SetupTwoFactor() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [enrollData, setEnrollData] = useState<EnrollData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Step 2: code input state
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Enroll on mount
  useEffect(() => {
    enroll();
  }, []);

  async function enroll() {
    setLoading(true);
    setError(null);

    try {
      const supabase = createClient();
      const { data, error: enrollError } = await supabase.auth.mfa.enroll({
        factorType: "totp",
        friendlyName: "CryptoBot Authenticator",
      });

      if (enrollError) {
        setError(enrollError.message);
        return;
      }

      if (!data?.totp) {
        setError("Failed to generate TOTP data. Please try again.");
        return;
      }

      setEnrollData({
        factorId: data.id,
        qrCode: data.totp.qr_code,
        secret: data.totp.secret,
      });
    } catch {
      setError("An unexpected error occurred during enrollment.");
    } finally {
      setLoading(false);
    }
  }

  async function copySecret() {
    if (!enrollData) return;
    try {
      await navigator.clipboard.writeText(enrollData.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select text
    }
  }

  // Step 2 handlers
  function handleChange(index: number, value: string) {
    const digit = value.replace(/\D/g, "").slice(-1);
    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);

    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

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

    const focusIndex = Math.min(pasted.length, 5);
    inputRefs.current[focusIndex]?.focus();

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

    if (!enrollData) {
      setError("No enrollment data. Please refresh and try again.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const supabase = createClient();

      // Challenge
      const { data: challengeData, error: challengeError } =
        await supabase.auth.mfa.challenge({
          factorId: enrollData.factorId,
        });

      if (challengeError) {
        setError(challengeError.message);
        return;
      }

      // Verify
      const { error: verifyError } = await supabase.auth.mfa.verify({
        factorId: enrollData.factorId,
        challengeId: challengeData.id,
        code: codeStr,
      });

      if (verifyError) {
        setError("Invalid code. Please try again.");
        setCode(["", "", "", "", "", ""]);
        inputRefs.current[0]?.focus();
        return;
      }

      // Success
      setStep(3);
    } catch {
      setError("An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }

  function goToStep2() {
    setStep(2);
    setError(null);
    setCode(["", "", "", "", "", ""]);
    // Focus first input after render
    setTimeout(() => inputRefs.current[0]?.focus(), 50);
  }

  // Progress indicator
  function StepIndicator() {
    return (
      <div className="flex items-center justify-center gap-2 mb-8">
        {[1, 2, 3].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                s < step
                  ? "bg-success text-white"
                  : s === step
                  ? "bg-accent text-white"
                  : "bg-bg-card text-text-muted border border-border"
              }`}
            >
              {s < step ? (
                <CheckCircle className="w-4 h-4" />
              ) : (
                s
              )}
            </div>
            {s < 3 && (
              <div
                className={`w-8 h-0.5 ${
                  s < step ? "bg-success" : "bg-border"
                }`}
              />
            )}
          </div>
        ))}
      </div>
    );
  }

  // Step 1: Show QR code and secret
  if (step === 1) {
    return (
      <div>
        <StepIndicator />

        <div className="flex items-center gap-2 mb-2">
          <Shield className="w-5 h-5 text-accent" />
          <h1 className="text-2xl font-bold text-text-primary">
            Set up 2FA
          </h1>
        </div>
        <p className="text-sm text-text-muted mb-6">
          Scan this QR code with your authenticator app (Google Authenticator,
          Authy, etc.)
        </p>

        {loading && !enrollData && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 text-accent animate-spin" />
          </div>
        )}

        {error && !enrollData && (
          <div className="text-sm text-danger bg-danger-muted rounded-lg px-3 py-2 mb-4">
            {error}
          </div>
        )}

        {enrollData && (
          <>
            {/* QR Code */}
            <div className="flex justify-center mb-6">
              <div className="bg-white rounded-xl p-3">
                <img
                  src={enrollData.qrCode}
                  alt="TOTP QR Code"
                  width={200}
                  height={200}
                  className="block"
                />
              </div>
            </div>

            {/* Secret key */}
            <div className="mb-6">
              <p className="text-xs text-text-muted mb-2">
                Or enter this key manually:
              </p>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-bg-card border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary tracking-wider select-all break-all">
                  {enrollData.secret}
                </div>
                <button
                  onClick={copySecret}
                  className="shrink-0 p-2 rounded-lg border border-border bg-bg-card hover:bg-bg-card-hover text-text-secondary hover:text-text-primary transition-colors"
                  title="Copy to clipboard"
                >
                  <Copy className="w-4 h-4" />
                </button>
              </div>
              {copied && (
                <p className="text-xs text-success mt-1">Copied to clipboard</p>
              )}
            </div>

            <Button className="w-full" onClick={goToStep2}>
              Next
            </Button>
          </>
        )}
      </div>
    );
  }

  // Step 2: Verify code
  if (step === 2) {
    return (
      <div>
        <StepIndicator />

        <h1 className="text-2xl font-bold text-text-primary mb-2">
          Verify your code
        </h1>
        <p className="text-sm text-text-muted mb-8">
          Enter the 6-digit code from your authenticator app
        </p>

        <div className="flex gap-2 justify-center mb-6" onPaste={handlePaste}>
          {code.map((digit, i) => (
            <input
              key={i}
              ref={(el) => {
                inputRefs.current[i] = el;
              }}
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
          {loading ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Verifying...
            </span>
          ) : (
            "Verify & Enable"
          )}
        </Button>

        <button
          onClick={() => {
            setStep(1);
            setError(null);
          }}
          className="w-full text-xs text-text-muted text-center mt-4 hover:text-text-secondary transition-colors"
        >
          Back to QR code
        </button>
      </div>
    );
  }

  // Step 3: Success
  return (
    <div>
      <StepIndicator />

      <div className="flex flex-col items-center text-center">
        <div className="w-16 h-16 rounded-full bg-success/20 flex items-center justify-center mb-4">
          <CheckCircle className="w-8 h-8 text-success" />
        </div>

        <h1 className="text-2xl font-bold text-text-primary mb-2">
          Two-factor authentication enabled!
        </h1>
        <p className="text-sm text-text-muted mb-8">
          Your account is now more secure. You will need your authenticator app
          each time you sign in.
        </p>

        <Button
          className="w-full"
          onClick={() => {
            router.push("/dashboard");
            router.refresh();
          }}
        >
          Continue to Dashboard
        </Button>
      </div>
    </div>
  );
}
