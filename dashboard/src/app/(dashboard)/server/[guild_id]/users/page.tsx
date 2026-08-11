import { createClient } from "@/lib/supabase/server";

export default async function UsersPage({ params }: { params: { guild_id: string } }) {
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
        user:users(discord_user_id),
        linked_accounts(*)
      `)
      .eq("guild_settings_id", guildSetting.id)
      .order("cp_star_rating", { ascending: false });
    
    members = data || [];
  }

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Users & Roles Breakdown</h2>
      <p className="mb-6 text-gray-400">Explanation of how each user's star rating is calculated based on their linked accounts.</p>

      <div className="grid gap-6">
        {members.map((member: any) => {
          const cpAccounts = member.linked_accounts?.filter((acc: any) => ["codeforces", "codechef", "atcoder"].includes(acc.platform)) || [];
          const dsaAccounts = member.linked_accounts?.filter((acc: any) => ["leetcode"].includes(acc.platform)) || [];
          
          return (
            <div key={member.id} className="rounded-lg border border-gray-800 bg-gray-900 p-6">
              <div className="mb-4 flex items-center justify-between border-b border-gray-800 pb-4">
                <h3 className="text-lg font-semibold text-white">Discord User: {member.user?.discord_user_id}</h3>
                <div className="flex gap-4">
                  <span className="rounded bg-blue-900/30 px-3 py-1 text-sm font-medium text-blue-400">
                    CP Stars: {member.cp_star_rating}
                  </span>
                  <span className="rounded bg-green-900/30 px-3 py-1 text-sm font-medium text-green-400">
                    DSA Stars: {member.dsa_star_rating}
                  </span>
                </div>
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                {/* CP Breakdown */}
                <div className="rounded bg-gray-950 p-4">
                  <h4 className="mb-3 font-medium text-gray-300">Competitive Programming (CP)</h4>
                  {cpAccounts.length === 0 ? (
                    <p className="text-sm text-gray-500">No linked CP accounts.</p>
                  ) : (
                    <div className="space-y-3">
                      {cpAccounts.map((acc: any) => (
                        <div key={acc.id} className="flex items-center justify-between text-sm">
                          <span className="text-gray-400 capitalize">{acc.platform} ({acc.handle})</span>
                          <span className="font-mono text-white">Rating: {acc.current_rating || "N/A"}</span>
                        </div>
                      ))}
                      <div className="mt-3 border-t border-gray-800 pt-3 text-sm text-gray-400">
                        <p>The system evaluates the highest tier reached across these platforms. For example, Codeforces Newbie (0-1199) is 1 Star, Specialist is 2 Stars, Expert is 3 Stars, etc.</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* DSA Breakdown */}
                <div className="rounded bg-gray-950 p-4">
                  <h4 className="mb-3 font-medium text-gray-300">Data Structures & Algorithms (DSA)</h4>
                  {dsaAccounts.length === 0 ? (
                    <p className="text-sm text-gray-500">No linked DSA accounts.</p>
                  ) : (
                    <div className="space-y-3">
                      {dsaAccounts.map((acc: any) => (
                        <div key={acc.id} className="flex items-center justify-between text-sm">
                          <span className="text-gray-400 capitalize">{acc.platform} ({acc.handle})</span>
                          <span className="font-mono text-white">Rating: {acc.current_rating || "N/A"}</span>
                        </div>
                      ))}
                      <div className="mt-3 border-t border-gray-800 pt-3 text-sm text-gray-400">
                        <p>For LeetCode, typical mapping is: &lt;1600 (1 Star), 1600+ (2 Stars), 1800+ (3 Stars), 2000+ (4 Stars), 2200+ (5 Stars).</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
