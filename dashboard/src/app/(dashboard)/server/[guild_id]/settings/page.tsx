import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";

export default async function SettingsPage({ params }: { params: { guild_id: string } }) {
  const supabase = await createClient();
  
  const { data: settings } = await supabase
    .from("guild_settings")
    .select("*")
    .eq("discord_guild_id", params.guild_id)
    .single();

  if (!settings) {
    return <div className="text-red-500">Settings not found for this server.</div>;
  }

  async function updateSettings(formData: FormData) {
    "use server";
    
    const timezone = formData.get("timezone");
    const onboarding_channel_id = formData.get("onboarding_channel_id");
    const announcement_channel_id = formData.get("announcement_channel_id");
    const alert_role_id = formData.get("alert_role_id");
    const reminders_enabled = formData.get("reminders_enabled") === "on";
    const auto_create_events = formData.get("auto_create_events") === "on";

    const sb = await createClient();
    await sb
      .from("guild_settings")
      .update({
        timezone,
        onboarding_channel_id: onboarding_channel_id || null,
        announcement_channel_id: announcement_channel_id || null,
        alert_role_id: alert_role_id || null,
        reminders_enabled,
        auto_create_events
      })
      .eq("discord_guild_id", params.guild_id);
      
    revalidatePath(`/server/${params.guild_id}/settings`);
  }

  return (
    <div className="max-w-2xl">
      <h2 className="mb-6 text-2xl font-bold">Server Settings</h2>
      
      <form action={updateSettings} className="space-y-6 rounded-lg border border-gray-800 bg-gray-900 p-8">
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-300">Timezone</label>
          <input 
            type="text" 
            name="timezone" 
            defaultValue={settings.timezone}
            className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-white focus:border-blue-500 focus:outline-none" 
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Onboarding Channel ID</label>
            <input 
              type="text" 
              name="onboarding_channel_id" 
              defaultValue={settings.onboarding_channel_id || ""}
              className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-white focus:border-blue-500 focus:outline-none" 
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Announcement Channel ID</label>
            <input 
              type="text" 
              name="announcement_channel_id" 
              defaultValue={settings.announcement_channel_id || ""}
              className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-white focus:border-blue-500 focus:outline-none" 
            />
          </div>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-300">Alert Role ID</label>
          <input 
            type="text" 
            name="alert_role_id" 
            defaultValue={settings.alert_role_id || ""}
            className="w-full rounded border border-gray-700 bg-gray-950 px-3 py-2 text-white focus:border-blue-500 focus:outline-none" 
          />
        </div>

        <div className="flex items-center gap-6 border-t border-gray-800 pt-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input 
              type="checkbox" 
              name="reminders_enabled"
              defaultChecked={settings.reminders_enabled}
              className="h-4 w-4 rounded border-gray-700 bg-gray-950 text-blue-600 focus:ring-blue-500" 
            />
            <span className="text-sm font-medium text-gray-300">Enable Reminders</span>
          </label>
          
          <label className="flex items-center gap-2 cursor-pointer">
            <input 
              type="checkbox" 
              name="auto_create_events"
              defaultChecked={settings.auto_create_events}
              className="h-4 w-4 rounded border-gray-700 bg-gray-950 text-blue-600 focus:ring-blue-500" 
            />
            <span className="text-sm font-medium text-gray-300">Auto-create Events</span>
          </label>
        </div>

        <div className="flex justify-end pt-4">
          <button type="submit" className="rounded bg-blue-600 px-6 py-2 text-sm font-semibold hover:bg-blue-500">
            Save Settings
          </button>
        </div>
      </form>
    </div>
  );
}
