import { Suspense } from "react";
import { AuthCard } from "@/components/auth/AuthCard";

export default function SignupPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-50" />}>
      <AuthCard mode="signup" />
    </Suspense>
  );
}
