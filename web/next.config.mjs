/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The dashboard talks to the agent service for actions and to Supabase
  // (Realtime + reads) directly from the browser.
};

export default nextConfig;
