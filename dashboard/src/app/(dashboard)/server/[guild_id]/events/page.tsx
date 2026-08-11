import { createClient } from "@/lib/supabase/server";

export default async function EventsPage({ params }: { params: { guild_id: string } }) {
  const supabase = await createClient();
  
  // Get guild_settings_id
  const { data: guildSetting } = await supabase
    .from("guild_settings")
    .select("id")
    .eq("discord_guild_id", params.guild_id)
    .single();

  let events = [];
  if (guildSetting) {
    const { data } = await supabase
      .from("events")
      .select("*")
      .eq("guild_settings_id", guildSetting.id)
      .order("start_time_utc", { ascending: true });
    
    events = data || [];
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold">Events</h2>
        <button className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500">
          Create Event
        </button>
      </div>

      {events.length === 0 ? (
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-8 text-center text-gray-400">
          No events found for this server.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-800 bg-gray-900">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-800/50 text-xs uppercase text-gray-400">
              <tr>
                <th className="px-6 py-4">Title</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Platform</th>
                <th className="px-6 py-4">Start Time</th>
                <th className="px-6 py-4">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {events.map((event: any) => (
                <tr key={event.id} className="hover:bg-gray-800/50">
                  <td className="px-6 py-4 font-medium text-white">{event.title}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
                      event.status === 'published' ? 'bg-green-500/10 text-green-500' :
                      event.status === 'draft' ? 'bg-gray-500/10 text-gray-400' :
                      'bg-red-500/10 text-red-500'
                    }`}>
                      {event.status}
                    </span>
                  </td>
                  <td className="px-6 py-4">{event.platform || "Custom"}</td>
                  <td className="px-6 py-4">{new Date(event.start_time_utc).toLocaleString()}</td>
                  <td className="px-6 py-4">
                    <button className="text-blue-400 hover:text-blue-300">Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
