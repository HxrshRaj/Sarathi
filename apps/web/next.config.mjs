/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output is what the Docker image ships. It requires symlink
  // privileges the Windows/OneDrive dev box often lacks, so it's opt-in:
  // the web Dockerfile sets BUILD_STANDALONE=1.
  output: process.env.BUILD_STANDALONE ? "standalone" : undefined,
  async rewrites() {
    // Browser calls /api/* -> proxied to the API service (keeps cookies same-origin).
    // Only when a target is configured. On a split-origin deploy (Vercel front /
    // Render API) it's unset: the client talks to NEXT_PUBLIC_API_BASE_URL
    // directly, and proxying to localhost:8000 would 404 (DNS_HOSTNAME_RESOLVED_PRIVATE).
    const target = process.env.API_INTERNAL_BASE_URL;
    if (!target) return [];
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
};
export default nextConfig;
