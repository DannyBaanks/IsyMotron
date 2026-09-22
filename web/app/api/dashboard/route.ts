import { NextResponse } from "next/server";

export async function GET() {
  const backend = process.env.ISYMOTRON_BACKEND_URL ?? "http://127.0.0.1:8760";
  const token = process.env.ISYMOTRON_SESSION_TOKEN;
  if (!token) {
    return NextResponse.json({ connected: false, reason: "missing session token" });
  }

  try {
    const response = await fetch(`${backend}/api/state`, {
      headers: { "X-IsyMotron-Token": token },
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json({ connected: false, reason: `backend ${response.status}` }, { status: 502 });
    }
    return NextResponse.json(await response.json());
  } catch {
    return NextResponse.json({ connected: false, reason: "backend unavailable" }, { status: 502 });
  }
}
