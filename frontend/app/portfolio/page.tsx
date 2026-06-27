import { AuthGuard } from "@/components/auth/AuthGuard";
import { PortfolioClient } from "@/components/portfolio/PortfolioClient";

export default function PortfolioPage() {
  return (
    <AuthGuard>
      <PortfolioClient />
    </AuthGuard>
  );
}
