import type { NextConfig } from "next";

const backendUrl = (process.env.BACKEND_URL ?? "http://127.0.0.1:8001").replace(/\/$/, "");

// Hôtes LAN autorisés à charger les ressources de développement (mode --lan ou réseau local).
const customDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const allowedDevOrigins = Array.from(
  new Set([
    "localhost",
    "127.0.0.1",
    "192.168.*",
    "10.*",
    "172.16.*",
    "*.local",
    ...customDevOrigins,
  ])
);

const config: NextConfig = {
  output: "standalone",
  allowedDevOrigins,
  poweredByHeader: false,
  experimental: {
    proxyClientMaxBodySize: "45mb",
    proxyTimeout: 660_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default config;
