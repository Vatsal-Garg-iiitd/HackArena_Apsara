"use client";

import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { QuantyAssistant } from "@/components/quanty/QuantyAssistant";
import { supabase } from "@/lib/supabase";

export function AuthGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function checkSession() {
      if (!supabase) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        return;
      }

      const { data } = await supabase.auth.getSession();
      if (!mounted) return;

      if (!data.session) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        return;
      }

      setReady(true);
    }

    checkSession();

    const { data } =
      supabase?.auth.onAuthStateChange((_event, session) => {
        if (!session) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        } else {
          setReady(true);
        }
      }) ?? { data: null };

    return () => {
      mounted = false;
      data?.subscription.unsubscribe();
    };
  }, [pathname, router]);

  if (!ready) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 px-4 text-slate-700">
        <section className="rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <p className="text-sm font-medium">Opening your trading workspace...</p>
        </section>
      </main>
    );
  }

  return (
    <>
      {children}
      <QuantyAssistant />
    </>
  );
}
