import { createClient } from "@/lib/supabase/server";

export default async function LeaderboardPage({ params }: { params: { guild_id: string } }) {
  const supabase = await createClient();
  
  // Get guild_settings_id
  const { data: guildSetting } = await supabase
    .from("guild_settings")
    .select("id")
    .eq("discord_guild_id", params.guild_id)
    .single();

  let members = [];
  if (guildSetting) {
    const { data } = await supabase
      .from("guild_members")
      .select(`
        *,
        user:users(discord_user_id)
      `)
      .eq("guild_settings_id", guildSetting.id)
      .order("arena_points_current_cycle", { ascending: false })
      .limit(100);
    
    members = data || [];
  }

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Server Leaderboard</h2>
      <p className="mb-6 text-gray-400">Current cycle standings for this server.</p>

      <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-900">
        <table className="w-full text-left text-sm text-gray-300">
          <thead className="bg-gray-800/50 text-xs uppercase text-gray-400">
            <tr>
              <th className="px-6 py-4">Rank</th>
              <th className="px-6 py-4">User ID</th>
              <th className="px-6 py-4 text-right">Cycle Points</th>
              <th className="px-6 py-4 text-right">All Time Points</th>
              <th className="px-6 py-4 text-center">Verified</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {members.map((member: any, idx: number) => (
              <tr key={member.id} className="hover:bg-gray-800/50">
                <td className="px-6 py-4 font-medium text-white">#{idx + 1}</td>
                <td className="px-6 py-4 font-mono text-gray-400">{member.user?.discord_user_id}</td>
                <td className="px-6 py-4 text-right font-bold text-white">{member.arena_points_current_cycle}</td>
                <td className="px-6 py-4 text-right text-gray-400">{member.arena_points_all_time}</td>
                <td className="px-6 py-4 text-center">
                  {member.verified_competitor ? (
                    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-green-500/10 text-green-500">✓</span>
                  ) : (
                    <span className="text-gray-600">-</span>
                  )}
                </td>
              </tr>
            ))}
            {members.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  No members found on the leaderboard yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
