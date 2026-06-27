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
        surface: {
          950: "#ffffff",
          900: "#fbfcfd",
          850: "#f7f8fa",
          800: "#eef1f4",
          700: "#dfe3e8"
        },
        ink: {
          50: "#32394a",
          200: "#4c5568",
          400: "#6f7787",
          500: "#8b93a3"
        },
        gain: "#00a889",
        loss: "#d35b4f",
        warn: "#c7a45d"
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "JetBrains Mono", "ui-monospace", "monospace"]
      },
      boxShadow: {
        panel: "inset 0 1px 0 rgba(255,255,255,0.02)"
      }
    }
  },
  plugins: []
};

export default config;
