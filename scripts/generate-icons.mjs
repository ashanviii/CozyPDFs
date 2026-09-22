/**
 * Generates cozypdf's PWA icons with a tiny dependency-free PNG encoder.
 * Run with `npm run icons` (the build does it automatically).
 */
import { deflateSync } from 'node:zlib'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons')

/* ---------------------------------------------------------------- png ---- */

const CRC_TABLE = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()

function crc32(buf) {
  let c = -1
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ -1) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'latin1'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

function encodePng(width, height, rgba) {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // truecolour with alpha
  const raw = Buffer.alloc((width * 4 + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0 // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4)
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

/* ------------------------------------------------------------- drawing ---- */

const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t)

const INK_TOP = [29, 24, 21]
const INK_BOTTOM = [52, 40, 33]
const PAPER = [244, 233, 215]
const PAPER_SHADE = [223, 205, 179]
const EMBER = [214, 138, 74]

function inPolygon(pts, x, y) {
  let inside = false
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i]
    const [xj, yj] = pts[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

/** Signed "inside" test for a rounded rectangle in normalised coords. */
function inRoundRect(x, y, x0, y0, x1, y1, r) {
  const cx = Math.min(Math.max(x, x0 + r), x1 - r)
  const cy = Math.min(Math.max(y, y0 + r), y1 - r)
  if (x < x0 || x > x1 || y < y0 || y > y1) return false
  return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
}

/** The artwork, sampled in normalised [0,1] space. Returns [r,g,b,a 0-255]. */
function sample(u, v, { maskable }) {
  const pad = maskable ? 0.14 : 0 // keep the mark inside the safe zone
  const radius = maskable ? 0 : 0.225

  // Background plate.
  const onPlate = maskable || inRoundRect(u, v, 0, 0, 1, 1, radius)
  if (!onPlate) return [0, 0, 0, 0]
  let col = mix(INK_TOP, INK_BOTTOM, Math.min(1, v * 1.15))

  // A warm glow in the upper third, like lamplight on a page.
  const gd = Math.hypot((u - 0.5) * 1.1, v - 0.3)
  col = mix(col, [63, 47, 38], Math.max(0, 1 - gd * 2.2) * 0.75)

  // Geometry of the open book, squeezed into the safe area when maskable.
  const s = 1 - pad * 2
  const U = (n) => 0.5 + (n - 0.5) * s
  const V = (n) => 0.5 + (n - 0.5) * s

  const left = [
    [U(0.155), V(0.375)],
    [U(0.487), V(0.325)],
    [U(0.487), V(0.735)],
    [U(0.155), V(0.675)],
  ]
  const right = [
    [U(0.513), V(0.325)],
    [U(0.845), V(0.375)],
    [U(0.845), V(0.675)],
    [U(0.513), V(0.735)],
  ]

  // Soft drop shadow under the pages.
  const shadow = [
    [U(0.155), V(0.66)],
    [U(0.845), V(0.66)],
    [U(0.845), V(0.775)],
    [U(0.155), V(0.775)],
  ]
  if (inPolygon(shadow, u, v)) {
    const t = (V(0.775) - v) / (V(0.775) - V(0.66))
    col = mix(col, [12, 9, 8], Math.max(0, t) * 0.5)
  }

  const onLeft = inPolygon(left, u, v)
  const onRight = inPolygon(right, u, v)
  if (onLeft || onRight) {
    // Pages, with a gentle gutter shading toward the spine.
    const distToSpine = Math.abs(u - 0.5) / (0.33 * s)
    col = mix(PAPER_SHADE, PAPER, Math.min(1, distToSpine * 2.4))

    // Ruled lines standing in for text.
    const top = onLeft ? V(0.375) + (V(0.325) - V(0.375)) * ((u - U(0.155)) / (0.332 * s)) : V(0.325) + (V(0.375) - V(0.325)) * ((u - U(0.513)) / (0.332 * s))
    const rel = (v - top) / (0.36 * s)
    for (const line of [0.2, 0.42, 0.64]) {
      if (Math.abs(rel - line) < 0.035) {
        const edge = onLeft ? (u - U(0.19)) / (0.26 * s) : (U(0.81) - u) / (0.26 * s)
        if (edge > 0 && edge < 1) col = mix(col, [150, 128, 104], 0.75)
      }
    }
  }

  // A ribbon bookmark falling from the spine.
  const ribbon = [
    [U(0.472), V(0.33)],
    [U(0.528), V(0.33)],
    [U(0.528), V(0.86)],
    [U(0.5), V(0.79)],
    [U(0.472), V(0.86)],
  ]
  if (inPolygon(ribbon, u, v) && v > V(0.66)) col = mix(EMBER, [176, 100, 48], (v - V(0.66)) / (0.2 * s))
  else if (inPolygon(ribbon, u, v)) col = mix(col, [0, 0, 0], 0.35)

  return [...col.map((c) => Math.round(Math.max(0, Math.min(255, c)))), 255]
}

function render(size, opts) {
  const SS = 3 // supersampling factor
  const buf = Buffer.alloc(size * size * 4)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0, a = 0
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const [pr, pg, pb, pa] = sample((x + (sx + 0.5) / SS) / size, (y + (sy + 0.5) / SS) / size, opts)
          const w = pa / 255
          r += pr * w; g += pg * w; b += pb * w; a += pa
        }
      }
      const n = SS * SS
      const aw = a / 255 || 1
      const i = (y * size + x) * 4
      buf[i] = Math.round(r / aw)
      buf[i + 1] = Math.round(g / aw)
      buf[i + 2] = Math.round(b / aw)
      buf[i + 3] = Math.round(a / n)
    }
  }
  return encodePng(size, size, buf)
}

/* ---------------------------------------------------------------- main ---- */

mkdirSync(OUT, { recursive: true })
const jobs = [
  ['icon-192.png', 192, { maskable: false }],
  ['icon-512.png', 512, { maskable: false }],
  ['maskable-512.png', 512, { maskable: true }],
  ['apple-touch-icon.png', 180, { maskable: false }],
  ['icon-64.png', 64, { maskable: false }],
]
for (const [name, size, opts] of jobs) {
  writeFileSync(resolve(OUT, name), render(size, opts))
  console.log(`icons/${name}  ${size}x${size}`)
}
