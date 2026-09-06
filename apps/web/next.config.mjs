/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output is what the Docker image ships. It requires symlink
  // privileges the Windows/OneDrive dev box often lacks, so it's opt-in:
  // the web Dockerfile sets BUILD_STANDALONE=1.
  output: process.env.BUILD_STANDALONE ? "standalone" : undefined,
  async rewrites() {
    // Browser calls /api/* -> proxied to the API service (keeps cookies same-origin).
    const target = process.env.API_INTERNAL_BASE_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
};
export default nextConfig;
