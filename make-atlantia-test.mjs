/**
 * Reconstructs the exact dialogue/prose passage from the user's screenshot
 * comparison — first-line-indent paragraphing, one italic word ("him"),
 * dialogue lines mixed with narrative — to verify the paragraph-boundary
 * fix against the actual reported content, not just a synthetic stand-in.
 */
import { writeFileSync } from 'node:fs'

const W = 396
const H = 600
const MARGIN = 40
const INDENT = MARGIN + 20
const LEAD = 15.6
const esc = (s) => s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)')

const objects = []
const add = (b) => { objects.push(b); return objects.length }
add('PLACEHOLDER')
add('PLACEHOLDER')
add('<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>')
add('<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic >>')

// { runs: [{text, italic}], indent }
const lines = [
  { runs: [{ text: '“We go home to marry, my Princess.”' }], indent: true },
  { runs: [{ text: 'As in get married?' }], indent: true },
  { runs: [{ text: 'To ' }, { text: 'him', italic: true }, { text: '?' }], indent: true },
  { runs: [{ text: "Suddenly, I thought of all those girlish fantasies I’d had before I" }], indent: true },
  { runs: [{ text: 'learned who I was and what was expected of me—daydreams given' }], indent: false },
  { runs: [{ text: 'life because of the love my parents had for one another.' }], indent: false },
  { runs: [{ text: 'Never once did those little-girl dreams include a proposal that' }], indent: true },
  { runs: [{ text: "wasn’t remotely an actual proposal. Nor did they incorporate it being" }], indent: false },
  { runs: [{ text: 'announced at a table full of strangers, half of which wanted me dead.' }], indent: false },
  { runs: [{ text: 'And those dreams surely hadn’t involved what had to be the' }], indent: true },
  { runs: [{ text: 'kingdom’s worst—and possibly most insane—non-proposal of' }], indent: false },
  { runs: [{ text: 'marriage to a man currently holding me captive.' }], indent: false },
  { runs: [{ text: 'Perhaps I had some sort of ailment of the brain. Maybe I was' }], indent: true },
  { runs: [{ text: 'experiencing hallucinations brought on by stress. After all, there had' }], indent: false },
  { runs: [{ text: 'been so much painful death to process. His betrayal to deal with.' }], indent: false },
]

const ops = []
let y = H - 60
for (const line of lines) {
  let x = line.indent ? INDENT : MARGIN
  for (const run of line.runs) {
    const font = run.italic ? '/F2' : '/F1'
    ops.push(`BT ${font} 11 Tf 1 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)} Tm (${esc(run.text)}) Tj ET`)
    // rough Times-Roman-ish advance width for the next run's x position
    x += run.text.length * 5.4
  }
  y -= LEAD
}
const stream = ops.join('\n')
const contentObj = add(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`)
const pageObj = add(
  `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Contents ${contentObj} 0 R ` +
    `/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>`,
)
objects[0] = `<< /Type /Catalog /Pages 2 0 R >>`
objects[1] = `<< /Type /Pages /Kids [${pageObj} 0 R] /Count 1 >>`
const infoNumber = add('<< /Title (Atlantia Passage Test) >>')

let pdf = Buffer.from('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n', 'latin1')
const offsets = [0]
objects.forEach((b, index) => {
  offsets.push(pdf.length)
  pdf = Buffer.concat([pdf, Buffer.from(`${index + 1} 0 obj\n`, 'latin1'), Buffer.from(b, 'utf8'), Buffer.from('\nendobj\n', 'latin1')])
})
const xrefStart = pdf.length
let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
for (let i = 1; i <= objects.length; i++) xref += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`
xref += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R /Info ${infoNumber} 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`
pdf = Buffer.concat([pdf, Buffer.from(xref, 'latin1')])

const out = process.argv[2] ?? 'atlantia-test.pdf'
writeFileSync(out, pdf)
console.log(`wrote ${out}: ${pdf.length} bytes`)
