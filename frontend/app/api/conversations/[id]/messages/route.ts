import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8001").replace(/\/$/, "");

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const targetUrl = `${BACKEND_URL}/api/conversations/${encodeURIComponent(id)}/messages`;

  const forwardHeaders = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower !== "host" && lower !== "connection" && lower !== "content-length") {
      forwardHeaders.set(key, value);
    }
  });

  forwardHeaders.set("Accept", "text/event-stream");

  const ip = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (ip) {
    forwardHeaders.set("x-forwarded-for", ip);
  }

  const body = await request.text();

  const upstreamRes = await fetch(targetUrl, {
    method: "POST",
    headers: forwardHeaders,
    body,
    cache: "no-store",
    signal: request.signal,
  });

  if (!upstreamRes.ok || !upstreamRes.body) {
    const errorBody = await upstreamRes.text();
    return new Response(errorBody, {
      status: upstreamRes.status,
      statusText: upstreamRes.statusText,
      headers: {
        "Content-Type": upstreamRes.headers.get("content-type") ?? "application/json",
      },
    });
  }

  const responseHeaders = new Headers();
  responseHeaders.set("Content-Type", "text/event-stream; charset=utf-8");
  responseHeaders.set("Cache-Control", "no-cache, no-transform");
  responseHeaders.set("Connection", "keep-alive");
  responseHeaders.set("X-Accel-Buffering", "no");

  const setCookie = upstreamRes.headers.get("set-cookie");
  if (setCookie) {
    responseHeaders.set("Set-Cookie", setCookie);
  }

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    headers: responseHeaders,
  });
}

