import { redirect } from "next/navigation";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import AdminSidebar from "@/components/admin/AdminSidebar";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = createServerSupabaseClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  // Check owner role
  const { data: profile } = await supabase
    .from("profiles")
    .select("role, has_2fa")
    .eq("id", user.id)
    .single();

  if (!profile || profile.role !== "owner") {
    redirect("/dashboard");
  }

  // Owner must have 2FA
  if (!profile.has_2fa) {
    redirect("/dashboard?error=2fa_required");
  }

  return (
    <div className="flex min-h-screen bg-bg-primary">
      <AdminSidebar />
      <main className="flex-1 min-w-0">
        <div className="border-b border-border bg-bg-secondary px-6 py-4 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-bold text-text-primary pl-12 lg:pl-0">
              Admin Panel
            </h1>
            <a
              href="/dashboard"
              className="text-sm text-text-muted hover:text-text-primary transition-colors hidden lg:block"
            >
              Back to Dashboard
            </a>
          </div>
        </div>
        <div className="p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
