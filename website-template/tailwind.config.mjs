/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      // Brand primary color — customize per client
      colors: {
        brand: {
          50: '#f0f4ff',
          100: '#e0e8ff',
          200: '#c7d4fe',
          300: '#a3bdfd',
          400: '#7a9df7',
          500: '#5c7df0',
          600: '#4261e6',
          700: '#3549cc',
          800: '#2d3da8',
          900: '#293a87',
          950: '#1e264a',
        },
      },
      fontFamily: {
        // System font stack for fast loading — replace with client's brand font
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};