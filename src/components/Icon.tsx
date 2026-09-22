/** A small hand-rolled icon set, so nothing here needs an icon dependency. */

export type IconName = keyof typeof PATHS

const PATHS = {
  book: 'M4 4.5A1.5 1.5 0 0 1 5.5 3H19v18H5.5A1.5 1.5 0 0 1 4 19.5Zm0 0A1.5 1.5 0 0 0 5.5 6H19',
  plus: 'M12 5v14M5 12h14',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3',
  sliders: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h10M18 18h2M14 4v4M8 10v4M14 16v4',
  type: 'M4 19 9.5 5h1L16 19M6 14.5h8.5M18 19l2-6 2 6M18.7 17h2.6',
  folder: 'M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h9A1.5 1.5 0 0 1 21 10v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18Z',
  folderPlus:
    'M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h9A1.5 1.5 0 0 1 21 10v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18ZM12 12v5M9.5 14.5h5',
  more: 'M12 6.5h.01M12 12h.01M12 17.5h.01',
  chevronLeft: 'M14.5 6 9 12l5.5 6',
  chevronRight: 'M9.5 6 15 12l-5.5 6',
  chevronDown: 'M6 9.5 12 15l6-5.5',
  x: 'M6 6l12 12M18 6 6 18',
  play: 'M7 4.8v14.4L19.5 12Z',
  pause: 'M9 5v14M15 5v14',
  skipBack: 'M18 5v14L8 12ZM6 5v14',
  skipForward: 'M6 5v14l10-7ZM18 5v14',
  headphones: 'M4 15v-3a8 8 0 0 1 16 0v3M4 14h2.5a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Zm16 0h-2.5a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1H19a1 1 0 0 0 1-1Z',
  bookmark: 'M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1Z',
  highlight: 'M14 4 8 10l-3 6 6-3 6-6ZM4 21h16',
  note: 'M6 3h9l5 5v13H6ZM15 3v5h5M9.5 13h7M9.5 16.5h5',
  list: 'M4 6h2M9 6h11M4 12h2M9 12h11M4 18h2M9 18h11',
  trash: 'M4 7h16M10 7V5h4v2M6.5 7l.8 13h9.4l.8-13M10.5 11v5M13.5 11v5',
  edit: 'M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17ZM14.5 7.5l2 2',
  check: 'M5 12.5 10 17.5 19.5 7',
  cloud: 'M7 18a4 4 0 0 1 .5-8 5.5 5.5 0 0 1 10.6 1.4A3.5 3.5 0 0 1 17.5 18Z',
  cloudOff: 'M7 18a4 4 0 0 1 .5-8M9.5 6.2A5.5 5.5 0 0 1 18.1 11.4 3.5 3.5 0 0 1 17.5 18h-6M4 4l16 16',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20a7 7 0 0 1 14 0',
  logOut: 'M15 4h3.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H15M10 8l-4 4 4 4M6 12h9',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM12 2v2M12 20v2M4.2 4.2l1.5 1.5M18.3 18.3l1.5 1.5M2 12h2M20 12h2M4.2 19.8l1.5-1.5M18.3 5.7l1.5-1.5',
  moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z',
  volume: 'M4 9.5h3L11 6v12l-4-3.5H4ZM15 9.5a3.5 3.5 0 0 1 0 5M17.8 7a7 7 0 0 1 0 10',
  volumeOff: 'M4 9.5h3L11 6v12l-4-3.5H4ZM15.5 10l4 4M19.5 10l-4 4',
  wind: 'M3 8h9a2.5 2.5 0 1 0-2.5-2.5M3 12h13a2.5 2.5 0 1 1-2.5 2.5M3 16h7a2 2 0 1 1-2 2',
  gauge: 'M12 20a8 8 0 1 1 8-8M12 12l4.5-3.5',
  download: 'M12 4v10M8 10.5l4 4 4-4M5 19h14',
  upload: 'M12 15V5M8 8.5 12 4.5l4 4M5 19h14',
  alert: 'M12 8v5M12 16.5h.01M10.3 4.2 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z',
  sparkle: 'M12 3.5 13.7 9l5.3 1.7-5.3 1.7L12 18l-1.7-5.6L5 10.7 10.3 9ZM18.5 16l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8Z',
  inbox: 'M4 13h4l1.5 3h5L16 13h4M4 13 6.5 5h11L20 13v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z',
  refresh: 'M20 12a8 8 0 1 1-2.6-5.9M20 4v4h-4',
  grid: 'M4 4h7v7H4ZM13 4h7v7h-7ZM4 13h7v7H4ZM13 13h7v7h-7Z',
  arrowLeft: 'M5 12h14M11 6l-6 6 6 6',
  install: 'M12 3v10M8.5 9.5 12 13l3.5-3.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4',
} as const

interface IconProps {
  name: IconName
  size?: number
  className?: string
  strokeWidth?: number
  fill?: boolean
}

export function Icon({ name, size = 19, className, strokeWidth = 1.6, fill = false }: IconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}

/** The app mark, used in the header and on the auth screen. */
export function Mark({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="cozy-plate" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1d1815" />
          <stop offset="1" stopColor="#342821" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="url(#cozy-plate)" />
      <path d="M10 24 31.2 20.8 31.2 47 10 43.2Z" fill="#f0e3cd" />
      <path d="M54 24 32.8 20.8 32.8 47 54 43.2Z" fill="#e2d1b6" />
      <path d="M30.2 21h3.6v33l-1.8-4.4-1.8 4.4Z" fill="#d68a4a" />
    </svg>
  )
}
