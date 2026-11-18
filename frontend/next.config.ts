import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: process.env.NODE_ENV === "production" ? "standalone" : undefined,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        // Los agentes Windows usan el mismo dominio que el panel (APP_ORIGIN), asi
        // el backend no necesita dominio publico propio. Las peticiones van firmadas
        // con Ed25519 sobre metodo, ruta, consulta y cuerpo, que el proxy no altera.
        source: "/agent/v1/:path*",
        destination: `${backendUrl}/agent/v1/:path*`,
      },
    ];
  },
  experimental: {
    // El agente espera hasta 25 s un comando (long-poll); el limite de 30 s por
    // defecto del proxy queda demasiado justo.
    proxyTimeout: 60_000,
  },
  turbopack: {
    root: process.cwd(),
  },
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
    ],
  },
};

export default nextConfig;
