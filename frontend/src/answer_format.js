export function parseConceptualAnswer(text) {
  let normalized = String(text || '').replace(/\r\n/g, '\n').trim()
  const inlineBullets = normalized.match(/[ \t]+[-*•][ \t]+(?=\S)/g) || []

  if (inlineBullets.length >= 2) {
    normalized = normalized.replace(/[ \t]+[-*•][ \t]+(?=\S)/g, '\n\n- ')
  }

  normalized = normalized
    .replace(/^[ \t]*[*•][ \t]+/gm, '- ')
    .replace(/^[ \t]*-[ \t]+/gm, '- ')
    .replace(/(^- .+?)\n(?=- )/gm, '$1\n\n')
    .replace(/\s*real-life example\s*:\s*/gi, '\n\nReal-life example:\n\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

  return normalized
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const bullet = block.match(/^[-*•]\s+([\s\S]+)$/)
      if (bullet) {
        return { type: 'bullet', text: bullet[1].trim() }
      }
      if (/^real-life example:$/i.test(block)) {
        return { type: 'heading', text: 'Real-life example:' }
      }
      return { type: 'paragraph', text: block }
    })
}

export function groupConceptualAnswer(blocks) {
  return blocks.reduce((groups, block, index) => {
    if (block.type !== 'bullet') {
      groups.push({ ...block, sourceIndexes: [index] })
      return groups
    }

    const previous = groups[groups.length - 1]
    if (previous?.type === 'list') {
      previous.items.push(block.text)
      previous.sourceIndexes.push(index)
    } else {
      groups.push({ type: 'list', items: [block.text], sourceIndexes: [index] })
    }
    return groups
  }, [])
}
