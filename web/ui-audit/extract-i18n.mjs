// One-off codemod: moves plain JSX text and a few string attributes in staff pages into the i18n
// files. Only touches text that is a whole element's only child, or a string attribute, so no
// sentence is ever split. Usage: node ui-audit/extract-i18n.mjs <File.tsx>...  (writes in place)
import { readFileSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'

import ts from 'typescript'

const ATTRS = new Set(['placeholder', 'aria-label', 'title', 'alt'])
const out = {} // page -> { key: text }, only the keys added by this run
const prior = process.env.PRIOR ? JSON.parse(readFileSync(process.env.PRIOR, 'utf8')) : {}

function slug(text) {
  const words = text
    .replace(/[^A-Za-z0-9 ]+/g, ' ')
    .trim()
    .split(/\s+/)
    .slice(0, 4)
  const s = words.map((w, i) => (i ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w.toLowerCase())).join('')
  return s || 'text'
}

for (const file of process.argv.slice(2)) {
  const page = basename(file, '.tsx')
  const src = readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const keys = new Map() // text -> key
  const used = new Set()
  const fresh = new Set()
  for (const [k, text] of Object.entries(prior[page] ?? {})) {
    keys.set(text, k)
    used.add(k)
  }
  const edits = [] // {start,end,replacement,fn}
  const hasT = /\bt\b/.test(src.replace(/\bt\(/g, '').replace(/\{ t \}/g, ''))
  const tName = hasT ? 'tr' : 't'

  function keyFor(text) {
    if (keys.has(text)) return keys.get(text)
    let k = slug(text)
    let n = 2
    const base = k
    while (used.has(k)) k = base + n++
    used.add(k)
    keys.set(text, k)
    fresh.add(k)
    return k
  }
  const worthy = (s) => /[A-Za-z]{2,}/.test(s) && !/^[\w.-]+\/[\w./-]+$/.test(s)

  function enclosingFn(node) {
    let n = node.parent
    while (n) {
      if (ts.isFunctionDeclaration(n) || ts.isArrowFunction(n) || ts.isFunctionExpression(n)) {
        // a component: starts with a capital letter or is default-exported
        const name = n.name?.text ?? (ts.isVariableDeclaration(n.parent) ? n.parent.name.getText() : '')
        if (/^[A-Z]/.test(name) || (ts.isFunctionDeclaration(n) && n.modifiers?.some((m) => m.kind === ts.SyntaxKind.DefaultKeyword))) return n
      }
      n = n.parent
    }
    return null
  }

  function visit(node) {
    if (ts.isJsxElement(node)) {
      const kids = node.children.filter((c) => !(ts.isJsxText(c) && c.containsOnlyTriviaWhiteSpaces))
      if (kids.length === 1 && ts.isJsxText(kids[0])) {
        const raw = kids[0].text
        const text = raw.replace(/\s+/g, ' ').trim()
        const tag = node.openingElement.tagName.getText()
        if (worthy(text) && !/[{}<>]/.test(text) && tag !== 'code' && tag !== 'pre') {
          const fn = enclosingFn(node)
          if (fn) {
            const start = kids[0].getStart() + raw.indexOf(raw.trim()[0]) - (kids[0].getStart() - kids[0].pos) * 0
            const lead = raw.length - raw.trimStart().length
            const trail = raw.length - raw.trimEnd().length
            edits.push({
              start: kids[0].pos + lead,
              end: kids[0].end - trail,
              replacement: `{${tName}('staff.pages.${page}.${keyFor(text)}')}`,
              fn,
              text,
            })
          }
        }
      }
    }
    if (ts.isJsxText(node) && !node.containsOnlyTriviaWhiteSpaces && process.env.LOOSE) {
      const sibs = node.parent.children
      const i = sibs.indexOf(node)
      const near = (j) => {
        for (let x = j; x >= 0 && x < sibs.length; x += j < i ? -1 : 1) {
          const c = sibs[x]
          if (!(ts.isJsxText(c) && c.containsOnlyTriviaWhiteSpaces) && c !== node) return c
        }
        return null
      }
      const prev = near(i - 1)
      const next = near(i + 1)
      const text = node.text.replace(/\s+/g, ' ').trim()
      const tag = node.parent.openingElement?.tagName.getText()
      if (
        worthy(text) &&
        !/[{}<>]/.test(text) &&
        !(prev && ts.isJsxExpression(prev)) &&
        !(next && ts.isJsxExpression(next)) &&
        tag !== 'code' &&
        tag !== 'pre' &&
        !(prev === null && next === null)
      ) {
        const fn = enclosingFn(node)
        if (fn) {
          const raw = node.text
          const lead = raw.length - raw.trimStart().length
          const trail = raw.length - raw.trimEnd().length
          edits.push({ start: node.pos + lead, end: node.end - trail, replacement: `{${tName}('staff.pages.${page}.${keyFor(text)}')}`, fn, text })
        }
      }
    }
    if (ts.isJsxAttribute(node) && ATTRS.has(node.name.getText()) && node.initializer && ts.isStringLiteral(node.initializer)) {
      const text = node.initializer.text
      const fn = enclosingFn(node)
      if (worthy(text) && fn)
        edits.push({
          start: node.initializer.getStart(),
          end: node.initializer.end,
          replacement: `{${tName}('staff.pages.${page}.${keyFor(text)}')}`,
          fn,
          text,
        })
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  if (!edits.length) continue

  // functions needing the hook
  const fns = [...new Set(edits.map((e) => e.fn))]
  for (const fn of fns) {
    if (!fn.body || !ts.isBlock(fn.body)) {
      console.error(`${page}: expression-bodied component, skipped its edits`)
      for (let i = edits.length - 1; i >= 0; i--) if (edits[i].fn === fn) edits.splice(i, 1)
      continue
    }
    const hasHook = fn.body.getText().includes('useTranslation()')
    if (!hasHook) edits.push({ start: fn.body.getStart() + 1, end: fn.body.getStart() + 1, replacement: `\n  const { t${tName === 't' ? '' : ': tr'} } = useTranslation()\n`, fn: null })
    else if (tName !== 't') console.error(`${page}: has own hook and a local 't'; check by hand`)
  }
  edits.sort((a, b) => b.start - a.start)
  let res = src
  for (const e of edits) res = res.slice(0, e.start) + e.replacement + res.slice(e.end)
  if (!/from 'react-i18next'/.test(res)) {
    const firstImportEnd = res.indexOf('\n', res.indexOf('import '))
    res = res.slice(0, firstImportEnd + 1) + "import { useTranslation } from 'react-i18next'\n" + res.slice(firstImportEnd + 1)
  }
  writeFileSync(file, res)
  out[page] = Object.fromEntries([...keys].filter(([, k]) => fresh.has(k)).map(([text, k]) => [k, text]))
  console.error(`${page}: ${fresh.size} new strings`)
}
console.log(JSON.stringify(out, null, 1))
