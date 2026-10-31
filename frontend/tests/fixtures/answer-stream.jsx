import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import OverlayWindow from '../../src/components/OverlayWindow.jsx'
import { mergeOverlaySnapshot } from '../../src/overlay_snapshot.js'
import MainAnswerDisplay from '../../src/components/MainAnswerDisplay.jsx'
import { createGrpcAutoSession } from '../../src/grpc_auto_session.js'

window.phase3OverlayVersion = 0
const stages = []
const started = performance.now()
const mark = stage => { if (stages.length < 128) stages.push({ stage, localMs: performance.now() - started }) }
window.phase1Stages = stages
let listener
window.phase1Snapshot = snapshot => { mark('renderer_consumption'); listener?.(snapshot) }
export default function Harness() {
  const [entry, setEntry] = useState({ answer: '', status: 'generating' })
  const [overlay, setOverlay] = useState({ answer: '', answerDisplayMode: 'answer', visible: true })
  window.phase3OverlaySnapshot = next => setOverlay(current => mergeOverlaySnapshot(current, next))
  window.phase1Start = async source => {
    window.phase1Session = await createGrpcAutoSession({ source,
      stream: { getTracks: () => [], getAudioTracks: () => [] },
      api: { connectGrpcAutoPipeline: () => window.phase1Connect(source),
        onGrpcAutoEvent: fn => { listener = fn; return () => { listener = null } },
        getGrpcRealtimeStatus: () => window.phase1Status(), closeGrpcRealtime: () => window.phase1Close() },
      createMic: () => ({ start: async () => {}, close() {} }),
      onAnswer: next => { mark('react_state_requested'); setEntry(next); window.phase3OverlaySnapshot({ answer: next.answer, transcript: next.question, answerDisplayMode: 'answer', answerRevealActive: next.status === 'generating', answerFullAvailable: Boolean(next.answer), grpcAnswerIdentity: next.streamIdentity, overlayPublicationVersion: ++window.phase3OverlayVersion }) },
    })
  }
  return <><section id="main-answer"><MainAnswerDisplay answer={entry.answer} /></section><section id="overlay-answer"><OverlayWindow overlayState={overlay} /></section></>
}
new MutationObserver(() => { if (document.querySelector('#root')?.textContent) mark('dom_mutation') })
  .observe(document.getElementById('root'), { subtree: true, childList: true, characterData: true })
createRoot(document.getElementById('root')).render(<Harness />)
