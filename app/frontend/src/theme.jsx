// App-wide dark-mode context. Toggles `class="dark"` on <html> and persists to localStorage.
import { createContext, useContext, useEffect, useState, useCallback } from 'react'

const KEY = 'ff_theme' // 'light' | 'dark'
const ThemeCtx = createContext({ dark: false, toggle: () => {} })

function initialDark() {
  const saved = localStorage.getItem(KEY)
  // Only follow the stored preference; don't inherit OS dark mode on first visit.
  // The mockups are light-first — Explore and Chat use white/grey-wash surfaces.
  return saved === 'dark'
}

export function ThemeProvider({ children }) {
  const [dark, setDark] = useState(initialDark)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem(KEY, dark ? 'dark' : 'light')
  }, [dark])

  // Animated circle-reveal toggle (from the Landing mockup). Falls back to an
  // instant flip if no click coordinates are supplied.
  const toggle = useCallback((e) => {
    const next = !dark
    const x = e?.clientX, y = e?.clientY
    if (x == null || y == null) { setDark(next); return }

    const ov = document.createElement('div')
    Object.assign(ov.style, {
      position: 'fixed', inset: '0', zIndex: '99999',
      background: next ? '#0a0a0a' : '#176dcc',
      clipPath: `circle(0px at ${x}px ${y}px)`,
      transition: 'clip-path .6s cubic-bezier(.4,0,.2,1)', pointerEvents: 'none',
    })
    document.body.appendChild(ov)
    const max = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + 40
    requestAnimationFrame(() => { ov.style.clipPath = `circle(${max}px at ${x}px ${y}px)` })
    setTimeout(() => {
      setDark(next)
      requestAnimationFrame(() => {
        ov.style.transition = 'opacity .3s ease'
        ov.style.opacity = '0'
        setTimeout(() => ov.remove(), 320)
      })
    }, 610)
  }, [dark])

  return <ThemeCtx.Provider value={{ dark, toggle }}>{children}</ThemeCtx.Provider>
}

export const useTheme = () => useContext(ThemeCtx)
