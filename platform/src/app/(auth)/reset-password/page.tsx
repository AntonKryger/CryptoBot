import { Suspense } from "react";
import ResetPasswordForm from "@/components/auth/ResetPasswordForm";

export const metadata = {
  title: "Reset Password — CryptoBot",
};

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="text-sm text-text-muted">Loading...</div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
