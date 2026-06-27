"use client";

import { useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { upsertProfile } from "@/lib/profile";

export function ProfileBootstrap() {
  useEffect(() => {
    if (!supabase) return;

    supabase.auth.getUser().then(({ data }) => {
      if (data.user) {
        upsertProfile(data.user);
      }
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        upsertProfile(session.user);
      }
    });

    return () => data.subscription.unsubscribe();
  }, []);

  return null;
}
