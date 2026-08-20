import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        border: "#E5E7EB",
        foreground: "#0A0A0A",
        muted: "#6B7280",
        subtle: "#9CA3AF",
        surface: "#F8FAFC",
        accent: "#F97316",
        "accent-soft": "#FFF7ED",
        risk: {
          low: "#16A34A",
          moderate: "#EAB308",
          high: "#F97316",
          severe: "#DC2626"
        }
      },
      fontFamily: {
        sans: ["Geist Sans", "Satoshi", "Avenir Next", "Helvetica Neue", "Arial", "sans-serif"]
      },
      boxShadow: {
        preview: "0 24px 80px rgba(15,23,42,0.08)",
        card: "0 1px 2px rgba(0,0,0,0.04)"
      }
    }
  },
  plugins: []
};

export default config;
