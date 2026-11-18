import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/hooks/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        musgo: "rgb(var(--color-musgo) / <alpha-value>)",
        arcilla: "rgb(var(--color-arcilla) / <alpha-value>)",
        crema: "rgb(var(--color-crema) / <alpha-value>)",
        carbon: "rgb(var(--color-carbon) / <alpha-value>)",
        tinta: "rgb(var(--color-tinta) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "Segoe UI", "sans-serif"],
        display: ["var(--font-inter)", "Inter", "Segoe UI", "sans-serif"],
        title: ["var(--font-inter)", "Inter", "Segoe UI", "sans-serif"],
        mono: ["Cascadia Code", "Consolas", "Courier New", "monospace"],
      },
      borderRadius: {
        pill: "2rem",
        "pill-lg": "3rem",
      },
      transitionTimingFunction: {
        "power3-out": "cubic-bezier(0.22, 1, 0.36, 1)",
        "out-strong": "cubic-bezier(0.23, 1, 0.32, 1)",
      },
      animation: {
        "pulse-dot": "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
