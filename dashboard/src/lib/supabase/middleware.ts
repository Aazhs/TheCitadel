import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!, // Use service role to check db tables
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({
            request,
          });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // IMPORTANT: Avoid writing any logic between createServerClient and
  // supabase.auth.getUser(). A simple mistake could make it very hard to debug
  // issues with users being randomly logged out.

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const isAuthRoute = request.nextUrl.pathname.startsWith("/login") || request.nextUrl.pathname.startsWith("/auth/callback");

  if (!user && !isAuthRoute) {
    // no user, potentially respond by redirecting the user to the login page
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  if (user && isAuthRoute && request.nextUrl.pathname !== "/auth/callback") {
      // If user is logged in, redirect to home unless it's the callback
      const url = request.nextUrl.clone();
      url.pathname = "/";
      return NextResponse.redirect(url);
  }

  // If user is logged in and trying to access a guild specific route,
  // we could verify they are an admin for that guild here or in the layout.
  // For simplicity and speed, we will do route protection here.
  
  if (user && request.nextUrl.pathname.startsWith("/server/")) {
      const parts = request.nextUrl.pathname.split("/");
      if (parts.length >= 3) {
          const guildId = parts[2]; // /server/[guild_id]/...
          
          // Check if user is an admin for this guild
          // The Discord OAuth provider stores the discord id in user.user_metadata.provider_id
          const discordId = user.user_metadata?.provider_id || user.identities?.[0]?.identity_data?.provider_id;
          
          if (discordId) {
              const { data: adminData } = await supabase
                  .from("guild_admins")
                  .select("guild_settings_id, guild_settings!inner(discord_guild_id)")
                  .eq("discord_user_id", discordId)
                  .eq("guild_settings.discord_guild_id", guildId)
                  .single();
                  
              if (!adminData) {
                  // Not an admin for this guild
                  const url = request.nextUrl.clone();
                  url.pathname = "/"; // redirect to server selection
                  return NextResponse.redirect(url);
              }
          }
      }
  }

  return supabaseResponse;
}
