/** @type {import('tailwindcss').Config} */
// Cordillera highland palette: pine green through to highland gold, on a
// cool mist background. "uc-green" is the primary institutional green.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        "uc-green": "#15803d",
        "uc-green-dark": "#14532d",
        "uc-green-light": "#86efac",
        "uc-gold": "#d9a441",
        "uc-mist": "#f1f6f2",
      },
    },
  },
  plugins: [],
};
