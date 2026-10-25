const v = (name) => `var(--${name})`

// Every value resolves through the CSS variables in src/index.css, so the resident (day/night)
// and staff themes share these names. Components use these tokens, never raw colours.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      borderColor: { DEFAULT: v('line') },
      fontFamily: { sans: [v('font-sans')] },
      colors: {
        bg: v('bg'),
        surface: v('surface'),
        'surface-2': v('surface-2'),
        ink: v('ink'),
        'ink-soft': v('ink-soft'),
        line: v('line'),
        primary: v('primary'),
        'primary-ink': v('primary-ink'),
        'primary-soft': v('primary-soft'),
        ok: v('ok'),
        'ok-soft': v('ok-soft'),
        lock: v('lock'),
        'lock-soft': v('lock-soft'),
        notice: v('notice'),
        'notice-soft': v('notice-soft'),
        danger: v('danger'),
        'danger-soft': v('danger-soft'),
      },
      fontSize: {
        sm: [v('fs-sm'), '1.4'],
        body: [v('fs-body'), '1.45'],
        label: [v('fs-label'), '1.3'],
        h3: [v('fs-h3'), '1.25'],
        h2: [v('fs-h2'), '1.2'],
        h1: [v('fs-h1'), '1.15'],
        display: [v('fs-display'), '1.05'],
      },
      minHeight: { touch: v('touch') },
      minWidth: { touch: v('touch') },
      borderRadius: { card: v('r-card'), ctl: v('r-ctl') },
      boxShadow: { card: v('shadow-card') },
    },
  },
  plugins: [],
}
