import { Suspense } from "react";
import TwoFactorInput from "@/components/auth/TwoFactorInput";

export default function VerifyTwoFactorPage() {
  return (
    <Suspense>
      <TwoFactorInput />
    </Suspense>
  );
}
