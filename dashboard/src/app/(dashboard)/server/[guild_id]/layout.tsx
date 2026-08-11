import Link from "next/link";
import { headers } from "next/headers";
import { LayoutDashboard, Calendar, Shield, Trophy, Settings, Users, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { guild_id: string };
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const navigation = [
    { name: "Events", href: `/server/${params.guild_id}/events`, icon: Calendar },
    { name: "Auto Events", href: `/server/${params.guild_id}/auto-events`, icon: LayoutDashboard },
    { name: "Moderation Queue", href: `/server/${params.guild_id}/moderation`, icon: Shield },
    { name: "Leaderboard", href: `/server/${params.guild_id}/leaderboard`, icon: Trophy },
    { name: "Users & Roles", href: `/server/${params.guild_id}/users`, icon: Users },
    { name: "Settings", href: `/server/${params.guild_id}/settings`, icon: Settings },
  ];

  return (
    <div className="flex min-h-screen bg-gray-950 text-white">
      {/* Sidebar */}
      <aside className="w-64 border-r border-gray-800 bg-gray-900 flex flex-col">
        <div className="flex h-16 items-center px-6 border-b border-gray-800">
          <Link href="/" className="font-bold text-lg hover:text-gray-300">
            &larr; All Servers
          </Link>
        </div>
        <div className="px-6 py-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Server {params.guild_id}
          </p>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className="group flex items-center rounded-md px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-800 hover:text-white"
              >
                <Icon className="mr-3 h-5 w-5 flex-shrink-0 text-gray-400 group-hover:text-white" />
                {item.name}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-gray-800 p-4">
          <div className="flex items-center gap-3">
            <div className="flex-1 truncate">
              <p className="text-sm font-medium text-white truncate">{user?.user_metadata?.full_name}</p>
            </div>
            <form action="/auth/signout" method="post">
              <button type="submit" className="text-gray-400 hover:text-white">
                <LogOut size={18} />
              </button>
            </form>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
