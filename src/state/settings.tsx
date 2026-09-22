import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { ReadingFont, Settings, ThemeName } from '../lib/types'

const KEY = 'cozypdf.settings'

export const DEFAULT_SETTINGS: Settings = {
  theme: 'system',
  font: 'literata',
  fontSize: 19,
  lineHeight: 1.62,
  measure: 66,
  margin: 24,
  paragraphSpacing: 0.85,
  justify: false,
  mode: 'scroll',
  voiceURI: null,
  rate: 1,
  pitch: 1,
  ttsVolume: 1,
  ambience: 'none',
  ambienceVolume: 0.3,
  highlightColor: 'butter',
  keepAwake: true,
  reduceMotion: false,
}

export const FONTS: { id: ReadingFont; name: string; stack: string; note: string }[] = [
  { id: 'literata', name: 'Literata', stack: '"Literata", Georgia, serif', note: 'Made for screens' },
  { id: 'lora', name: 'Lora', stack: '"Lora", Georgia, serif', note: 'Bookish, warm' },
  { id: 'fraunces', name: 'Fraunces', stack: '"Fraunces", Georgia, serif', note: 'Characterful' },
  { id: 'inter', name: 'Inter', stack: '"Inter", system-ui, sans-serif', note: 'Clean sans' },
  {
    id: 'hyperlegible',
    name: 'Hyperlegible',
    stack: '"Atkinson Hyperlegible", system-ui, sans-serif',
    note: 'Highest legibility',
  },
]

const THEME_COLORS: Record<Exclude<ThemeName, 'system'>, string> = {
  light: '#faf7f2',
  sepia: '#f4ecdc',
  dark: '#14110f',
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<Settings>
    return { ...DEFAULT_SETTINGS, ...parsed }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function resolveTheme(theme: ThemeName): Exclude<ThemeName, 'system'> {
  if (theme !== 'system') return theme
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

interface SettingsContextValue {
  settings: Settings
  resolvedTheme: Exclude<ThemeName, 'system'>
  set: <K extends keyof Settings>(key: K, value: Settings[K]) => void
  update: (patch: Partial<Settings>) => void
  reset: () => void
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(load)
  const [systemDark, setSystemDark] = useState(
    () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches,
  )

  useEffect(() => {
    const media = matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const resolvedTheme =
    settings.theme === 'system' ? (systemDark ? 'dark' : 'light') : settings.theme

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(settings))
    } catch {
      /* storage full or blocked; settings simply will not persist */
    }
  }, [settings])

  // Push the reading preferences into CSS so layout stays declarative.
  useEffect(() => {
    const root = document.documentElement
    const font = FONTS.find((f) => f.id === settings.font) ?? FONTS[0]
    root.dataset.theme = resolvedTheme
    root.style.setProperty('--reading-font', font.stack)
    root.style.setProperty('--reading-size', `${settings.fontSize}px`)
    root.style.setProperty('--reading-leading', String(settings.lineHeight))
    root.style.setProperty('--reading-measure', `${settings.measure}ch`)
    root.style.setProperty('--reading-margin', `${settings.margin}px`)
    root.style.setProperty('--para-space', `${settings.paragraphSpacing}em`)
    root.style.setProperty('--reading-align', settings.justify ? 'justify' : 'start')
    root.dataset.motion = settings.reduceMotion ? 'reduced' : 'full'

    document
      .querySelectorAll('meta[name="theme-color"]')
      .forEach((meta) => meta.setAttribute('content', THEME_COLORS[resolvedTheme]))
  }, [settings, resolvedTheme])

  const set = useCallback(<K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((current) => (current[key] === value ? current : { ...current, [key]: value }))
  }, [])

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((current) => ({ ...current, ...patch }))
  }, [])

  const reset = useCallback(() => setSettings({ ...DEFAULT_SETTINGS }), [])

  const value = useMemo(
    () => ({ settings, resolvedTheme, set, update, reset }),
    [settings, resolvedTheme, set, update, reset],
  )

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
  const context = useContext(SettingsContext)
  if (!context) throw new Error('useSettings must be used inside SettingsProvider')
  return context
}
