(() => {
  if (globalThis.__SAIIA_C095_CONTENT_SCRIPT_READY__) {
    return
  }
  globalThis.__SAIIA_C095_CONTENT_SCRIPT_READY__ = true

  const LIMITS = {
    maxTextLength: 6000,
    maxSectionTextLength: 2500,
    maxTitleLength: 180,
    maxExamples: 4,
    maxOptions: 12,
    maxCodeLength: 8000,
    maxConstraints: 20,
    maxCandidateRegions: 12,
    maxWarnings: 12,
  }
  const SECTION_DEFS = [
    ['statement', /^(problem|statement|question|description|instructions?|task)$/i],
    ['function_description', /^(function description|task)$/i],
    ['input_format', /^(input format|parameters|arguments|function parameters|standard input)$/i],
    ['output_format', /^(output format|print|prints|return value|returns|standard output|expected return)$/i],
    ['constraints', /^(constraints|limits)$/i],
    ['examples', /^(example(?:\s+\d+)?|examples|sample(?:\s+\d+)?|samples|sample input(?:\s+\d+)?|sample output(?:\s+\d+)?|sample explanation(?:\s+\d+)?|example input(?:\s+\d+)?|example output(?:\s+\d+)?|example explanation(?:\s+\d+)?|expected output(?:\s+\d+)?|example result|explanation(?:\s+\d+)?|test case(?:\s+\d+)?)$/i],
    ['explanation', /^(explanation|notes?)$/i],
    ['runtime_panel', /^(custom input|test against custom input|test result|run output|your output|console output|console|submit code|run code)$/i],
  ]
  const exampleDiagnosticsState = {
    rawCandidateCount: 0,
    duplicateCount: 0,
    truncated: false,
    sectionBoundaryStopCount: 0,
    editorSectionExcludedCount: 0,
  }

  function sanitizeText(value, limit = LIMITS.maxTextLength) {
    return String(value ?? '')
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' ')
      .replace(/[ \t\f\v]+/g, ' ')
      .replace(/\s*\n\s*/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
      .slice(0, limit)
  }

  function sanitizeTextPreserveTabs(value, limit = LIMITS.maxTextLength) {
    return String(value ?? '')
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' ')
      .replace(/[ \f\v]+/g, ' ')
      .replace(/[ \t]*\n[ \t]*/g, '\n')
      .replace(/\t+/g, '\t')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
      .slice(0, limit)
  }

  function sanitizeCode(value, limit = LIMITS.maxCodeLength) {
    return String(value ?? '')
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, ' ')
      .replace(/\r\n?/g, '\n')
      .replace(/\n{4,}/g, '\n\n\n')
      .trim()
      .slice(0, limit)
  }

  function isVisible(node) {
    if (!node || node.hidden || node.getAttribute?.('aria-hidden') === 'true') return false
    const style = window.getComputedStyle(node)
    if (style.display === 'none' || style.visibility === 'hidden') return false
    const rect = node.getBoundingClientRect?.()
    return !(rect && rect.width === 0 && rect.height === 0 && !node.textContent?.trim())
  }

  function visibleText(node) {
    if (!node) return ''
    const clone = node.cloneNode(true)
    clone.querySelectorAll('script,style,noscript,template,nav,aside,footer,header,[hidden],[aria-hidden="true"],input[type="password"],button').forEach((entry) => entry.remove())
    return sanitizeText(clone.textContent || '', LIMITS.maxTextLength)
  }

  function scoreCandidate(node) {
    const text = visibleText(node)
    const html = node.outerHTML || ''
    let score = 0
    if (/\b(problem|question|task|description|instructions?)\b/i.test(text)) score += 4
    if (/\b(input format|output format|constraints?|examples?|sample input|sample output)\b/i.test(text)) score += 3
    if (/\b(function|class|return|print|stdin|stdout|debug|fix|output)\b/i.test(text)) score += 2
    if (node.querySelector?.('pre,code,textarea,[contenteditable="true"],[class*="editor"],[class*="code"],[class*="line"]')) score += 4
    if (node.querySelector?.('input[type="radio"],input[type="checkbox"],[role="option"]')) score += 4
    if (node.querySelector?.('img,figure,svg,canvas')) score += 2
    if (text.length > 80) score += 2
    if (text.length > 400) score += 1
    if (/\b(nav|menu|profile|account|advertisement|copyright|subscribe|share|settings)\b/i.test(text)) score -= 4
    if (/<(main|article|section|form)\b/i.test(html)) score += 1
    return { node, text, score }
  }

  function selectRoot() {
    const nodes = Array.from(document.querySelectorAll('main,article,section,form,[role="main"],[data-question],div'))
      .filter(isVisible)
      .slice(0, 180)
    const initial = nodes
      .map(scoreCandidate)
      .filter((candidate) => candidate.text.length >= 24 || candidate.score > 4)
      .sort((a, b) => b.score - a.score || a.text.length - b.text.length)
      .slice(0, LIMITS.maxCandidateRegions)
    if (document.body) {
      initial.push({ ...scoreCandidate(document.body), score: scoreCandidate(document.body).score - 2 })
    }
    const splitPair = findComplementaryCodingPair(initial)
    const candidates = collapseCandidateOverlaps(initial)
    const selected = candidates[0] || { node: document.body, text: visibleText(document.body), score: 0 }
    const second = candidates[1]
    const comparisonA = splitPair?.[0] || selected
    const comparisonB = splitPair?.[1] || second
    const relationship = comparisonA && comparisonB ? candidateRelationship(comparisonA, comparisonB) : 'none'
    const sharedRoot = comparisonA && comparisonB ? sharedWorkspaceCandidate(initial, comparisonA, comparisonB) : null
    const complementary = Boolean(splitPair || (selected && second && areComplementaryCodingRegions(selected, second, sharedRoot)))
    const independentEvidence = selected && second ? independentQuestionEvidence(selected, second, relationship) : singleRootIndependentEvidence(selected)
    const closeScores = Boolean(second && selected.score >= 4 && Math.abs(selected.score - second.score) <= 1.2)
    const combinedBase = complementary
      ? splitPair
        ? preferCandidateRoot(splitPair[0], splitPair[1])
        : preferCandidateRoot(selected, second)
      : null
    const combined = complementary ? { ...(sharedRoot || combinedBase), score: Math.max(comparisonA?.score ?? 0, comparisonB?.score ?? 0) } : null
    const finalSelected = combined || selected
    const ambiguous = Boolean(!combined && independentEvidence.length && (closeScores || !second))
    const strategy = combined
      ? 'combined_split_coding_workspace'
      : ambiguous
        ? 'ambiguous_independent_question_regions'
        : 'highest_scoring_generic_region'
    const status = ambiguous ? 'selection_required' : undefined
    return {
      root: finalSelected.node,
      candidateCount: candidates.length,
      score: finalSelected.score,
      strategy,
      warnings: ambiguous ? ['multiple_question_regions_detected'] : [],
      ambiguous,
      diagnostics: {
        initial_candidate_count: initial.length,
        collapsed_candidate_count: candidates.length,
        top_score: finalSelected?.score ?? 0,
        second_score: candidates.length > 1 ? candidates[1]?.score ?? null : null,
        initial_top_score: initial[0]?.score ?? 0,
        initial_second_score: initial[1]?.score ?? null,
        candidate_relationship: relationship,
        shared_root_found: Boolean(sharedRoot),
        combined_split_layout: Boolean(combined),
        independent_question_evidence: independentEvidence,
        selection_strategy: strategy,
        final_status: status || 'ready_or_incomplete',
      },
    }
  }

  function collapseCandidateOverlaps(candidates) {
    const collapsed = []
    for (const candidate of candidates) {
      const duplicateIndex = collapsed.findIndex((entry) => {
        const relation = candidateRelationship(entry, candidate)
        return relation === 'duplicate_or_overlap' || relation === 'ancestor_descendant'
      })
      if (duplicateIndex === -1) {
        collapsed.push(candidate)
        continue
      }
      collapsed[duplicateIndex] = preferCandidateRoot(collapsed[duplicateIndex], candidate)
    }
    return collapsed.sort((a, b) => b.score - a.score || a.text.length - b.text.length)
  }

  function findComplementaryCodingPair(candidates) {
    for (let i = 0; i < candidates.length; i += 1) {
      for (let j = i + 1; j < candidates.length; j += 1) {
        const sharedRoot = sharedWorkspaceCandidate(candidates, candidates[i], candidates[j])
        if (areComplementaryCodingRegions(candidates[i], candidates[j], sharedRoot)) {
          return [candidates[i], candidates[j]]
        }
      }
    }
    return null
  }

  function preferCandidateRoot(a, b) {
    const aSignals = candidateSignals(a)
    const bSignals = candidateSignals(b)
    if (aSignals.problemLike && aSignals.codeLike && !(bSignals.problemLike && bSignals.codeLike)) return a
    if (bSignals.problemLike && bSignals.codeLike && !(aSignals.problemLike && aSignals.codeLike)) return b
    if (aSignals.problemScore !== bSignals.problemScore) return aSignals.problemScore > bSignals.problemScore ? a : b
    if (a.score !== b.score) return a.score > b.score ? a : b
    return a.text.length >= b.text.length ? a : b
  }

  function sharedWorkspaceCandidate(candidates, a, b) {
    const containing = candidates
      .filter((candidate) => candidate !== a && candidate !== b)
      .filter((candidate) => candidate.node?.contains?.(a.node) && candidate.node?.contains?.(b.node) && isSafeWorkspaceRoot(candidate.node))
      .sort((left, right) => left.text.length - right.text.length || right.score - left.score)[0]
    if (containing) return containing
    const ancestor = nearestCommonAncestor(a.node, b.node)
    return ancestor ? scoreCandidate(ancestor) : null
  }

  function areComplementaryCodingRegions(a, b, sharedRoot = null) {
    const left = candidateSignals(a)
    const right = candidateSignals(b)
    const oneProblemOneCode = (left.problemLike && right.codeLike && !right.independentLike) ||
      (right.problemLike && left.codeLike && !left.independentLike)
    if (!oneProblemOneCode) return false
    if (left.optionLike || right.optionLike) return false
    if (left.separateTaskLike && right.separateTaskLike) return false
    if (!sharedRoot && candidateRelationship(a, b) === 'separate') return false
    const sharedSignals = sharedRoot ? candidateSignals(sharedRoot) : null
    if (sharedSignals?.optionGroups > 1 || sharedSignals?.separateQuestionBlocks > 1) return false
    return true
  }

  function independentQuestionEvidence(a, b, relationship = candidateRelationship(a, b)) {
    const left = candidateSignals(a)
    const right = candidateSignals(b)
    const evidence = []
    if (relationship === 'separate') evidence.push('separate_regions')
    if (left.optionLike && right.optionLike) evidence.push('separate_option_groups')
    if (left.separateTaskLike && right.separateTaskLike) evidence.push('separate_task_headings')
    if (left.codeLike && right.codeLike && left.problemLike && right.problemLike) evidence.push('separate_coding_tasks')
    if (left.completeLike && right.completeLike && relationship !== 'ancestor_descendant' && relationship !== 'duplicate_or_overlap') {
      evidence.push('both_independently_complete')
    }
    return evidence
  }

  function singleRootIndependentEvidence(candidate) {
    const signals = candidateSignals(candidate)
    const evidence = []
    if (signals.separateQuestionBlocks > 1) evidence.push('multiple_question_blocks')
    if (signals.optionGroups > 1) evidence.push('multiple_option_groups')
    return evidence
  }

  function candidateRelationship(a, b) {
    if (a?.node && b?.node) {
      if (a.node === b.node) return 'same'
      if (a.node.contains?.(b.node) || b.node.contains?.(a.node)) return 'ancestor_descendant'
      if (nearestCommonAncestor(a.node, b.node)) return 'shared_workspace'
    }
    const aText = normalizedCandidateText(a)
    const bText = normalizedCandidateText(b)
    if (!aText || !bText) return 'separate'
    if (aText === bText || overlapRatio(aText, bText) >= 0.82) return 'duplicate_or_overlap'
    return 'separate'
  }

  function nearestCommonAncestor(a, b) {
    const seen = new Set()
    let node = a
    while (node) {
      seen.add(node)
      node = node.parentElement
    }
    node = b
    while (node) {
      if (seen.has(node) && isSafeWorkspaceRoot(node)) return node
      node = node.parentElement
    }
    return null
  }

  function isSafeWorkspaceRoot(node) {
    if (!node || /^(HTML|BODY)$/i.test(node.tagName || '')) return false
    return !node.closest?.('nav,header,footer,aside,[role="navigation"],[role="banner"],[role="contentinfo"]')
  }

  function candidateSignals(candidate) {
    const text = sanitizeText(candidate?.text || '')
    const html = String(candidate?.node?.outerHTML || '')
    const code = candidate?.node ? codeText(candidate.node) : ''
    const optionGroups = optionGroupCountFromHtml(html)
    const separateQuestionBlocks = (text.match(/\b(?:question|problem|task)\s+(?:\d+|[a-z]|one|two|three|four|five|six|seven|eight|nine|ten)\b/gi) || []).length
    const problemScore = [
      /\b(problem|question|task|description|instructions?)\b/i,
      /\b(given|write a program|implement|complete the function|return|print)\b/i,
      /\b(input format|output format|constraints?|examples?|sample input|sample output)\b/i,
    ].reduce((score, pattern) => score + (pattern.test(text) ? 1 : 0), 0)
    const problemLike = problemScore > 0 && text.length >= 24
    const codeLike = Boolean(code) || /<(pre|code|textarea)\b|contenteditable=["']?true|(?:editor|code|line)/i.test(html)
    const optionLike = optionGroups > 0 || /<input\b[^>]*type=["']?(?:radio|checkbox)|role=["']?option/i.test(html)
    const separateTaskLike = /\b(?:question|problem|task)\s+(?:\d+|[a-z]|one|two|three|four|five|six|seven|eight|nine|ten)\b/i.test(text)
    return {
      problemLike,
      codeLike,
      optionLike,
      problemScore,
      optionGroups,
      separateQuestionBlocks,
      separateTaskLike,
      independentLike: optionLike || separateTaskLike,
      completeLike: problemLike && (codeLike || optionLike || text.length >= 80),
    }
  }

  function optionGroupCountFromHtml(html) {
    const structural = (html.match(/<fieldset\b|role=["']?radiogroup|role=["']?listbox/gi) || []).length
    if (structural) return structural
    const names = [...String(html || '').matchAll(/<input\b[^>]*type=["']?(?:radio|checkbox)[^>]*name=["']?([^"'\s>]+)/gi)]
      .map((match) => match[1])
      .filter(Boolean)
    const distinctNames = new Set(names)
    if (distinctNames.size) return distinctNames.size
    const inputCount = (html.match(/<input\b[^>]*type=["']?(?:radio|checkbox)/gi) || []).length
    return inputCount >= 2 ? 1 : inputCount
  }

  function normalizedCandidateText(candidate) {
    return sanitizeText(candidate?.text || '', LIMITS.maxTextLength)
      .toLowerCase()
      .replace(/\s+/g, ' ')
  }

  function overlapRatio(a, b) {
    const shorter = a.length <= b.length ? a : b
    const longer = a.length <= b.length ? b : a
    if (!shorter) return 0
    if (longer.includes(shorter)) return 1
    const shortWords = new Set(shorter.split(/\W+/).filter((word) => word.length > 2))
    const longWords = new Set(longer.split(/\W+/).filter((word) => word.length > 2))
    if (!shortWords.size) return 0
    let overlap = 0
    for (const word of shortWords) {
      if (longWords.has(word)) overlap += 1
    }
    return overlap / shortWords.size
  }

  function sectionLabelPrefix(label) {
    return sanitizeText(label, 120).split('\n')[0].replace(/:.*/, '').trim()
  }

  function labelKey(label) {
    const safe = sectionLabelPrefix(label)
    return SECTION_DEFS.find(([, pattern]) => pattern.test(safe))?.[0] || null
  }

  function isSectionCollectionBoundaryNode(node, activeKey) {
    const key = labelKey(nodeLabel(node))
    const blocked = (key && !(activeKey === 'examples' && key === 'explanation')) || isEditorRuntimeSolutionNode(node)
    if (blocked) exampleDiagnosticsState.sectionBoundaryStopCount += 1
    return blocked
  }

  function isEditorRuntimeSolutionNode(node) {
    if (!node) return false
    const tag = (node.tagName || '').toLowerCase()
    if (/^(nav|aside|footer|header)$/.test(tag)) return true
    const marker = `${node.className || ''} ${node.id || ''} ${node.getAttribute?.('role') || ''} ${node.getAttribute?.('aria-label') || ''} ${node.getAttribute?.('data-testid') || ''} ${node.getAttribute?.('data-cy') || ''}`.toLowerCase()
    return /\b(monaco-editor|view-lines|ace_editor|ace_text-layer|codemirror|cm-editor|cm-content|generic[-_ ]?editor|code[-_ ]?editor|editor[-_ ]?(?:root|container|pane|area)|runtime|custom[-_ ]?input|testcase|test[-_ ]?result|run[-_ ]?output|console|editorial|solution|discussion|submissions?|sidebar)\b/.test(marker)
  }

  function cleanSectionNodeText(node, activeKey) {
    if (!node?.cloneNode) return ''
    const clone = node.cloneNode(true)
    const excluded = clone.querySelectorAll('script,style,noscript,template,nav,aside,footer,header,[hidden],[aria-hidden="true"],textarea,[contenteditable="true"],[role="textbox"],[aria-multiline="true"],[class*="editor"],[class*="code-editor"],[class*="monaco"],[class*="ace_"],[class*="CodeMirror"],[class*="cm-editor"],[class*="console"],[class*="testcase"],[class*="test-result"],[class*="run-output"],[class*="solution"],[class*="editorial"],[class*="discussion"]')
    exampleDiagnosticsState.editorSectionExcludedCount += excluded.length
    excluded.forEach((entry) => entry.remove())
    return sanitizeTextPreserveTabs((clone.textContent || '').replace(activeKey ? '' : '', ''), LIMITS.maxSectionTextLength)
  }

  function inlineLabelContent(labelNode, key) {
    const text = sanitizeTextPreserveTabs(labelNode?.textContent || '', LIMITS.maxSectionTextLength)
    const prefix = sectionLabelPrefix(nodeLabel(labelNode))
    if (!prefix || !text.toLowerCase().startsWith(prefix.toLowerCase())) return ''
    const remainder = sanitizeTextPreserveTabs(text.slice(prefix.length).replace(/^:\s*/, ''), LIMITS.maxSectionTextLength)
    return remainder && labelKey(prefix) === key ? remainder : ''
  }

  function collectLabelledText(labelNode, key = labelKey(nodeLabel(labelNode))) {
    const chunks = []
    const inline = inlineLabelContent(labelNode, key)
    if (inline) chunks.push(inline)
    let node = labelNode.nextElementSibling
    while (node && chunks.length < 12) {
      if (isSectionCollectionBoundaryNode(node, key)) break
      if (isVisible(node)) chunks.push(node.matches?.('table') ? visibleTableText(node) : cleanSectionNodeText(node, key))
      node = node.nextElementSibling
    }
    if (!chunks.length && labelNode.parentElement) {
      const clone = labelNode.parentElement.cloneNode(true)
      const excluded = clone.querySelectorAll('script,style,noscript,template,nav,aside,footer,header,[hidden],textarea,[contenteditable="true"],[role="textbox"],[aria-multiline="true"],[class*="editor"],[class*="code-editor"],[class*="monaco"],[class*="ace_"],[class*="CodeMirror"],[class*="cm-editor"],[class*="console"],[class*="testcase"],[class*="test-result"],[class*="run-output"],[class*="solution"],[class*="editorial"],[class*="discussion"]')
      exampleDiagnosticsState.editorSectionExcludedCount += excluded.length
      excluded.forEach((entry) => entry.remove())
      chunks.push(sanitizeText((clone.textContent || '').replace(labelNode.textContent || '', ''), LIMITS.maxSectionTextLength))
    }
    return sanitizeTextPreserveTabs(chunks.join('\n'), LIMITS.maxSectionTextLength)
  }

  function nodeLabel(node) {
    return sanitizeText(node?.getAttribute?.('aria-label') || node?.textContent || '', 120)
  }

  function visibleTableText(table) {
    return sanitizeTextPreserveTabs(Array.from(table?.querySelectorAll?.('tr') || []).map((row) => (
      Array.from(row.querySelectorAll('th,td')).map((cell) => sanitizeText(cell.textContent || '', 300)).filter(Boolean).join('\t')
    )).filter(Boolean).join('\n'), LIMITS.maxSectionTextLength)
  }

  function sections(root) {
    const result = { statement: '', examples: [] }
    const labels = Array.from(root.querySelectorAll('h1,h2,h3,h4,h5,h6,strong,b,dt,p,div,span,[aria-label]'))
      .filter(isVisible)
      .filter((node) => labelKey(nodeLabel(node)))
      .slice(0, 80)
    for (const labelNode of labels) {
      const label = nodeLabel(labelNode)
      const key = labelKey(label)
      const text = collectLabelledText(labelNode, key)
      if (!key || !text) continue
      if (key === 'examples') {
        result.examples = limitExamples(mergeExamples(result.examples, parseExamples(text, parseExampleHeading(label))))
      } else if (key === 'runtime_panel') {
        continue
      } else {
        result[key] = result[key] || text
      }
    }
    if (!result.statement) {
      result.statement = sanitizeText(visibleText(root).replace(codeText(root), ''), LIMITS.maxTextLength)
    }
    if (!result.examples.length) {
      result.examples = examples(root)
    }
    return result
  }

  function codeText(root) {
    return collectEditorEvidence(root).code
  }

  function emptyEditorEvidence() {
    return {
      editorPresent: false,
      editorType: null,
      editorRootCount: 0,
      code: '',
      codeAvailable: false,
      editorTextAvailable: false,
      editorBoilerplateOnly: false,
      placeholderText: '',
      codeExtractionMethod: null,
      codeLineCount: 0,
      codeLength: 0,
      codeMayBePartial: false,
      warning: null,
    }
  }

  function collectEditorEvidence(root) {
    const candidates = []
    const editorRoots = collectEditorRoots(root)
    for (const editorRoot of editorRoots) {
      const editorType = detectEditorType(editorRoot)
      for (const textarea of collectReachableNodes(editorRoot, 'textarea').filter(isVisible)) {
        addCodeCandidate(candidates, textarea.value || textarea.textContent || '', editorType || 'native_textarea', 'textarea_value', true, 9)
      }
      for (const editable of collectReachableNodes(editorRoot, '[contenteditable="true"]').filter(isVisible)) {
        addCodeCandidate(candidates, editable.innerText || editable.textContent || '', editorType || 'contenteditable', 'contenteditable_text', true, 8)
      }
      addLineCandidate(candidates, editorRoot, '.view-line', editorType || 'monaco', 'monaco_view_lines')
      addLineCandidate(candidates, editorRoot, '.ace_line', editorType || 'ace', 'ace_text_layer')
      addLineCandidate(candidates, editorRoot, '.cm-line', editorType || 'codemirror6', 'codemirror6_lines')
      addLineCandidate(candidates, editorRoot, '.CodeMirror-line', editorType || 'codemirror5', 'codemirror5_lines')
      addLineCandidate(candidates, editorRoot, '.editor-line,.code-line,[data-line-number]', editorType || 'generic_editor', 'generic_editor_lines')
      for (const textbox of collectReachableNodes(editorRoot, '[role="textbox"],[aria-multiline="true"]').filter(isVisible)) {
        addCodeCandidate(candidates, textbox.value || textbox.innerText || textbox.textContent || '', editorType || 'accessible_textbox', 'role_textbox_text', true, 6)
      }
      for (const block of collectReachableNodes(editorRoot, 'pre,code').filter(isVisible)) {
        addCodeCandidate(candidates, block.innerText || block.textContent || '', editorType || 'generic_editor', 'editor_pre_code', true, 5)
      }
      if (editorType === 'generic_editor') {
        addCodeCandidate(candidates, editorRoot.innerText || editorRoot.textContent || '', editorType, 'generic_editor_text', true, 6)
      }
    }

    if (!editorRoots.length) {
      for (const block of collectReachableNodes(root, 'pre,code,textarea,[contenteditable="true"]').filter(isVisible).slice(0, 20)) {
        if (block.closest?.('[class*="example"],[class*="sample"],[class*="output"],[class*="console"],[class*="testcase"],[class*="editorial"],[class*="solution"]')) continue
        addCodeCandidate(candidates, block.value || block.innerText || block.textContent || '', 'preformatted_code', 'pre_code_block', false, 4)
      }
    }

    for (const frameDoc of collectSameOriginFrameDocuments(root)) {
      const nested = collectEditorEvidence(frameDoc.body)
      if (nested.editorPresent) {
        addCodeCandidate(candidates, nested.code, nested.editorType || 'generic_editor', nested.codeExtractionMethod || 'same_origin_frame_editor', true, nested.codeAvailable ? 8 : 0)
      }
    }

    return finalizeEditorEvidence({ candidates, editorPresent: editorRoots.length > 0, editorRootCount: editorRoots.length })
  }

  function collectEditorRoots(root) {
    const selector = 'textarea,[contenteditable="true"],[role="textbox"],[aria-multiline="true"],.monaco-editor,.view-lines,.ace_editor,.CodeMirror,.cm-editor,[aria-label*="code" i],[aria-label*="editor" i],[class*="editor"],[class*="code"],canvas'
    const canonical = collectReachableNodes(root, selector)
      .filter(isVisible)
      .filter((node) => isEditorRoot(node))
      .map(canonicalEditorRoot)
      .filter(Boolean)
    return [...new Set(canonical)]
      .filter((node, _index, nodes) => !nodes.some((other) => other !== node && other.contains?.(node) && sameEditorType(other, node)))
      .slice(0, 12)
  }

  function collectEditorEvidenceWithFallback(root) {
    const selected = collectEditorEvidence(root)
    if (selected.codeAvailable) return { ...selected, editorScope: 'selected_root' }
    if (selected.editorBoilerplateOnly) return { ...selected, editorScope: 'selected_root' }
    const documentRoots = collectEditorRoots(document.body)
      .filter((node) => !node.closest?.('[class*="solution"],[class*="editorial"],[class*="discussion"],[class*="testcase"],[class*="test-result"],[class*="console"],[class*="custom-input"],[aria-label*="solution" i],[aria-label*="editorial" i],[aria-label*="console" i]'))
      .filter((node, index, nodes) => nodes.indexOf(node) === index)
    const fallbackEvidence = documentRoots.map((node) => collectEditorEvidence(node))
    const usable = fallbackEvidence.filter((entry) => entry.codeAvailable)
    if (usable.length === 1) {
      return { ...usable[0], editorScope: 'document_single_editor_fallback', editorRootCount: documentRoots.length }
    }
    if (documentRoots.length === 1 && fallbackEvidence[0]?.editorTextAvailable) {
      return { ...fallbackEvidence[0], editorScope: 'document_single_editor_fallback', editorRootCount: documentRoots.length }
    }
    if (documentRoots.length > 1) return { ...selected, editorScope: 'ambiguous_multiple_editors' }
    return { ...selected, editorScope: selected.editorPresent ? 'selected_root' : 'unavailable' }
  }

  function canonicalEditorRoot(node) {
    return node.closest?.('.monaco-editor,.ace_editor,.CodeMirror,.cm-editor') ||
      (node.matches?.('textarea,[contenteditable="true"]') ? node : null) ||
      node.closest?.('[class*="editor"],[class*="code"]') ||
      node
  }

  function sameEditorType(a, b) {
    return detectEditorType(a) === detectEditorType(b)
  }

  function isEditorRoot(node) {
    const text = `${node.className || ''} ${node.id || ''} ${node.getAttribute?.('aria-label') || ''} ${node.getAttribute?.('data-testid') || ''} ${node.getAttribute?.('data-cy') || ''}`.toLowerCase()
    if (/\b(editorial|headline|timeline|barcode)\b/.test(text)) return false
    if (/\b(monaco-editor|view-lines|ace_editor|ace_text-layer|codemirror|cm-editor|cm-content)\b/.test(text)) return true
    if (/\b(?:code[-_ ]?editor|generic[-_ ]?editor|editor[-_ ]?(?:root|container|pane|area))\b/.test(text)) return true
    if (node.matches?.('textarea,[contenteditable="true"]')) return true
    if (node.matches?.('[role="textbox"],[aria-multiline="true"]') && /\b(code|editor)\b/.test(text)) return true
    if ((node.tagName || '').toLowerCase() === 'canvas' && /\b(code|editor|monaco|ace|cm-)\b/.test(text + ' ' + (node.parentElement?.className || ''))) return true
    return false
  }

  function detectEditorType(node) {
    const text = `${node.className || ''} ${node.getAttribute?.('aria-label') || ''}`.toLowerCase()
    if (text.includes('monaco') || node.querySelector?.('.view-line')) return 'monaco'
    if (text.includes('ace_') || node.querySelector?.('.ace_line')) return 'ace'
    if (text.includes('codemirror') || node.querySelector?.('.CodeMirror-line')) return 'codemirror5'
    if (text.includes('cm-editor') || node.querySelector?.('.cm-line')) return 'codemirror6'
    if (node.matches?.('textarea')) return 'native_textarea'
    if (node.matches?.('[contenteditable="true"]')) return 'contenteditable'
    return 'generic_editor'
  }

  function collectReachableNodes(root, selector, depth = 0, seen = new Set()) {
    if (!root || depth > 3 || seen.has(root)) return []
    seen.add(root)
    const nodes = root.matches?.(selector) ? [root] : []
    nodes.push(...Array.from(root.querySelectorAll?.(selector) || []))
    const shadowHosts = Array.from(root.querySelectorAll?.('*') || []).filter((node) => node.shadowRoot).slice(0, 40)
    for (const host of shadowHosts) nodes.push(...collectReachableNodes(host.shadowRoot, selector, depth + 1, seen))
    return nodes
  }

  function collectSameOriginFrameDocuments(root) {
    return Array.from(root?.querySelectorAll?.('iframe,frame') || []).slice(0, 4).map((frame) => {
      try {
        return frame.contentDocument || null
      } catch {
        return null
      }
    }).filter(Boolean)
  }

  function addLineCandidate(candidates, root, selector, editorType, method) {
    const lines = collectReachableNodes(root, selector).filter(isVisible).map((node) => node.textContent || node.innerText || '')
    if (lines.length) addCodeCandidate(candidates, lines.join('\n'), editorType, method, true, 10, hasFoldedEditorNode(root))
  }

  function addCodeCandidate(candidates, value, editorType, method, editorBacked, baseScore, partial = false) {
    const code = normalizeEditorCode(value)
    if (!code) return
    const lineCount = code.split('\n').length
    const score = baseScore + (looksLikeCode(code) ? 8 : 0) + (lineCount > 1 ? 2 : 0) - (/^(run code|submit|testcase|output)$/i.test(code) ? 20 : 0)
    if (score <= 0) return
    candidates.push({ code, editorType, method, editorBacked, score, lineCount, partial })
  }

  function finalizeEditorEvidence({ candidates, editorPresent, editorRootCount }) {
    const classified = candidates.map((candidate) => ({ ...candidate, classification: classifyEditorText(candidate.code) }))
    const best = classified
      .filter((candidate) => candidate.classification.starterCodeAvailable)
      .sort((a, b) => b.score - a.score || b.code.length - a.code.length)[0] || null
    if (best) {
      return {
        editorPresent: editorPresent || best.editorBacked,
        editorType: best.editorType,
        editorRootCount,
        code: best.classification.usableCode,
        codeAvailable: true,
        editorTextAvailable: true,
        editorBoilerplateOnly: false,
        placeholderText: '',
        codeExtractionMethod: best.method,
        codeLineCount: best.lineCount,
        codeLength: best.classification.usableCode.length,
        codeMayBePartial: best.partial || best.method === 'generic_editor_lines',
        warning: best.partial || best.method === 'generic_editor_lines' ? 'editor_code_may_be_partial' : null,
      }
    }
    const readable = classified
      .filter((candidate) => candidate.classification.textAvailable)
      .sort((a, b) => b.score - a.score || b.code.length - a.code.length)[0] || null
    if (readable?.classification.boilerplateOnly) {
      return {
        editorPresent: editorPresent || readable.editorBacked,
        editorType: readable.editorType,
        editorRootCount,
        code: '',
        codeAvailable: false,
        editorTextAvailable: true,
        editorBoilerplateOnly: true,
        placeholderText: readable.classification.placeholderText,
        codeExtractionMethod: readable.method,
        codeLineCount: readable.lineCount,
        codeLength: 0,
        codeMayBePartial: false,
        warning: 'editor_boilerplate_only',
      }
    }
    if (!readable) {
      return { ...emptyEditorEvidence(), editorPresent, editorType: editorPresent ? 'generic_editor' : null, editorRootCount, warning: editorPresent ? 'editor_code_unavailable' : null }
    }
    return {
      editorPresent: editorPresent || readable.editorBacked,
      editorType: readable.editorType,
      editorRootCount,
      code: '',
      codeAvailable: false,
      editorTextAvailable: true,
      editorBoilerplateOnly: false,
      placeholderText: '',
      codeExtractionMethod: readable.method,
      codeLineCount: readable.lineCount,
      codeLength: 0,
      codeMayBePartial: false,
      warning: null,
    }
  }

  function classifyEditorText(text) {
    const raw = normalizeEditorCode(text)
    if (!raw) {
      return { textAvailable: false, starterCodeAvailable: false, boilerplateOnly: false, usableCode: '', placeholderText: '', warning: 'editor_code_unavailable' }
    }
    const meaningfulStructure = /(^|\n)\s*(?:def\s+\w+\s*\(|class\s+\w+|function\s+\w+\s*\(|(?:public\s+)?static\s+void\s+main\s*\(|int\s+main\s*\(|[A-Za-z_][\w:<>,\[\]\s*&]*\s+[A-Za-z_]\w*\s*\([^)]*\)\s*\{|#include\b|using\s+namespace\b|public:|private:|protected:)/m.test(raw)
    const commentOnly = raw.split('\n').map((line) => line.trim()).filter(Boolean).every((line) => /^(#|\/\/|\/\*|\*|\*\/)/.test(line))
    const uncommented = raw
      .split('\n')
      .map((line) => line.replace(/^\s*(#|\/\/|\*|\/\*)\s?/, '').replace(/\*\/\s*$/, '').trim())
      .filter(Boolean)
      .join(' ')
    const placeholder = /\b(enter your code here|write your code here|your code goes here|read input from stdin|print output to stdout|complete the code below|start coding here|todo)\b/i.test(uncommented)
    const passOnly = /^pass$/i.test(uncommented)
    const starterCodeAvailable = meaningfulStructure || (looksLikeCode(raw) && !commentOnly && !placeholder && !passOnly)
    const boilerplateOnly = !starterCodeAvailable && (commentOnly || placeholder || passOnly)
    return {
      textAvailable: true,
      starterCodeAvailable,
      boilerplateOnly,
      usableCode: starterCodeAvailable ? raw : '',
      placeholderText: boilerplateOnly ? raw : '',
      warning: boilerplateOnly ? 'editor_boilerplate_only' : null,
    }
  }

  function hasFoldedEditorNode(root) {
    return Boolean(root?.querySelector?.('[class*="folding-collapsed"],[class*="fold-placeholder"],[class*="collapsed-fold"],[class*="hidden-range"],[aria-label*="folded" i],[title*="folded" i]'))
  }

  function normalizeEditorCode(value) {
    const lines = String(value ?? '')
      .replace(/\r\n?/g, '\n')
      .split('\n')
      .map((line) => line.replace(/^\s*\d+\s+(?=\S)/, ''))
    return sanitizeCode(lines.join('\n'))
  }

  function looksLikeCode(value) {
    const code = sanitizeCode(value, 1200)
    return /(^|\n)\s*(?:def|class|function|#include|using\s+namespace|int\s+main\s*\(|import|from|public\s+class|static\s+void\s+main|using\s+System|namespace\s+\w+|package\s+main|func\s+\w+|fn\s+main|pub\s+fn|fun\s+main|object\s+\w+|public:|private:|protected:|return(?:\s+[\w({["']|$)|print\s*\(|System\.out|console\.log|if\s+__name__|(?:const|let|var)\s+\w+|[A-Za-z_]\w*\s*=\s*input\s*\(|[A-Za-z_]\w*\s+\w+\s*\([^)]*\)\s*\{)/m.test(code)
  }

  function options(root) {
    const containers = Array.from(root.querySelectorAll('fieldset,[role="radiogroup"],[role="listbox"],ul,ol'))
      .filter(isVisible)
      .filter((node) => !node.closest('nav,header,footer,aside,[role="toolbar"],[role="navigation"],[role="tablist"]'))
      .slice(0, 80)
    const radioNames = new Map()
    for (const input of Array.from(root.querySelectorAll('input[type="radio"],input[type="checkbox"]'))) {
      if (!isVisible(input) || input.closest('nav,header,footer,aside,[role="toolbar"],[role="navigation"],[role="tablist"]')) continue
      const name = input.getAttribute('name') || ''
      if (!name) continue
      radioNames.set(name, [...(radioNames.get(name) || []), input])
    }
    const nameGroups = [...radioNames.values()].map((inputs) => inputs.map((input) => input.closest('label') || input.parentElement).filter(Boolean))
    const parentLabelGroups = [...new Set(Array.from(root.querySelectorAll('label input[type="radio"],label input[type="checkbox"]'))
      .map((input) => input.closest('label')?.parentElement)
      .filter(Boolean))]
      .map((parent) => Array.from(parent.children || []).filter((node) => node.matches?.('label') && isVisible(node)))
    const groups = [
      ...containers.map((node) => ({
        options: optionGroupFromNodes(Array.from(node.querySelectorAll('label,li,[role="option"]')).filter(isVisible)),
        relationship: node.matches?.('fieldset,[role="radiogroup"]') ? 'strong' : 'explicit',
      })),
      ...nameGroups.map((nodes) => ({ options: optionGroupFromNodes(nodes), relationship: 'strong' })),
      ...parentLabelGroups.map((nodes) => ({ options: optionGroupFromNodes(nodes), relationship: 'explicit' })),
    ]
    const best = groups
      .filter((group) => isValidAssociatedOptionGroup(group.options, group.relationship))
      .map((group) => group.options)
      .sort((a, b) => b.length - a.length)[0]
    return (best || []).slice(0, LIMITS.maxOptions)
  }

  function optionGroupFromNodes(nodes) {
    return dedupeOptions(nodes
      .filter((node) => !node.querySelector?.('button,select,option'))
      .map((node, index) => ({
        ...normalizeOption(node.textContent, index),
        input_present: Boolean(node.querySelector?.('input[type="radio"],input[type="checkbox"]')),
        role_option: node.getAttribute?.('role') === 'option',
      }))
      .filter((option) => option.text && !isActionOrControlText(option.text) && !isQuestionLikeOptionText(option.label_explicit ? `${option.label}. ${option.text}` : option.text)))
  }

  function isValidAssociatedOptionGroup(group, relationship = 'explicit') {
    if (!Array.isArray(group) || group.length < 2) return false
    const distinctTexts = new Set(group.map((option) => option.text.toLowerCase()))
    if (distinctTexts.size < 2) return false
    if (relationship === 'strong' && group.some((option) => option.input_present || option.role_option)) return true
    const explicitLabels = group.filter((option) => option.label_explicit).map((option) => option.label)
    return explicitLabels.length >= 2 && explicitLabels.every((label) => /^[a-z]$|^\d+$/i.test(label))
  }

  function normalizeOption(value, index) {
    const text = sanitizeText(value, 320).replace(/^option\s*/i, '')
    const match = /^([a-z0-9]+)[).:-]\s*(.*)$/i.exec(text)
    return { label: match ? match[1] : null, text: match ? match[2] : text, label_explicit: Boolean(match), fallback_index: index }
  }

  function isQuestionLikeOptionText(text) {
    const match = /^\s*\d+[).:-]\s*(.+)/i.exec(sanitizeText(text, 320))
    return Boolean(match && (/\?\s*$/.test(match[1]) || /^(what|which|why|how|identify|if|when|where)\b/i.test(match[1])))
  }

  function dedupeOptions(entries) {
    const seen = new Set()
    return entries.filter((option) => {
      const key = `${option.label || option.fallback_index}:${option.text}`.toLowerCase()
      if (!option.text || seen.has(key)) return false
      seen.add(key)
      return true
    })
  }

  function isActionOrControlText(text) {
    return /\b(run code|submit|upload|custom input|language|editorial|solutions?|submissions?|login|sign up|filter|sort|next|previous|profile|settings)\b/i.test(sanitizeText(text, 320))
  }

  function examples(root) {
    return limitExamples(dedupeExamples(Array.from(root.querySelectorAll('[data-section*="example"],[class*="example"],[class*="sample"]'))
      .filter(isVisible)
      .flatMap((node) => parseExamples(visibleText(node), parseExampleHeading(nodeLabel(node) || headingText(node))))
      .filter(Boolean)))
  }

  function parseExamples(text, metadata = parseExampleHeading(null)) {
    const safe = sanitizeTextPreserveTabs(text, LIMITS.maxSectionTextLength)
    if (!safe || isRuntimeTestPanelText(`${metadata.label || ''}\n${safe}`)) return []
    const meta = metadata || parseExampleHeading(null)
    const tableItems = examplesFromTableText(safe, meta)
    if (tableItems.length) {
      recordRawExampleCandidates(tableItems.length)
      return tableItems
    }
    const blocks = semanticExampleBlocks(safe, meta)
    recordRawExampleCandidates(blocks.filter((block) => block.role !== 'example_group').length || blocks.length)
    return groupSemanticExampleBlocks(blocks, meta)
  }

  function examplesFromTableText(text, metadata = parseExampleHeading(null)) {
    if (!text.includes('\t')) return []
    const rows = text.split('\n').map((line) => line.split('\t').map((cell) => sanitizeText(cell, 400)).filter(Boolean)).filter((row) => row.length >= 2)
    if (rows.length < 2) return []
    const header = rows[0].map((cell) => cell.toLowerCase())
    const inputIndex = header.findIndex((cell) => /^(input|stdin|standard input)$/.test(cell))
    const outputIndex = header.findIndex((cell) => /^(output|expected output|standard output)$/.test(cell))
    const functionIndex = header.findIndex((cell) => /^(function|parameter|method|variable)$/.test(cell))
    const kind = metadata.kind !== 'unknown' ? metadata.kind : 'sample'
    if (inputIndex >= 0 && outputIndex >= 0) {
      return rows.slice(1).map((row, index) => normalizeExampleItem({
        kind,
        label: metadata.label || groupExampleLabel({ kind, label: kind === 'sample' ? 'Sample' : 'Example', index: index + 1 }),
        index: Number.isInteger(metadata.index) ? metadata.index : index + 1,
        input: row[inputIndex] || null,
        output: row[outputIndex] || null,
        explanation: null,
        text: null,
      })).filter(hasExampleContent)
    }
    if (inputIndex >= 0 && functionIndex >= 0) {
      return [normalizeExampleItem({
        ...exampleBase({ ...metadata, kind, label: metadata.label || (kind === 'sample' ? 'Sample' : 'Example') }),
        input: rows.slice(1).map((row) => row[inputIndex]).filter(Boolean).join('\n'),
      })].filter(hasExampleContent)
    }
    return []
  }

  function semanticExampleBlocks(text, metadata = parseExampleHeading(null)) {
    const blocks = []
    const meta = metadata || parseExampleHeading(null)
    if (meta.part) {
      return [{ role: `example_${meta.part}`, ...meta, text: cleanExamplePartText(text), order: 0 }]
    }
    if (meta.kind !== 'unknown') {
      blocks.push({ role: 'example_group', ...meta, text: '', order: 0 })
    }
    const pattern = /(^|\n)[ \t]*((?:sample|example)[ \t]+(?:input|output|explanation)|(?:official[ \t]+)?test case(?:[ \t]+(?:input|output|explanation))?|expected output|standard input|standard output|stdin|examples?|samples?|input|output|explanation|notes)(?:[ \t]*#?[ \t]*(\d+))?[ \t]*:?[ \t]*/gi
    const matches = [...text.matchAll(pattern)]
    if (!matches.length) {
      blocks.push({ role: 'example_text', ...meta, text, order: blocks.length })
      return blocks
    }
    const firstIndex = matches[0].index ?? 0
    const preamble = sanitizeText(text.slice(0, firstIndex), LIMITS.maxSectionTextLength)
    if (preamble) {
      blocks.push({ role: 'example_text', ...meta, text: preamble, order: blocks.length })
    }
    matches.forEach((match, index) => {
      const rawLabel = sanitizeText(`${match[2]}${match[3] ? ` ${match[3]}` : ''}`, 120)
      const heading = parseSemanticHeading(rawLabel, { insideExamples: true })
      const start = (match.index ?? 0) + match[0].length
      const end = index + 1 < matches.length ? matches[index + 1].index : text.length
      const value = cleanExamplePartText(text.slice(start, end))
      if (heading.role === 'noise' || heading.role === 'runtime_input' || heading.role === 'runtime_output') return
      blocks.push({ ...heading, text: value, order: blocks.length })
    })
    return blocks
  }

  function cleanExamplePartText(value) {
    return sanitizeTextPreserveTabs(
      String(value || '').split(/\n\s*(?=(?:function|def|class|public|private|protected|#include|using namespace|int main)\b)/i)[0],
      LIMITS.maxSectionTextLength
    )
  }

  function parseSemanticHeading(label, context = {}) {
    const raw = sanitizeText(label || '', 120).replace(/:$/, '') || null
    const lower = (raw || '').toLowerCase()
    if (isRuntimeTestPanelText(raw)) return { role: lower.includes('output') || lower.includes('result') || lower.includes('console') ? 'runtime_output' : 'runtime_input', kind: 'unknown', label: raw, index: null, part: null }
    if (/^(input format|parameters|arguments|function parameters)$/.test(lower)) return { role: 'global_input_format', kind: 'unknown', label: raw, index: null, part: null }
    if (/^(output format|print|prints|return value|returns|expected return)$/.test(lower)) return { role: 'global_output_format', kind: 'unknown', label: raw, index: null, part: null }
    const meta = parseExampleHeading(raw)
    if (/^(examples?|samples?|(?:official\s+)?test case(?:\s+\d+)?)$/.test(lower)) return { role: 'example_group', ...meta }
    if (meta.part) return { role: `example_${meta.part}`, ...meta }
    if (context.insideExamples && /^(stdin|standard input|input)$/.test(lower)) return { role: 'example_input', kind: meta.kind, label: raw, index: meta.index, part: 'input' }
    if (context.insideExamples && /^(standard output|output|expected output)$/.test(lower)) return { role: 'example_output', kind: meta.kind || 'unknown', label: raw, index: meta.index, part: 'output' }
    if (context.insideExamples && /^(explanation|notes)$/.test(lower)) return { role: 'example_explanation', kind: meta.kind, label: raw, index: meta.index, part: 'explanation' }
    return { role: 'unknown', kind: meta.kind, label: raw, index: meta.index, part: meta.part }
  }

  function groupSemanticExampleBlocks(blocks, metadata = parseExampleHeading(null)) {
    const items = []
    let current = null
    const start = (block) => {
      const inheritedGroup = metadata.kind !== 'unknown' && /^(input|output|explanation|notes)$/i.test(block.label || '')
      return exampleBase({
        ...metadata,
        ...block,
        kind: block.kind === 'unknown' && metadata.kind !== 'unknown' ? metadata.kind : block.kind,
        label: inheritedGroup ? groupExampleLabel(metadata) : groupExampleLabel(block) || groupExampleLabel(metadata),
        part: inheritedGroup ? null : block.part,
      })
    }
    const finish = () => {
      if (current && hasExampleContent(current)) items.push(normalizeExampleItem(current))
      current = null
    }
    for (const block of blocks) {
      if (block.role === 'global_input_format' || block.role === 'global_output_format' || block.role === 'noise') {
        finish()
        continue
      }
      if (block.role === 'example_group') {
        finish()
        current = start(block)
        if (block.text) current.text = block.text
        continue
      }
      if (!current) current = start(block)
      const field = block.role.replace(/^example_/, '')
      if (['input', 'output'].includes(field) && current[field] && (current.input || current.output)) {
        finish()
        current = start(block)
      }
      if (['input', 'output', 'explanation', 'text'].includes(field) && block.text) {
        current[field] = current[field] && current[field] !== block.text
          ? sanitizeText(`${current[field]}\n${block.text}`, LIMITS.maxSectionTextLength)
          : block.text
        if (field !== 'text') current.text = null
      }
    }
    finish()
    return items.filter(hasExampleContent)
  }

  function hasExampleContent(item) {
    return Boolean(item?.input || item?.output || item?.explanation || item?.text)
  }

  function parseExampleHeading(label) {
    const raw = sanitizeText(label || '', 120).replace(/:$/, '') || null
    const lower = (raw || '').toLowerCase()
    let kind = 'unknown'
    if (/^samples?\b/.test(lower)) kind = 'sample'
    else if (/^examples?\b|^expected output\b/.test(lower)) kind = 'example'
    else if (/^test case\b|^official test case\b/.test(lower)) kind = 'test_case'
    let part = null
    if (/\binput\b/.test(lower)) part = 'input'
    else if (/\boutput\b|^expected output\b/.test(lower)) part = 'output'
    else if (/\bexplanation\b/.test(lower)) part = 'explanation'
    const indexMatch = /(?:sample|example|test case|input|output|explanation)\s+(\d+)\b/i.exec(raw || '')
    const index = indexMatch ? Number(indexMatch[1]) : null
    return { kind, label: raw, index: Number.isInteger(index) ? index : null, part }
  }

  function exampleBase(metadata) {
    return {
      kind: metadata.kind || 'unknown',
      label: groupExampleLabel(metadata),
      index: Number.isInteger(metadata.index) ? metadata.index : null,
      input: null,
      output: null,
      explanation: null,
      text: null,
    }
  }

  function groupExampleLabel(metadata) {
    if (!metadata?.label) return null
    if (!metadata.part) return metadata.label
    const prefix = metadata.kind === 'sample' ? 'Sample' : metadata.kind === 'example' ? 'Example' : metadata.kind === 'test_case' ? 'Test Case' : metadata.label
    return metadata.kind === 'unknown' ? metadata.label : `${prefix}${Number.isInteger(metadata.index) ? ` ${metadata.index}` : ''}`
  }

  function normalizeExampleItem(item) {
    return {
      kind: item.kind || 'unknown',
      label: item.label || null,
      index: Number.isInteger(item.index) ? item.index : null,
      input: item.input ? normalizeExampleInput(item.input) : null,
      output: item.output || null,
      explanation: item.explanation || null,
      text: item.text || null,
    }
  }

  function mergeExamples(existing, incoming) {
    return dedupeExamples(attachStandaloneExplanations([...(existing || []), ...(incoming || [])]))
  }

  function attachStandaloneExplanations(items) {
    const result = []
    let attachedOrDropped = 0
    for (const item of items.map(normalizeExampleItem)) {
      if (isStandaloneExplanation(item)) {
        const target = findExplanationTarget(result, item)
        if (target) {
          if (!target.explanation) target.explanation = item.explanation
          attachedOrDropped += 1
          continue
        }
      }
      result.push(item)
    }
    attachStandaloneExplanations.lastAttachedOrDroppedCount = attachedOrDropped
    return result
  }

  function isStandaloneExplanation(item) {
    return item.kind === 'unknown' && item.explanation && !item.input && !item.output && !item.text
  }

  function findExplanationTarget(items, explanation) {
    if (Number.isInteger(explanation.index)) {
      const indexed = [...items].reverse().find((item) => item.index === explanation.index && item.kind !== 'unknown')
      if (indexed) return indexed
    }
    return [...items].reverse().find((item) => item.kind !== 'unknown' && (item.input || item.output || item.text))
  }

  function dedupeExamples(exampleItems) {
    const seen = new Set()
    const merged = []
    for (const example of exampleItems) {
      const item = normalizeExampleItem(example)
      const mergeKey = exampleMergeKey(item)
      const existing = mergeKey ? merged.find((entry) => exampleMergeKey(entry) === mergeKey) : null
      if (existing && canMergeExample(existing, item)) {
        existing.input = existing.input || item.input
        existing.output = existing.output || item.output
        existing.explanation = existing.explanation || item.explanation
        existing.text = existing.text || item.text
        continue
      }
      merged.push(item)
    }
    const withoutRepresentedUnknowns = removeRepresentedUnknownExamples(merged)
    const representedRemoved = merged.length - withoutRepresentedUnknowns.length
    let exactRemoved = 0
    const final = withoutRepresentedUnknowns.filter((item) => {
      const key = JSON.stringify([item.kind, item.index, item.input, item.output, item.explanation, item.text])
      if (seen.has(key)) {
        exactRemoved += 1
        return false
      }
      seen.add(key)
      return true
    })
    const duplicateCount = Math.max(0, representedRemoved + exactRemoved + Number(attachStandaloneExplanations.lastAttachedOrDroppedCount || 0))
    exampleDiagnosticsState.duplicateCount += duplicateCount
    dedupeExamples.lastDuplicateCount = duplicateCount
    return final
  }

  function removeRepresentedUnknownExamples(items) {
    const structuredBlobs = items.filter((item) => item.kind !== 'unknown').map(exampleBlob).filter(Boolean)
    return items.filter((item) => {
      if (item.kind !== 'unknown') return true
      const blob = exampleBlob(item)
      if (!blob) return false
      return !structuredBlobs.some((structured) => structured.includes(blob) || blob.includes(structured))
    })
  }

  function exampleBlob(item) {
    return sanitizeText([item.input, item.output, item.explanation, item.text].filter(Boolean).join('\n'), LIMITS.maxSectionTextLength).toLowerCase()
  }

  function exampleMergeKey(item) {
    if (item.kind === 'unknown' || !item.label) return null
    return `${item.kind}:${item.index ?? 'none'}:${item.label.toLowerCase()}`
  }

  function canMergeExample(a, b) {
    return ['input', 'output', 'explanation', 'text'].every((key) => !a[key] || !b[key] || a[key] === b[key])
  }

  function limitExamples(exampleItems) {
    limitExamples.lastTruncated = exampleItems.length > LIMITS.maxExamples
    if (limitExamples.lastTruncated) exampleDiagnosticsState.truncated = true
    return exampleItems.slice(0, LIMITS.maxExamples)
  }

  function collectExampleDiagnostics(examples = []) {
    const unknownCount = examples.filter((example) => example?.kind === 'unknown').length
    const orphanPartCount = examples.filter((example) => example?.kind === 'unknown' && (example?.input || example?.output || example?.explanation) && !example?.text).length
    const duplicateCount = Number(exampleDiagnosticsState.duplicateCount || dedupeExamples.lastDuplicateCount || 0)
    return {
      rawCount: Math.max(Number(exampleDiagnosticsState.rawCandidateCount || 0), examples.length + duplicateCount),
      finalCount: examples.length,
      duplicateCount,
      unknownCount,
      orphanPartCount,
      runtimePanelExcludedCount: 0,
      warnings: [
        unknownCount ? 'unknown_examples_detected' : null,
        orphanPartCount ? 'orphan_example_part' : null,
        exampleDiagnosticsState.truncated && examples.length >= LIMITS.maxExamples ? 'examples_truncated' : null,
      ].filter(Boolean),
    }
  }

  function resetExampleDiagnostics() {
    exampleDiagnosticsState.rawCandidateCount = 0
    exampleDiagnosticsState.duplicateCount = 0
    exampleDiagnosticsState.truncated = false
    exampleDiagnosticsState.sectionBoundaryStopCount = 0
    exampleDiagnosticsState.editorSectionExcludedCount = 0
    attachStandaloneExplanations.lastAttachedOrDroppedCount = 0
    dedupeExamples.lastDuplicateCount = 0
    limitExamples.lastTruncated = false
  }

  function recordRawExampleCandidates(count) {
    exampleDiagnosticsState.rawCandidateCount += Math.max(0, Number(count) || 0)
  }

  function normalizeExampleInput(value) {
    const text = sanitizeText(value, LIMITS.maxSectionTextLength)
    const lines = text.split('\n').map((line) => line.trim()).filter(Boolean)
    const headerIndex = lines.findIndex((line) => /\b(?:stdin|standard input|input)\b/i.test(line) && /\b(?:function|parameter|method|variable)\b/i.test(line))
    if (headerIndex < 0) return text
    const data = lines.slice(headerIndex + 1)
      .filter((line) => !/^-{2,}(?:\s+-{2,})*$/.test(line))
      .map((line) => {
        const columns = line.split(/\s{2,}|\t+/).map((part) => part.trim()).filter(Boolean)
        return (columns[0] || '').split(/\s+[A-Za-z_]\w*\s*=/)[0].trim()
      })
      .filter(Boolean)
    return data.length ? sanitizeText(data.join('\n'), LIMITS.maxSectionTextLength) : text
  }

  function headingText(node) {
    return node?.querySelector?.('h1,h2,h3,h4,h5,h6,strong,b,dt')?.textContent || ''
  }

  function isRuntimeTestPanelText(value) {
    return /\b(custom input|test against custom input|your input|test input|run input|testcase input|test result|run result|your output|console(?: output)?|compilation output|debug output|standard error|failed test|passed test|hidden testcase|run code|submit)\b/i.test(sanitizeText(value, 500))
  }

  function visualContext(root) {
    const visualPresent = Array.from(root.querySelectorAll('img,figure,svg,canvas')).some(isMeaningfulVisualElement)
    const text = visibleText(root)
    const diagram = visualPresent && visualDependencyPattern(text)
    const chart = visualPresent && /\b(shown in|based on|inspect|interpret|refer to|from)\b.{0,60}\b(chart|graph)\b|\b(chart|graph)\b.{0,60}\b(shown|below|above|figure|image)\b/i.test(text)
    return { visual_present: visualPresent, diagram_present: diagram, chart_present: chart, image_context_required: diagram || chart, visual_description: null }
  }

  function visualDependencyPattern(text) {
    return /\b(shown in|shown below|shown above|in the image|from the image|based on the image|using the diagram|study the diagram|refer to the figure|given figure|following figure|diagram below|architecture diagram|circuit diagram|study the circuit|tree shown|graph shown|chart shown|inspect the chart|interpret the chart|identify from the image)\b/i.test(text || '')
  }

  function isMeaningfulVisualElement(node) {
    if (!isVisible(node)) return false
    if (node.closest('nav,header,footer,aside,[role="toolbar"],[role="navigation"],button,[aria-hidden="true"],[role="presentation"],[class*="logo"],[class*="avatar"],[class*="icon"]')) return false
    const tag = (node.tagName || '').toLowerCase()
    if (tag === 'canvas' && node.closest('[class*="editor"],[class*="code"],[class*="monaco"],[class*="minimap"],textarea,pre,code')) return false
    const width = Number(node.getAttribute?.('width') || node.clientWidth || 0)
    const height = Number(node.getAttribute?.('height') || node.clientHeight || 0)
    if (width && height && width <= 48 && height <= 48) return false
    return true
  }

  function titleFrom(root) {
    const candidates = Array.from(root.querySelectorAll('h1,h2,h3,h4,[role="heading"],[aria-level],div,p,span,strong,b'))
      .filter(isVisible)
      .slice(0, 80)
      .map((node, index) => {
        const text = sanitizeText(node.textContent || '', LIMITS.maxTitleLength)
        if (labelKey(text)) return null
        const tag = (node.tagName || '').toLowerCase()
        const ariaLevel = Number(node.getAttribute?.('aria-level') || 0)
        const headingLike = /^h[1-4]$/.test(tag) || node.getAttribute?.('role') === 'heading' || ariaLevel
        const rank = tag === 'h1' || ariaLevel === 1 ? 1 : tag === 'h2' || ariaLevel === 2 ? 2 : headingLike ? 3 : 5
        return { text, rank, index }
      })
      .filter(Boolean)
      .filter((candidate) => candidate.rank < 5 || isNumberedProblemTitle(candidate.text))
    return rankTitleCandidates(candidates)?.text || cleanDocumentTitle(document.title)
  }

  function rankTitleCandidates(candidates) {
    return candidates
      .map((candidate) => ({ ...candidate, text: sanitizeText(candidate.text, LIMITS.maxTitleLength) }))
      .filter((candidate) => candidate.text && candidate.text.length <= LIMITS.maxTitleLength)
      .map((candidate) => ({ ...candidate, score: titleScore(candidate) }))
      .filter((candidate) => candidate.score > 0)
      .sort((a, b) => b.score - a.score || a.index - b.index || a.text.length - b.text.length)[0] || null
  }

  function titleScore(candidate) {
    const text = sanitizeText(candidate.text, LIMITS.maxTitleLength)
    const lower = text.toLowerCase()
    let score = 0
    score += Math.max(0, 8 - candidate.rank * 2)
    if (candidate.index < 8) score += 3
    if (candidate.index < 24) score += 1
    if (isNumberedProblemTitle(text)) score += 6
    if (/^[A-Z0-9][\w\s:'().-]{2,70}$/.test(text)) score += 2
    if (text.length <= 70) score += 2
    if (/[.!?]$/.test(text)) score -= 6
    if (/\b(think of it|let'?s|you are|how would|explanation|example|sample|note|description|problem|task|input format|output format)\b/i.test(lower)) score -= 4
    if (/^(description|problem|task|example|explanation|input format|output format)$/i.test(text)) score -= 8
    if (text.length > 90) score -= 5
    return score
  }

  function isNumberedProblemTitle(text) {
    return /^(?:\d+\s*[.)-]\s+|(?:question|problem|task)\s+\d+\s*:\s+)[A-Z][\w\s:'().-]{2,}$/i.test(sanitizeText(text, LIMITS.maxTitleLength))
  }

  function cleanDocumentTitle(title) {
    return sanitizeText(title, LIMITS.maxTitleLength).split(/\s[-|–—]\s/).map((part) => part.trim()).filter(Boolean)[0] || null
  }

  function detectType(statement, sectionMap, code, optionList, visual) {
    const text = `${statement}\n${sectionMap.function_description || ''}`.toLowerCase()
    const codingText = /\b(given|function|class|stdin|stdout|write a program|write code|implement|implement the solution|implement the function|implement the method|complete the function|complete the code|complete the solution|solve this problem|solve this challenge|provide an implementation|process the input|produce the output|return the required result|convert|find|calculate|compute|determine|construct|build|create|modify|remove|generate|sort|merge|reverse|rotate)\b/i.test(text)
    if (optionList.length >= 2) return 'mcq'
    if (code && /\b(debug|fix|bug|correct|error|failing|unexpected)\b/i.test(text)) return 'debugging'
    if (code && /\b(what\s+(?:is\s+)?(?:the\s+)?output|what\s+.*prints?|printed by|prints? the following|displayed by)\b/i.test(text)) return 'output_prediction'
    if (code) return 'coding'
    if (code || sectionMap.input_format || sectionMap.output_format || codingText) return 'coding'
    if (visual.image_context_required) return 'diagram'
    if (/\?\s*$|^(what|why|how|which|explain|describe|define)\b/i.test(statement || '')) return 'technical'
    if (statement) return 'general'
    return 'unknown'
  }

  function evaluate(questionType, statement, sectionMap, code, optionList, signature, visual) {
    const missing = []
    const warnings = []
    const readable = Boolean(statement && statement.length >= 12)
    if (questionType === 'mcq') {
      if (!readable) missing.push('statement')
      if (optionList.length < 2) missing.push('options')
    } else if (questionType === 'debugging') {
      if (!readable) missing.push('debug_instruction')
      if (!code) missing.push('code')
    } else if (questionType === 'output_prediction') {
      if (!readable) missing.push('output_instruction')
      if (!code) missing.push('code')
    } else if (questionType === 'coding') {
      if (!readable && !(code && signature)) missing.push('statement')
      if (sectionMap.function_description && !code && !signature) warnings.push('code_context_partially_extracted')
    } else if (questionType === 'diagram' || questionType === 'chart') {
      if (!readable) missing.push('statement')
      if (visual.image_context_required) warnings.push('visual_context_required')
    } else if (questionType === 'technical' || questionType === 'general') {
      if (!readable) missing.push('statement')
    } else if (!readable) {
      missing.push('statement')
    }
    return { complete: missing.length === 0, missing, warnings: missing.length ? [...warnings, 'extraction_incomplete'] : warnings }
  }

  function confidence({ complete, questionType, statement, title, sectionMap, code, optionList, visual, rootSelection, warnings = [] }) {
    let score = 0.35
    if (complete) score += 0.2
    if (statement) score += 0.15
    if (title) score += 0.08
    if (sectionMap.input_format || sectionMap.output_format || sectionMap.constraints || sectionMap.examples?.length) score += 0.08
    if (code || optionList.length >= 2) score += 0.1
    if (rootSelection.score >= 8) score += 0.08
    if (questionType === 'unknown') score -= 0.18
    if (rootSelection.ambiguous) score -= 0.18
    if (visual.image_context_required) score -= 0.1
    if (warnings.length) score -= Math.min(0.12, warnings.length * 0.03)
    const cap = warnings.length ? 0.97 : 0.99
    return Math.max(0, Math.min(cap, Number(score.toFixed(2))))
  }

  function findSignature(code) {
    const safe = code || ''
    const anchored = (/^\s*((?:function|def|func|fn|fun)\s+[a-zA-Z_][\w]*\s*\([^)]*\)|(?:public\s+)?static\s+void\s+main\s*\([^)]*\)|int\s+main\s*\([^)]*\)|(?:public|private|protected)?\s*(?:static\s+)?[a-zA-Z_][\w:<>,\[\]\s*&]*\s+[a-zA-Z_][\w]*\s*\([^)]*\)|[a-zA-Z_][\w]*\s*=\s*\([^)]*\)\s*=>)/m.exec(safe) || [])[1]
    const inline = (/\b((?!(?:if|for|while|switch|catch|return)\s*\()[A-Za-z_][\w:<>,\[\]\s*&]*\s+[A-Za-z_]\w*\s*\([^;{}]*\))\s*(?:\{|;|=>)/.exec(safe) || [])[1]
    return sanitizeText(anchored || inline || '', 240) || null
  }

  function findClassName(code) {
    return sanitizeText((/class\s+([A-Za-z_][\w]*)/m.exec(code || '') || [])[1] || '', 120) || null
  }

  function languageCandidate(code) {
    if (!code) return null
    if (/^\s*def\s+/m.test(code)) return 'python'
    if (/\bpublic\s+class\b|\bSystem\.out\b/.test(code)) return 'java'
    if (/\b#include\b|std::/.test(code)) return 'cpp'
    if (/\bfunction\b|=>|\bconst\b|\blet\b/.test(code)) return 'javascript'
    return null
  }

  function splitLines(text) {
    return sanitizeText(text, LIMITS.maxSectionTextLength).split(/(?:\n|;|\.\s+)/).map((line) => sanitizeText(line, 280)).filter(Boolean)
  }

  function emptyConstraintInfo() {
    return { items: [], text: '', candidateCount: 0, truncated: false, warning: null, source: 'none', codeLikeRejectedCount: 0 }
  }

  function extractConstraints(root, labelledText = '', code = '') {
    const chunks = []
    if (labelledText) chunks.push(labelledText)
    for (const labelNode of Array.from(root?.querySelectorAll?.('h1,h2,h3,h4,h5,h6,strong,b,dt,p,div,span,[aria-label]') || []).filter(isVisible).slice(0, 120)) {
      const label = nodeLabel(labelNode)
      if (!/^(constraints|limits)$/i.test(sectionLabelPrefix(label))) continue
      chunks.push(collectLabelledText(labelNode, 'constraints'))
    }
    const labelled = finalizeConstraints(chunks, 'labelled')
    if (labelled.items.length) return labelled
    const fallback = finalizeConstraints([visibleTextWithoutEditorRuntime(root).replace(code || '', '')], chunks.length ? 'labelled_plus_fallback' : 'fallback_clean_problem_text')
    return fallback
  }

  function visibleTextWithoutEditorRuntime(root) {
    if (!root?.cloneNode) return ''
    const clone = root.cloneNode(true)
    clone.querySelectorAll('script,style,noscript,template,nav,aside,footer,header,[hidden],[aria-hidden="true"],textarea,pre,code,[contenteditable="true"],[role="textbox"],[aria-multiline="true"],[class*="editor"],[class*="code"],[class*="console"],[class*="testcase"],[class*="solution"],[class*="editorial"],[class*="discussion"]').forEach((entry) => entry.remove())
    removeConstraintFallbackNoiseSections(clone)
    return sanitizeTextPreserveTabs(clone.textContent || '', LIMITS.maxTextLength)
  }

  function removeConstraintFallbackNoiseSections(root) {
    const labels = Array.from(root.querySelectorAll?.('h1,h2,h3,h4,h5,h6,strong,b,dt,p,div,span,[aria-label]') || [])
    for (const labelNode of labels) {
      const label = sanitizeText(nodeLabel(labelNode), 80).replace(/:$/, '')
      if (!/^(sample(?: input| output| explanation|\s+\d+)?|samples|example(?: input| output| explanation|\s+\d+)?|examples|custom input|test result|run output|console|editorial|solution|discussion)$/i.test(label)) continue
      let node = labelNode
      while (node) {
        const next = node.nextElementSibling
        node.remove?.()
        if (!next || labelKey(nodeLabel(next))) break
        node = next
      }
    }
  }

  function finalizeConstraints(chunks, source = 'unknown') {
    const rawCandidates = chunks.flatMap((chunk) => constraintCandidatesFromText(chunk))
    const labelledSource = source === 'labelled'
    let codeLikeRejectedCount = 0
    const candidates = rawCandidates.filter((candidate) => {
      if (!isConstraintNoiseLine(candidate)) return true
      codeLikeRejectedCount += 1
      return false
    })
    const seen = new Set()
    const items = []
    for (const candidate of candidates) {
      const normalized = normalizeConstraintLine(candidate)
      if (!normalized || !(labelledSource ? isLabelledConstraintLine(normalized) : isConstraintLine(normalized))) continue
      const key = normalized.toLowerCase()
      if (seen.has(key)) continue
      const representedIndex = items.findIndex((item) => item.toLowerCase().includes(key) || key.includes(item.toLowerCase()))
      if (representedIndex >= 0) {
        if (normalized.length < items[representedIndex].length) {
          seen.delete(items[representedIndex].toLowerCase())
          items[representedIndex] = normalized
          seen.add(key)
        }
        continue
      }
      seen.add(key)
      items.push(normalized)
    }
    const truncated = items.length > LIMITS.maxConstraints
    const limited = items.slice(0, LIMITS.maxConstraints)
    return {
      items: limited,
      text: limited.join('\n'),
      candidateCount: rawCandidates.length,
      truncated,
      warning: truncated ? 'constraints_truncated' : null,
      source,
      codeLikeRejectedCount,
    }
  }

  function isLabelledConstraintLine(line) {
    const safe = sanitizeText(line, 280)
    if (!safe || /^(constraints|limits)$/i.test(safe) || isConstraintNoiseLine(safe)) return false
    return isConstraintLine(safe) ||
      /\b(?:contains?\s+only|consists?\s+only|only\s+(?:lowercase|uppercase|english|digits?)|guaranteed|does not exceed|at most|at least|between|valid character|valid pair|total number|sum of)\b/i.test(safe)
  }

  function constraintCandidatesFromText(text) {
    const safe = sanitizeTextPreserveTabs(text, LIMITS.maxSectionTextLength)
    return safe
      .split(/\n|;/)
      .flatMap((line) => {
        const columns = line.split('\t').map((part) => sanitizeText(part, 280)).filter(Boolean)
        if (columns.length > 1) {
          const constraintColumns = columns.filter(isConstraintLine)
          return constraintColumns.length ? constraintColumns : [columns.join(' ')]
        }
        return [line]
      })
      .map((line) => sanitizeText(line, 280))
      .filter(Boolean)
  }

  function normalizeConstraintLine(line) {
    return sanitizeText(String(line || '')
      .replace(/^\s*(?:constraints|limits)\s*:\s*/i, '')
      .replace(/&lt;=/gi, '<=')
      .replace(/&gt;=/gi, '>=')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/[\u2070\u00B9\u00B2\u00B3\u2074-\u2079]/g, (digit) => ({ '\u2070': '^0', '\u00B9': '^1', '\u00B2': '^2', '\u00B3': '^3', '\u2074': '^4', '\u2075': '^5', '\u2076': '^6', '\u2077': '^7', '\u2078': '^8', '\u2079': '^9' }[digit] || digit))
      .replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]/g, (digit) => ({ '⁰': '^0', '¹': '^1', '²': '^2', '³': '^3', '⁴': '^4', '⁵': '^5', '⁶': '^6', '⁷': '^7', '⁸': '^8', '⁹': '^9' }[digit] || digit))
      .replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹]/g, (digit) => ({ '⁰': '^0', '¹': '^1', '²': '^2', '³': '^3', '⁴': '^4', '⁵': '^5', '⁶': '^6', '⁷': '^7', '⁸': '^8', '⁹': '^9' }[digit] || digit)), 280)
  }

  function isConstraintLine(line) {
    const safe = sanitizeText(line, 280)
    if (!safe || isConstraintNoiseLine(safe)) return false
    if (/[\u2264\u2265]/u.test(safe)) return true
    if (/[≤≥]/.test(safe)) return true
    return /(?:<=|>=|≤|≥|<|>)\s*[\w\d]/.test(safe) ||
      /\b[\w\]\)]+\s*(?:<=|>=|≤|≥|<|>)\s*[\d\w]/.test(safe) ||
      /\bbetween\s+\d+\b.+\b(?:and|to)\s+\d+/i.test(safe) ||
      /\bsum of\b.+\b(?:test cases|queries|values|n)\b/i.test(safe) ||
      /\btotal number of\b.+\b(?:queries|operations|test cases)\b/i.test(safe)
  }

  function isConstraintNoiseLine(line) {
    const safe = sanitizeText(line, 280)
    return /\b(sample input|sample output|example|custom input|test result|run output|your output|console|editorial|solution|discussion|run code|submit|time complexity|space complexity)\b/i.test(safe) ||
      /^\s*(?:return|if|else|for|while|def|class|function|const|let|var|int|long|float|double|public|private|protected|#include|using\s+namespace)\b/i.test(safe) ||
      /\b[A-Za-z_][\w:<>,\[\]\s*&]*\s+[A-Za-z_]\w*\s*\([^)]*\)\s*(?:\{|;|$)/.test(safe) ||
      /^\s*(?:public:|private:|protected:|};?|[{}])\s*$/.test(safe)
  }

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  async function readinessWarnings() {
    const started = performance.now()
    let previous = ''
    let stableCount = 0
    while (performance.now() - started < 800) {
      const current = visibleText(document.body)
      const editor = collectEditorEvidence(document.body)
      if (editor.codeAvailable || editor.editorTextAvailable) return []
      if (document.readyState === 'complete' && current && current === previous) {
        stableCount += 1
        if (stableCount >= 2) return []
      } else {
        stableCount = 0
      }
      previous = current
      await wait(120)
    }
    return document.readyState === 'complete' ? [] : ['dynamic_content_may_be_incomplete']
  }

  function extract(extraWarnings = []) {
    resetExampleDiagnostics()
    const rootSelection = selectRoot()
    const root = rootSelection.root || document.body
    const sectionMap = sections(root)
    const editorEvidence = collectEditorEvidenceWithFallback(root)
    const code = editorEvidence.code
    const constraintInfo = extractConstraints(root, sectionMap.constraints, code)
    sectionMap.constraints = constraintInfo.text
    const optionList = options(root)
    const detectedOptionCount = countDetectedOptionCandidates(root)
    const visual = visualContext(root)
    const title = titleFrom(root)
    const statement = sanitizeText((sectionMap.statement || sectionMap.function_description || visibleText(root)).replace(code, ''), LIMITS.maxTextLength) || null
    const cleanedQuestion = sanitizeText([
      title,
      statement,
      sectionMap.function_description,
      sectionMap.input_format,
      sectionMap.output_format,
      sectionMap.constraints,
      ...(sectionMap.examples || []).flatMap((example) => [example.input && `Input: ${example.input}`, example.output && `Output: ${example.output}`]),
    ].filter(Boolean).join('\n'), LIMITS.maxTextLength) || null
    const signature = findSignature(code)
    const questionType = detectType(statement, sectionMap, code, optionList, visual)
    const finalOptions = questionType === 'mcq' ? optionList : []
    const completeness = evaluate(questionType, statement, sectionMap, code, finalOptions, signature, visual)
    const exampleDiagnostics = collectExampleDiagnostics(sectionMap.examples)
    const warnings = [...new Set([
      ...extraWarnings,
      ...rootSelection.warnings,
      ...completeness.warnings,
      ...exampleDiagnostics.warnings,
      editorEvidence.warning,
      constraintInfo.warning,
      editorEvidence.codeMayBePartial ? 'editor_code_may_be_partial' : null,
    ].filter(Boolean))].slice(0, LIMITS.maxWarnings)
    return {
      question: {
        question_type: questionType,
        cleaned_question: cleanedQuestion,
        title,
        statement,
        function_description: sectionMap.function_description || null,
        input_format: sectionMap.input_format || null,
        output_format: sectionMap.output_format || null,
        constraints: constraintInfo.items,
        examples: sectionMap.examples || [],
        options: finalOptions,
        answer: { text: null, code: null, explanation: null },
        visual_context: visual,
        code_context: {
          selected_language: languageCandidate(code),
          language_source: code ? (editorEvidence.editorPresent ? 'visible_editor_code' : 'visible_code') : null,
          editor_present: editorEvidence.editorPresent,
          editor_text_available: editorEvidence.editorTextAvailable,
          editor_boilerplate_only: editorEvidence.editorBoilerplateOnly,
          starter_code: code || null,
          function_signature: signature,
          class_name: findClassName(code),
          editor_type: editorEvidence.editorType,
          code_extraction_method: editorEvidence.codeExtractionMethod,
          code_capture_scope: editorEvidence.codeAvailable ? 'visible_editor_dom' : null,
          code_may_be_partial: editorEvidence.codeMayBePartial,
          code_extraction_warning: editorEvidence.warning,
          editor_scope: editorEvidence.editorScope,
          platform_mode: null,
          submission_mode: null,
        },
      },
      extraction: {
        complete: completeness.complete,
        confidence: confidence({ complete: completeness.complete, questionType, statement, title, sectionMap, code, optionList: finalOptions, visual, rootSelection, warnings }),
        missing_sections: completeness.missing,
        warnings,
        candidate_count: rootSelection.candidateCount,
        selected_candidate_score: rootSelection.score,
        selection_strategy: rootSelection.strategy,
        valid_option_count: finalOptions.length,
        detected_option_count: detectedOptionCount,
        valid_mcq_group: questionType === 'mcq' && finalOptions.length >= 2,
        diagnostics: {
          ...rootSelection.diagnostics,
          editor_candidate_count: editorEvidence.editorRootCount,
          editor_present: editorEvidence.editorPresent,
          editor_type: editorEvidence.editorType,
          editor_code_available: editorEvidence.codeAvailable,
          editor_text_available: editorEvidence.editorTextAvailable,
          editor_boilerplate_only: editorEvidence.editorBoilerplateOnly,
          code_extraction_method: editorEvidence.codeExtractionMethod,
          code_line_count: editorEvidence.codeLineCount,
          code_length: editorEvidence.codeLength,
          code_may_be_partial: editorEvidence.codeMayBePartial,
          code_extraction_warning: editorEvidence.warning,
          editor_scope: editorEvidence.editorScope,
          raw_example_candidate_count: exampleDiagnostics.rawCount,
          final_example_count: exampleDiagnostics.finalCount,
          duplicate_example_count: exampleDiagnostics.duplicateCount,
          unknown_example_count: exampleDiagnostics.unknownCount,
          orphan_example_part_count: exampleDiagnostics.orphanPartCount,
          runtime_test_panel_excluded_count: exampleDiagnostics.runtimePanelExcludedCount,
          constraint_candidate_count: constraintInfo.candidateCount,
          final_constraint_count: constraintInfo.items.length,
          constraints_truncated: constraintInfo.truncated,
          constraint_source: constraintInfo.source,
          constraint_code_like_rejected_count: constraintInfo.codeLikeRejectedCount,
          section_boundary_stop_count: exampleDiagnosticsState.sectionBoundaryStopCount,
          editor_section_excluded_count: exampleDiagnosticsState.editorSectionExcludedCount,
        },
        status: rootSelection.ambiguous ? 'selection_required' : undefined,
      },
    }
  }

  function countDetectedOptionCandidates(root) {
    return Array.from(root.querySelectorAll('label,li,[role="option"]'))
      .filter(isVisible)
      .filter((node) => !node.closest('nav,header,footer,aside,[role="toolbar"],[role="navigation"],[role="tablist"]'))
      .filter((node) => {
        const text = node.textContent || ''
        return text && !isActionOrControlText(text) && !node.querySelector?.('button,select,option')
      })
      .length
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.protocol_version !== '1.0' || message?.type !== 'CONTENT_EXTRACT_PAGE') {
      return false
    }
    readinessWarnings()
      .then((warnings) => {
        sendResponse({
          protocol_version: '1.0',
          type: 'CONTENT_EXTRACTION_RESULT',
          message_id: message.message_id,
          operation_id: message.operation_id,
          request_id: message.request_id,
          requested_source: 'browser_extension',
          result: extract(warnings),
        })
      })
      .catch(() => {
        sendResponse({
          protocol_version: '1.0',
          type: 'CONTENT_EXTRACTION_ERROR',
          message_id: message.message_id,
          operation_id: message.operation_id,
          request_id: message.request_id,
          error: { code: 'extraction_failed', message: 'Content extraction failed.' },
        })
      })
    return true
  })
})()
