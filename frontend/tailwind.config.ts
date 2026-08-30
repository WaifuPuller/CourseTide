import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#1A0706",
        foreground: "#F3EEE8",
        burgundy: {
          dark: "#1A0706",
          surface: "#2A0B09",
          panel: "#3D0E0B",
          card: "#260A08",
          DEFAULT: "#55100D",
          border: "#55100D",
          light: "#771714",
        },
        tide: {
          red: "#DD0200",
          redHover: "#BF0200",
          gray: "#D9D9D9",
          grayMuted: "#8C8380",
          cream: "#F3EEE8",
        },
      },
    },
  },
  plugins: [],
};

export default config;
