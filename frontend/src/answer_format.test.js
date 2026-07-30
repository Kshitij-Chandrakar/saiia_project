import assert from 'node:assert/strict'
import test from 'node:test'

import { groupConceptualAnswer, parseConceptualAnswer } from './answer_format.js'

test('normalizes inline conceptual bullets into a semantic list and example heading', () => {
  const blocks = parseConceptualAnswer(
    'Authentication confirms identity. - It checks credentials. - It protects accounts. - It blocks unknown users. Real-life example: A phone uses a fingerprint before opening banking apps.'
  )
  const groups = groupConceptualAnswer(blocks)

  assert.deepEqual(groups.map((group) => group.type), ['paragraph', 'list', 'heading', 'paragraph'])
  assert.equal(groups[1].items.length, 3)
  assert.equal(groups[2].text, 'Real-life example:')
})

test('keeps already spaced bullets as separate list items', () => {
  const blocks = parseConceptualAnswer(
    'An API lets applications exchange data.\n\n- It defines requests.\n\n- It returns responses.\n\n- It hides internal details.\n\nReal-life example:\n\nA food app sends an order to a restaurant through an API.'
  )
  const list = groupConceptualAnswer(blocks).find((group) => group.type === 'list')

  assert.deepEqual(list.items, [
    'It defines requests.',
    'It returns responses.',
    'It hides internal details.',
  ])
})

test('keeps multiline personal stories as paragraphs', () => {
  const blocks = parseConceptualAnswer(
    'My childhood was mostly made up of simple evenings outside with friends. We invented games, changed rules, and somehow took every tiny argument seriously.\n\nI was quiet around new people, but with close friends I became talkative and competitive. By the next evening, everyone would be back together as if nothing had happened.\n\nLooking back, I value how ordinary those days were.'
  )

  assert.deepEqual(blocks.map((block) => block.type), ['paragraph', 'paragraph', 'paragraph'])
})
