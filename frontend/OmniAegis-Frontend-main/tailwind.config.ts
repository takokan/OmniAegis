import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: '#1e40af',
          soft: '#3b82f6'
        }
      },
      boxShadow: {
        soft: '0 24px 80px rgba(15, 23, 42, 0.08)'
      },
      backgroundImage: {
        'top-glow': 'radial-gradient(circle at top, rgba(59, 130, 246, 0.12), transparent 42%)'
      }
    }
  },
  plugins: []
};

export default config;