/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  basePath: "/mini-app",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};

export default nextConfig;
