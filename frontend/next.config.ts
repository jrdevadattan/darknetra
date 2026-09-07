import type { NextConfig } from "next";

const backendBaseUrl = process.env.DARKNETRA_API_BASE_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  experimental: { optimizePackageImports: ["@chakra-ui/react"] },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendBaseUrl}/api/:path*` }];
  },
};

export default nextConfig;
