import { AuthGuard } from "@/components/auth/AuthGuard";
import { ProfileClient } from "@/components/profile/ProfileClient";

export default function ProfilePage() {
  return (
    <AuthGuard>
      <ProfileClient />
    </AuthGuard>
  );
}
