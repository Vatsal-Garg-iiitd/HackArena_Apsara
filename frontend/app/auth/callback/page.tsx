"use client";

import { Suspense } from "react";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { upsertProfile } from "@/lib/profile";
import { supabase } from "@/lib/supabase";

function AuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState("Completing authentication...");

  useEffect(() => {
    async function completeAuth() {
      if (!supabase) {
        setMessage("Supabase is not configured.");
        return;
      }

      const code = searchParams.get("code");
      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);
        if (error) {
          setMessage("Authentication failed. Please login again.");
          return;
        }
      }

      const { data, error } = await supabase.auth.getUser();
      if (error || !data.user) {
        setMessage("Authentication failed. Please login again.");
        return;
      }

      await upsertProfile(data.user);
      const next = searchParams.get("next");
      router.replace(next?.startsWith("/") ? next : "/dashboard");
    }

    completeAuth();
  }, [router, searchParams]);

  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 px-4 text-slate-700">
      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-sm">{message}</p>
      </section>
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-slate-50" />}>
      <AuthCallbackContent />
    </Suspense>
  );
}
