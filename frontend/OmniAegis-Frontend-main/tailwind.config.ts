import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      /* ====== COLORS ====== */
      colors: {
        /* Primary Surfaces */
        surface: {
          primary: 'rgb(var(--color-bg-primary-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--color-bg-secondary-rgb) / <alpha-value>)',
          tertiary: 'rgb(var(--color-bg-tertiary-rgb) / <alpha-value>)',
          elevated: 'rgb(var(--color-bg-elevated-rgb) / <alpha-value>)',
        },
        /* Brand Accent */
        accent: {
          DEFAULT: 'rgb(var(--color-accent-rgb) / <alpha-value>)',
          hover: '#7B74FF',
          muted: '#6C63FF22',
          glow: '#6C63FF44',
        },
        /* Semantic Status */
        status: {
          success: '#22D3A0',
          warning: '#F5A623',
          danger: '#FF4D6A',
          neutral: '#8B93B0',
        },
        /* Borders */
        border: {
          DEFAULT: 'rgb(var(--color-border-default-rgb) / <alpha-value>)',
          strong: 'rgb(var(--color-border-strong-rgb) / <alpha-value>)',
          subtle: 'rgb(var(--color-border-subtle-rgb) / 0.05)',
          standard: 'rgb(var(--color-border-standard-rgb) / 0.08)',
        },
        /* Text */
        text: {
          primary: 'rgb(var(--color-text-primary-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--color-text-secondary-rgb) / <alpha-value>)',
          tertiary: 'rgb(var(--color-text-tertiary-rgb) / <alpha-value>)',
          disabled: 'rgb(var(--color-text-disabled-rgb) / <alpha-value>)',
        },
      },

      /* ====== TYPOGRAPHY ====== */
      fontFamily: {
        sans: ['Inter', 'Geist', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '1rem' }],
        'xs': ['0.75rem', { lineHeight: '1.4' }],
        'sm': ['0.8125rem', { lineHeight: '1.6' }],
        'base': ['0.9375rem', { lineHeight: '1.5' }],
        'md': ['1.0625rem', { lineHeight: '1.6' }],
        'lg': ['1.25rem', { lineHeight: '1.3' }],
        'xl': ['1.5rem', { lineHeight: '1.25' }],
        '2xl': ['2rem', { lineHeight: '1.2' }],
      },
      fontWeight: {
        normal: '400',
        medium: '500',
        semibold: '600',
        bold: '700',
      },
      letterSpacing: {
        tight: '-0.02em',
        normal: '0em',
        wide: '0.06em',
      },

      /* ====== SPACING ====== */
      spacing: {
        1: '4px',
        2: '8px',
        3: '12px',
        4: '16px',
        5: '20px',
        6: '24px',
        8: '32px',
        10: '40px',
        12: '48px',
        16: '64px',
        20: '80px',
      },

      /* ====== BORDER RADIUS ====== */
      borderRadius: {
        sm: '4px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        full: '9999px',
      },

      /* ====== SHADOWS ====== */
      boxShadow: {
        sm: '0 1px 3px rgba(0, 0, 0, 0.4)',
        md: '0 4px 16px rgba(0, 0, 0, 0.5)',
        lg: '0 12px 40px rgba(0, 0, 0, 0.6)',
        glow: '0 0 0 2px #6C63FF44',
        inset: 'rgba(0, 0, 0, 0.2) 0px 0px 12px inset',
      },

      /* ====== TRANSITION & ANIMATION ====== */
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.34, 1.56, 0.64, 1.0)',
      },
      transitionDuration: {
        fast: '100ms',
        normal: '200ms',
        slow: '350ms',
        crawl: '600ms',
      },

      /* ====== Z-INDEX ====== */
      zIndex: {
        base: '0',
        dropdown: '50',
        sticky: '20',
        fixed: '30',
        'modal-backdrop': '40',
        modal: '50',
        popover: '75',
        tooltip: '100',
        notification: '110',
      },

      /* ====== WIDTH & HEIGHT ====== */
      width: {
        sidebar: '240px',
        'sidebar-collapsed': '64px',
        'context-panel': '380px',
      },
      height: {
        'top-nav': '56px',
      },

      /* ====== MAX-WIDTH ====== */
      maxWidth: {
        container: '1440px',
      },
    },
  },
  plugins: [],
};

export default config;