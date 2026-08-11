import { createClient } from "@/lib/supabase/server";

export default async function AutoEventsPage({ params }: { params: { guild_id: string } }) {
  const supabase = await createClient();
  
  // Get guild_settings_id
  const { data: guildSetting } = await supabase
    .from("guild_settings")
    .select("id, auto_create_events")
    .eq("discord_guild_id", params.guild_id)
    .single();

  let events = [];
  if (guildSetting) {
    // Get events for the next 7 days
    const now = new Date();
    const nextWeek = new Date();
    nextWeek.setDate(now.getDate() + 7);

    const { data } = await supabase
      .from("events")
      .select(`
        *,
        registrations:event_registrations(count)
      `)
      .eq("guild_settings_id", guildSetting.id)
      .gte("start_time_utc", now.toISOString())
      .lte("start_time_utc", nextWeek.toISOString())
      .order("start_time_utc", { ascending: true });
    
    events = data || [];
  }

  // Create a 7-day calendar array
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date();
    d.setDate(d.getDate() + i);
    days.push(d);
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Weekly Auto-Events</h2>
          <p className="text-gray-400">View upcoming automated events for the next 7 days.</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-gray-800 bg-gray-900 px-4 py-2 text-sm">
          <div className={`h-2 w-2 rounded-full ${guildSetting?.auto_create_events ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span className="text-gray-300">
            Auto-Events: {guildSetting?.auto_create_events ? 'Enabled' : 'Disabled'}
          </span>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-7">
        {days.map((day, idx) => {
          const dayEvents = events.filter((e: any) => {
            const eventDate = new Date(e.start_time_utc);
            return eventDate.getDate() === day.getDate() && eventDate.getMonth() === day.getMonth();
          });

          return (
            <div key={idx} className="flex min-h-[150px] flex-col rounded-lg border border-gray-800 bg-gray-900 p-4">
              <div className="mb-3 text-center">
                <div className="text-sm font-medium text-gray-500">
                  {day.toLocaleDateString('en-US', { weekday: 'short' })}
                </div>
                <div className="text-lg font-bold text-white">
                  {day.getDate()}
                </div>
              </div>
              
              <div className="flex flex-1 flex-col gap-2">
                {dayEvents.map((event: any) => (
                  <div key={event.id} className="rounded bg-gray-950 p-2 text-xs">
                    <div className="mb-1 truncate font-medium text-blue-400" title={event.title}>
                      {event.title}
                    </div>
                    <div className="mb-1 flex items-center justify-between text-gray-500">
                      <span>{new Date(event.start_time_utc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      <span className={`rounded px-1.5 py-0.5 text-[10px] ${
                        event.status === 'published' ? 'bg-green-900/30 text-green-500' : 'bg-gray-800 text-gray-400'
                      }`}>
                        {event.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 text-gray-400">
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                      </svg>
                      {event.registrations?.[0]?.count || 0} registered
                    </div>
                  </div>
                ))}
                
                {dayEvents.length === 0 && (
                  <div className="flex flex-1 items-center justify-center text-xs text-gray-600">
                    No events
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
