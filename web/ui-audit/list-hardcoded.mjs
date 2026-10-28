import { readFileSync, readdirSync } from 'node:fs'
import ts from 'typescript'
for (const dir of ['src/staff/pages','src/staff']) {
  for (const f of readdirSync(dir).filter((x) => x.endsWith('.tsx') && !x.includes('test') && x !== 'Styleguide.tsx')) {
    const file = `${dir}/${f}`
    const sf = ts.createSourceFile(file, readFileSync(file,'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const visit = (node) => {
      const line = (n) => sf.getLineAndCharacterOfPosition(n.getStart()).line + 1
      if (ts.isJsxText(node) && /[A-Za-z]{2,}/.test(node.text)) console.log(`${file}:${line(node)}: ${JSON.stringify(node.text.trim().replace(/\s+/g,' '))}`)
      if (ts.isJsxAttribute(node) && ['placeholder','aria-label','title','alt'].includes(node.name.getText()) && node.initializer && ts.isStringLiteral(node.initializer)) console.log(`${file}:${line(node)}: attr ${JSON.stringify(node.initializer.text)}`)
      ts.forEachChild(node, visit)
    }
    visit(sf)
  }
}
