import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import Link from "next/link";
import { LogOut } from "lucide-react";

export default async function Home() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const discordId = user.user_metadata?.provider_id || user.identities?.[0]?.identity_data?.provider_id;

  if (!discordId) {
    return <div>Error identifying Discord user. Please re-login.</div>;
  }

  const { data: adminServers, error } = await supabase
    .from("guild_admins")
    .select("guild_settings_id, guild_settings(discord_guild_id)")
    .eq("discord_user_id", discordId);

  if (error || !adminServers || adminServers.length === 0) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-gray-950 p-6 text-white">
        <h1 className="text-2xl font-bold">Unauthorized</h1>
        <p className="mt-4 text-gray-400">You are not an administrator for any tracked Discord server.</p>
        <p className="mt-2 text-sm text-gray-500">Contact the bot owner to be added to the guild_admins table.</p>
        <form action="/auth/signout" method="post" className="mt-8">
          <button type="submit" className="flex items-center gap-2 rounded bg-gray-800 px-4 py-2 hover:bg-gray-700">
            <LogOut size={16} /> Sign Out
          </button>
        </form>
      </div>
    );
  }

  // Deduplicate and get guild IDs
  const guilds = adminServers.map(s => (s.guild_settings as any).discord_guild_id);

  return (
    <div className="flex min-h-screen flex-col bg-gray-950 text-white">
      <header className="flex items-center justify-between border-b border-gray-800 bg-gray-900 px-6 py-4">
        <h1 className="text-xl font-bold">Algorithm Arena</h1>
        <div className="flex items-center gap-4">
          <div className="text-sm text-gray-400">{user.user_metadata?.full_name}</div>
          <form action="/auth/signout" method="post">
            <button type="submit" className="text-gray-400 hover:text-white" title="Sign out">
              <LogOut size={20} />
            </button>
          </form>
        </div>
      </header>

      <main className="flex-1 p-8">
        <div className="mx-auto max-w-4xl">
          <h2 className="mb-6 text-2xl font-bold">Select Server</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {guilds.map(guildId => (
              <Link 
                key={guildId} 
                href={`/server/${guildId}/events`}
                className="group flex flex-col rounded-lg border border-gray-800 bg-gray-900 p-6 transition-colors hover:border-blue-500 hover:bg-gray-800/50"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-500/10 text-blue-500 group-hover:bg-blue-500 group-hover:text-white">
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>
                <h3 className="mt-4 font-semibold">Server {guildId}</h3>
                <p className="mt-1 text-sm text-gray-400">Manage events, submissions, and settings.</p>
              </Link>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
