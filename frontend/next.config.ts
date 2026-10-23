import type { NextConfig } from "next";

const backendUrl = (process.env.BACKEND_URL ?? "http://127.0.0.1:8001").replace(/\/$/, "");

// Hôtes LAN autorisés à charger les ressources de développement (mode --lan).
const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const config: NextConfig = {
  output: "standalone",
  allowedDevOrigins,
  poweredByHeader: false,
  experimental: {
    proxyClientMaxBodySize: "22mb",
    proxyTimeout: 660_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default config;
