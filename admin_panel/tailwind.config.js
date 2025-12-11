/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#5B21B6',   // deep purple
        accent: '#F97316',    // orange
        ocean: '#0EA5E9',     // blue
        dark: '#020617',
      },
    },
  },
  plugins: [],
};
