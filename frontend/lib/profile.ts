import type { User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

export async function upsertProfile(user: User) {
  if (!supabase) return;

  const fullName =
    user.user_metadata?.full_name ||
    user.user_metadata?.name ||
    user.email?.split("@")[0] ||
    "Trader";

  await supabase.from("profiles").upsert(
    {
      id: user.id,
      email: user.email,
      full_name: fullName,
      avatar_url: user.user_metadata?.avatar_url || null,
      provider: user.app_metadata?.provider || "email",
      updated_at: new Date().toISOString()
    },
    { onConflict: "id" }
  );
}
