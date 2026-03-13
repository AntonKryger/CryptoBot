import { Suspense } from "react";
import SetupTwoFactor from "@/components/auth/SetupTwoFactor";

export default function SetupTwoFactorPage() {
  return (
    <Suspense>
      <SetupTwoFactor />
    </Suspense>
  );
}
