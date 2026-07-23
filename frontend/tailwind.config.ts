import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#e11d74",
          light: "#fbcfe8",
          dark: "#9d174d",
        },
      },
    },
  },
  plugins: [],
};

export default config;
