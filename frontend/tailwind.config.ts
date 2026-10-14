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
        "on-accent": "rgb(var(--color-on-accent) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        inset: "rgb(var(--color-inset) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        subtle: "rgb(var(--color-subtle) / <alpha-value>)",
        success: "rgb(var(--color-success) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",

        musgo: "rgb(var(--color-musgo) / <alpha-value>)",
        arcilla: "rgb(var(--color-arcilla) / <alpha-value>)",
        crema: "rgb(var(--color-crema) / <alpha-value>)",
        carbon: "rgb(var(--color-carbon) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Segoe UI", "Arial", "sans-serif"],
        display: ["Georgia", "Times New Roman", "serif"],
        title: ["Segoe UI", "Arial", "sans-serif"],
        mono: ["Cascadia Code", "Consolas", "Courier New", "monospace"],
      },
      borderRadius: {
        pill: "2rem",
        "pill-lg": "3rem",
      },
      transitionTimingFunction: {
        "power3-out": "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      animation: {
        "pulse-dot": "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
