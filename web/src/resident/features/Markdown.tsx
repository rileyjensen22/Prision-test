import type { ReactNode } from 'react'

/**
 * A tiny, safe Markdown renderer for lessons: paragraphs, bullet and numbered lists, **bold** and
 * *italic*. It only ever builds React elements from plain text (never HTML), and the course
 * validator already refuses HTML, links and images.
 */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /\*\*([^*]+)\*\*|\*([^*]+)\*/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = pattern.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    out.push(m[1] !== undefined ? <strong key={key++}>{m[1]}</strong> : <em key={key++}>{m[2]}</em>)
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Markdown({ source }: { source: string }) {
  const blocks = source.trim().split(/\n\s*\n/)
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => {
        const lines = block.split('\n').filter((l) => l.trim())
        if (lines.every((l) => /^[-*] /.test(l)))
          return (
            <ul key={i} className="list-disc space-y-1 pl-6">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.slice(2))}</li>
              ))}
            </ul>
          )
        if (lines.every((l) => /^\d+\. /.test(l)))
          return (
            <ol key={i} className="list-decimal space-y-1 pl-6">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\d+\. /, ''))}</li>
              ))}
            </ol>
          )
        return <p key={i}>{inline(lines.join(' '))}</p>
      })}
    </div>
  )
}
