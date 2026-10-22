import React from 'react'
import './AnswerText.css'

// Deliberately small Markdown subset. HTML, links and resources remain inert
// text; only local React elements are created, including for incomplete streams.
function inline(text) {
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|(?<!\w)__[^_\n]+__(?!\w)|\*[^*\s](?:[^*\n]*?[^*\s])?\*)/g
  const parts = []
  let end = 0
  for (const match of text.matchAll(pattern)) {
    parts.push(text.slice(end, match.index))
    const token = match[0]
    const Tag = token.startsWith('`') ? 'code' : token.startsWith('**') || token.startsWith('__') ? 'strong' : 'em'
    const width = Tag === 'strong' ? 2 : 1
    parts.push(<Tag key={match.index}>{token.slice(width, -width)}</Tag>)
    end = match.index + token.length
  }
  parts.push(text.slice(end))
  return parts
}

const item = line => line.match(/^ {0,3}(?:(\d{1,6})[.)]|([-+*]))\s+(.+)$/)
const fence = line => line.match(/^ {0,3}(`{3,}|~{3,})([^`]*)$/)

export default function AnswerText({ text = '' }) {
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n')
  const blocks = []
  let i = 0
  while (i < lines.length) {
    const key = i, opening = fence(lines[i])
    if (!lines[i].trim()) { i++; continue }
    if (opening) {
      const code = []
      const delimiter = opening[1]
      i++
      while (i < lines.length && !(lines[i].trim().startsWith(delimiter) && !lines[i].trim().slice(delimiter.length).trim())) code.push(lines[i++])
      if (i < lines.length) i++
      blocks.push(<pre key={key}><code>{code.join('\n')}</code></pre>)
      continue
    }
    if (/^ {4}|^\t/.test(lines[i])) {
      const code = []
      while (i < lines.length && (/^ {4}|^\t/.test(lines[i]) || !lines[i].trim())) code.push(lines[i++].replace(/^(?: {4}|\t)/, ''))
      blocks.push(<pre key={key}><code>{code.join('\n')}</code></pre>)
      continue
    }
    const heading = lines[i].match(/^ {0,3}#{1,6}\s+(.+)$/)
    if (heading) { blocks.push(<h3 key={key}>{inline(heading[1])}</h3>); i++; continue }
    const first = item(lines[i])
    if (first) {
      const ordered = Boolean(first[1]), entries = []
      while (i < lines.length) {
        const next = item(lines[i])
        if (!next || Boolean(next[1]) !== ordered) break
        const content = [next[3]]
        i++
        while (i < lines.length && /^ {2,}\S/.test(lines[i]) && !item(lines[i])) content.push(lines[i++].trimStart())
        entries.push(<li key={entries.length}>{inline(content.join('\n'))}</li>)
      }
      blocks.push(ordered ? <ol key={key} start={Number(first[1])}>{entries}</ol> : <ul key={key}>{entries}</ul>)
      continue
    }
    const paragraph = [lines[i++]]
    while (i < lines.length && lines[i].trim() && !fence(lines[i]) && !item(lines[i]) && !/^ {0,3}#{1,6}\s/.test(lines[i]) && !/^ {4}|^\t/.test(lines[i])) paragraph.push(lines[i++])
    blocks.push(<p key={key}>{inline(paragraph.join('\n'))}</p>)
  }
  return <div className="answer-text">{blocks}</div>
}
