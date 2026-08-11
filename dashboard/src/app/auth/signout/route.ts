import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const requestUrl = new URL(request.url);
  const cookieStore = require("next/headers").cookies();
  
  const supabase = createServerClient(
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

  await supabase.auth.signOut();

  return NextResponse.redirect(new URL("/login", requestUrl.origin), {
    status: 301,
  });
}
