import type { NextConfig } from "next";

const backendUrl = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  experimental: {
    proxyClientMaxBodySize: "22mb",
    proxyTimeout: 300_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default config;
