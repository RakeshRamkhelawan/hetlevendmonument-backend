/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        heritage: {
          50: "#fbf9f5",
          100: "#f5f0e8",
          200: "#ebdccb",
          300: "#dec2a7",
          400: "#cea281",
          500: "#bf8461",
          600: "#b06f52",
          700: "#925743",
          800: "#77473a",
          900: "#613c32",
          950: "#341e1a",
        },
      },
      fontFamily: {
        sans: ["DM Sans Variable", "DM Sans", "sans-serif"],
        serif: ["Playfair Display Variable", "Playfair Display", "serif"],
      },
    },
  },
  plugins: [],
};
