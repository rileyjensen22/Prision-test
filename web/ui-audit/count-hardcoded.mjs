import { readFileSync, readdirSync } from 'node:fs'
import ts from 'typescript'
let total = 0; const per = {}
for (const dir of ['src/staff/pages', 'src/staff', 'src/resident', 'src/resident/features']) {
  for (const f of readdirSync(dir).filter((x) => x.endsWith('.tsx') && !x.includes('test'))) {
    const file = `${dir}/${f}`
    const sf = ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    let n = 0; const ex = []
    const visit = (node) => {
      if (ts.isJsxText(node) && /[A-Za-z]{2,}/.test(node.text)) { n++; ex.push(node.text.trim().slice(0, 50)) }
      if (ts.isJsxAttribute(node) && ['placeholder','aria-label','title','alt'].includes(node.name.getText()) && node.initializer && ts.isStringLiteral(node.initializer)) { n++; ex.push(node.initializer.text) }
      ts.forEachChild(node, visit)
    }
    visit(sf)
    if (n) { per[file] = [n, ex.slice(0, 3)]; total += n }
  }
}
console.log(total); for (const [k, v] of Object.entries(per)) console.log(k, v[0], JSON.stringify(v[1]))
