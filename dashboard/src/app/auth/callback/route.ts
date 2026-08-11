import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const next = requestUrl.searchParams.get("next") ?? "/";

  if (code) {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!,
      {
        cookies: {
          getAll() {
            return []; // We don't need to read cookies to exchange the code
          },
          setAll() {
            // we will let the middleware handle setting the session cookies
          },
        },
      }
    );
    
    // We actually need a real client to exchange code that can set cookies.
    // Let's re-create a proper client for the route handler.
    const cookieStore = require("next/headers").cookies();
    const routeSupabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet: any[]) {
            try {
              cookiesToSet.forEach(({ name, value, options }) => {
                cookieStore.set(name, value, options);
              });
            } catch (error) {
              // Ignore
            }
          },
        },
      }
    );
    
    await routeSupabase.auth.exchangeCodeForSession(code);
  }

  // URL to redirect to after sign in process completes
  return NextResponse.redirect(new URL(next, request.url));
}
