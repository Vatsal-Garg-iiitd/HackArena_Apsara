"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";
import { ProfileMenu } from "@/components/auth/ProfileMenu";
import { supabase } from "@/lib/supabase";

export function ProfileClient() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    supabase?.auth.getUser().then(({ data }) => setUser(data.user ?? null));
  }, []);

  const fullName = user?.user_metadata?.full_name || user?.user_metadata?.name || "Trader";

  return (
    <main className="soft-page min-h-screen px-4 py-5 text-slate-700 md:px-8">
      <div className="mx-auto max-w-4xl">
        <header className="mb-5 flex items-center justify-between gap-3 border-b border-slate-200 pb-4">
          <div>
            <Link href="/dashboard" className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900">
              <ArrowLeft className="h-4 w-4" />
              Dashboard
            </Link>
            <h1 className="text-2xl font-semibold text-slate-800">Profile</h1>
          </div>
          <ProfileMenu />
        </header>

        <section className="surface-panel rounded-lg border p-5">
          <div className="grid h-14 w-14 place-items-center rounded bg-slate-900 text-xl font-semibold text-white">
            {fullName.slice(0, 1).toUpperCase()}
          </div>
          <h2 className="mt-4 text-xl font-semibold text-slate-800">{fullName}</h2>
          <p className="mt-1 text-sm text-slate-500">{user?.email}</p>
          <div className="mt-5 grid gap-3 text-sm md:grid-cols-2">
            <div className="rounded border border-slate-200 bg-white/80 p-3 shadow-sm">
              <div className="text-slate-400">User ID</div>
              <div className="mt-1 break-all font-mono text-slate-700">{user?.id}</div>
            </div>
            <div className="rounded border border-slate-200 bg-white/80 p-3 shadow-sm">
              <div className="text-slate-400">Provider</div>
              <div className="mt-1 font-mono text-slate-700">{user?.app_metadata?.provider ?? "email"}</div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
