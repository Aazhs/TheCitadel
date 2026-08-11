import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";
import { CheckCircle, XCircle } from "lucide-react";

export default async function ModerationPage({ params }: { params: { guild_id: string } }) {
  const supabase = await createClient();
  
  // Get guild_settings_id
  const { data: guildSetting } = await supabase
    .from("guild_settings")
    .select("id")
    .eq("discord_guild_id", params.guild_id)
    .single();

  let submissions = [];
  if (guildSetting) {
    const { data } = await supabase
      .from("event_submissions")
      .select(`
        *,
        event:events(title),
        guild_member:guild_members(user:users(discord_user_id))
      `)
      .eq("verification_status", "pending")
      .order("submitted_at", { ascending: false });
    
    // Manual filtering for guild_settings_id because event_submissions doesn't have it directly,
    // wait, event_submissions is linked to event, which is linked to guild_settings.
    // Or it's linked to guild_member which has guild_settings_id.
    // We can filter using foreign tables but Supabase nested eq can be tricky.
    // Assuming the event_submissions returned all pending globally, let's filter in JS for now or use inner join.
    if (data) {
       // A more precise query would be:
       const { data: preciseData } = await supabase
        .from("event_submissions")
        .select(`
          *,
          event:events!inner(title, guild_settings_id),
          guild_member:guild_members!inner(user:users(discord_user_id))
        `)
        .eq("verification_status", "pending")
        .eq("event.guild_settings_id", guildSetting.id)
        .order("submitted_at", { ascending: false });
        
       submissions = preciseData || [];
    }
  }

  async function approveSubmission(formData: FormData) {
    "use server";
    const id = formData.get("submission_id");
    const adminId = formData.get("admin_id"); // Ideally from session
    
    const sb = await createClient();
    await sb
      .from("event_submissions")
      .update({ 
        verification_status: "approved",
        verified_at: new Date().toISOString(),
        // verified_by_discord_user_id: adminId
      })
      .eq("id", id);
      
    revalidatePath(`/server/${params.guild_id}/moderation`);
  }

  async function rejectSubmission(formData: FormData) {
    "use server";
    const id = formData.get("submission_id");
    const reason = formData.get("reason");
    
    if (!reason || reason.toString().trim() === "") {
        throw new Error("Reason is required for rejection");
    }

    const sb = await createClient();
    await sb
      .from("event_submissions")
      .update({ 
        verification_status: "rejected",
        moderator_note: reason,
        verified_at: new Date().toISOString(),
      })
      .eq("id", id);
      
    revalidatePath(`/server/${params.guild_id}/moderation`);
  }

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold">Moderation Queue</h2>
      <p className="mb-6 text-gray-400">Review pending event submissions.</p>

      {submissions.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-8 text-center text-gray-400">
          No pending submissions. All caught up!
        </div>
      ) : (
        <div className="grid gap-6">
          {submissions.map((sub: any) => (
            <div key={sub.id} className="rounded-lg border border-gray-800 bg-gray-900 p-6">
              <div className="mb-4 flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-white">Event: {sub.event?.title}</h3>
                  <p className="text-sm text-gray-400">
                    User ID: {sub.guild_member?.user?.discord_user_id}
                  </p>
                  <p className="text-sm text-gray-400">
                    Submitted: {new Date(sub.submitted_at).toLocaleString()}
                  </p>
                </div>
                <div className="rounded bg-blue-900/30 px-3 py-1 text-sm font-medium text-blue-400">
                  Solved: {sub.questions_solved}
                </div>
              </div>
              
              <div className="mb-6 grid grid-cols-2 gap-4 rounded bg-gray-950 p-4 text-sm">
                <div>
                  <span className="text-gray-500">Claimed Rank:</span>
                  <span className="ml-2 font-medium">{sub.claimed_rank || "N/A"}</span>
                </div>
                <div>
                  <span className="text-gray-500">Rating Change:</span>
                  <span className="ml-2 font-medium">{sub.claimed_rating_change ? (sub.claimed_rating_change > 0 ? `+${sub.claimed_rating_change}` : sub.claimed_rating_change) : "N/A"}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-gray-500">Evidence URL:</span>
                  {sub.evidence_url ? (
                    <a href={sub.evidence_url} target="_blank" rel="noreferrer" className="ml-2 text-blue-400 hover:underline">
                      {sub.evidence_url}
                    </a>
                  ) : (
                    <span className="ml-2">N/A</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-4 border-t border-gray-800 pt-4">
                <form action={approveSubmission}>
                  <input type="hidden" name="submission_id" value={sub.id} />
                  <button type="submit" className="flex items-center gap-2 rounded bg-green-600 px-4 py-2 text-sm font-semibold hover:bg-green-500">
                    <CheckCircle size={16} /> Approve
                  </button>
                </form>
                
                <form action={rejectSubmission} className="flex flex-1 items-center gap-2">
                  <input type="hidden" name="submission_id" value={sub.id} />
                  <input 
                    type="text" 
                    name="reason" 
                    placeholder="Reason for rejection (required)" 
                    required
                    className="flex-1 rounded border border-gray-700 bg-gray-950 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  />
                  <button type="submit" className="flex items-center gap-2 rounded bg-red-600 px-4 py-2 text-sm font-semibold hover:bg-red-500">
                    <XCircle size={16} /> Reject
                  </button>
                </form>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
