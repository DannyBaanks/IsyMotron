import { timingSafeEqual } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";

function visitorKeyMatches(request: NextRequest, expected: string): boolean {
  const header = request.headers.get("authorization") ?? "";
  const supplied = header.startsWith("Bearer ") ? header.slice(7) : "";
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function GET(request: NextRequest) {
  const backend = process.env.ISYMOTRON_BACKEND_URL ?? "http://127.0.0.1:8760";
  const token = process.env.ISYMOTRON_SESSION_TOKEN;
  if (!token) {
    return NextResponse.json({ connected: false, reason: "missing session token" });
  }

  // The backend session token never leaves this server. Visitors prove
  // themselves with a separate key; without one configured we fail closed.
  const visitorKey = process.env.ISYMOTRON_DASHBOARD_TOKEN;
  if (!visitorKey) {
    return NextResponse.json({ connected: false, reason: "dashboard key not configured" }, { status: 503 });
  }
  if (!visitorKeyMatches(request, visitorKey)) {
    return NextResponse.json({ connected: false, reason: "visitor key required" }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }

  try {
    const response = await fetch(`${backend}/api/state`, {
      headers: { "X-IsyMotron-Token": token },
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json({ connected: false, reason: `backend ${response.status}` }, { status: 502 });
    }
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ connected: false, reason: "backend unavailable" }, { status: 502 });
  }
}
