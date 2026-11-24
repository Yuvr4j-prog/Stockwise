import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL?.replace(/\/$/, "");

if (process.env.RENDER === "true" && !backendUrl) {
  throw new Error("BACKEND_URL must be set when building the StockWise web service on Render.");
}

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: { root: process.cwd() },
  async rewrites() {
    if (!backendUrl) return [];
    return [{ source: "/api/v1/:path*", destination: `${backendUrl}/api/v1/:path*` }];
  },
};

export default nextConfig;
