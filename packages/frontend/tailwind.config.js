/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#090d16',
        surface: '#111827',
        'surface-border': '#1f293d',
        accent: '#6366f1',
        'accent-emerald': '#10b981',
        'accent-cyan': '#06b6d4',
      },
    },
  },
  plugins: [],
}
