"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut, PieChart, User, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

export function ProfileMenu() {
  const router = useRouter();
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function closeMenu(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("mousedown", closeMenu);
    return () => document.removeEventListener("mousedown", closeMenu);
  }, []);

  async function handleLogout() {
    await supabase?.auth.signOut();
    setOpen(false);
    router.push("/");
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label="Open profile menu"
        title="Profile"
        className="grid h-10 w-10 place-items-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-950"
      >
        <UserCircle className="h-5 w-5" />
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-30 w-48 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          <Link
            href="/profile"
            onClick={() => setOpen(false)}
            className="flex h-10 items-center gap-2 rounded px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950"
          >
            <User className="h-4 w-4" />
            Profile
          </Link>
          <Link
            href="/portfolio"
            onClick={() => setOpen(false)}
            className="flex h-10 items-center gap-2 rounded px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950"
          >
            <PieChart className="h-4 w-4" />
            Portfolio
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="flex h-10 w-full items-center gap-2 rounded px-3 text-left text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-950"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      )}
    </div>
  );
}
