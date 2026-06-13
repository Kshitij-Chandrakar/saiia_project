import React, { useEffect, useRef, useState } from 'react'
import { Route, Routes } from 'react-router-dom'

const BACKEND_URL = 'http://localhost:8000'
const OVERLAY_PRIVACY_MESSAGE =
  'Visibility during screen sharing depends on OS, meeting app, and whether the user shares full screen, window, or tab.'

function getPreferredRecorderMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function getAudioFilename(blob) {
  const type = blob.type.split(';')[0]
  const extensionByType = {
    'audio/webm': 'webm',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/mpeg': 'mp3',
    'audio/mp4': 'mp4',
    'audio/x-m4a': 'm4a',
    'audio/ogg': 'ogg',
  }

  const extension = extensionByType[type] || 'webm'
  return `clip.${extension}`
}

async function parseJsonResponse(response, fallbackMessage) {
  let payload = null

  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const message = payload?.detail || payload?.error || fallbackMessage
    throw new Error(message)
  }

  return payload
}

function normalizePipelineError(error, fallbackMessage) {
  const message = error?.message || fallbackMessage

  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return 'SAIIA could not reach the backend. Please make sure the backend is running and try again.'
  }

  return message || fallbackMessage
}

function validateProfile(profile) {
  const requiredFields = ['resume', 'role', 'company', 'skills', 'experience']
  return requiredFields.every((field) => String(profile?.[field] || '').trim().length > 0)
}

function useElectronOverlaySync(state) {
  useEffect(() => {
    if (!window.electronAPI?.updateOverlayState) {
      return
    }

    window.electronAPI.updateOverlayState({
      ...state,
      privacyMessage: OVERLAY_PRIVACY_MESSAGE,
    })
  }, [state])
}

function OverlayWindow() {
  const [overlayState, setOverlayState] = useState({
    answer: '',
    error: '',
    status: 'Waiting for a question...',
    transcript: '',
    fontSize: 14,
    provider: '',
    category: '',
    generationMs: null,
    totalPipelineMs: null,
    visible: true,
    privacyMessage: OVERLAY_PRIVACY_MESSAGE,
  })

  useEffect(() => {
    let unsubscribe = null

    async function loadInitialState() {
      if (!window.electronAPI?.getOverlayState) {
        return
      }

      const initialState = await window.electronAPI.getOverlayState()
      setOverlayState((current) => ({ ...current, ...initialState }))

      if (window.electronAPI?.onOverlayState) {
        unsubscribe = window.electronAPI.onOverlayState((nextState) => {
          setOverlayState((current) => ({ ...current, ...nextState }))
        })
      }
    }

    loadInitialState()

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        padding: 18,
        background: 'transparent',
        color: 'white',
      }}
    >
      <div
        style={{
          WebkitAppRegion: 'drag',
          height: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'rgba(255,255,255,0.7)',
          cursor: 'move',
          userSelect: 'none',
        }}
      >
        ...
      </div>

      <div
        style={{
          WebkitAppRegion: 'no-drag',
          background: 'rgba(0,0,0,0.68)',
          borderRadius: 10,
          padding: 16,
          minHeight: 220,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>SAIIA Overlay</h3>
          <p style={{ margin: '6px 0 0', fontSize: 12, color: 'rgba(255,255,255,0.72)' }}>
            {overlayState.privacyMessage}
          </p>
        </div>

        {overlayState.status && (
          <div
            style={{
              background: 'rgba(255,255,255,0.08)',
              borderRadius: 6,
              padding: '8px 10px',
              fontSize: 13,
            }}
          >
            {overlayState.status}
          </div>
        )}

        {overlayState.error ? (
          <div
            style={{
              background: 'rgba(255, 99, 71, 0.22)',
              borderRadius: 6,
              padding: 12,
              fontSize: 14,
            }}
          >
            {overlayState.error}
          </div>
        ) : (
          <div
            style={{
              background: 'rgba(255,255,255,0.1)',
              borderRadius: 8,
              padding: 14,
              minHeight: 120,
              fontSize: `${overlayState.fontSize}px`,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
            }}
          >
            {overlayState.answer || 'Your latest interview answer will appear here.'}
          </div>
        )}

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            fontSize: 12,
            color: 'rgba(255,255,255,0.72)',
          }}
        >
          <span>Category: {overlayState.category || 'Waiting'}</span>
          <span>Provider: {overlayState.provider || 'Waiting'}</span>
          <span>Font: {overlayState.fontSize}px</span>
        </div>
      </div>
    </div>
  )
}

function MainWindow() {
  const [recording, setRecording] = useState(false)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [fontSize, setFontSize] = useState(14)
  const [provider, setProvider] = useState('')
  const [category, setCategory] = useState('')
  const [transcript, setTranscript] = useState('')
  const [generationMs, setGenerationMs] = useState(null)
  const [totalPipelineMs, setTotalPipelineMs] = useState(null)
  const [overlayVisible, setOverlayVisible] = useState(true)

  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => {
    let unsubscribe = null

    async function loadOverlayState() {
      if (!window.electronAPI?.getOverlayState) {
        return
      }

      const initialState = await window.electronAPI.getOverlayState()
      setOverlayVisible(Boolean(initialState.visible))

      if (window.electronAPI?.onOverlayState) {
        unsubscribe = window.electronAPI.onOverlayState((nextState) => {
          if (typeof nextState.visible === 'boolean') {
            setOverlayVisible(nextState.visible)
          }
        })
      }
    }

    loadOverlayState()

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [])

  useElectronOverlaySync({
    answer,
    error,
    status: status || (answer ? 'Latest answer ready.' : 'Waiting for a question...'),
    transcript,
    fontSize,
    provider,
    category,
    generationMs,
    totalPipelineMs,
  })

  const processAudioBlob = async (blob) => {
    if (!blob || blob.size === 0) {
      throw new Error('The recording is empty. Please record a short question and try again.')
    }

    const pipelineStarted = performance.now()
    setStatus('Transcribing...')
    setError('')

    const form = new FormData()
    form.append('file', blob, getAudioFilename(blob))

    const transcriptionStarted = performance.now()
    const transcribeResponse = await fetch(`${BACKEND_URL}/transcribe/`, {
      method: 'POST',
      body: form,
    })
    const { text } = await parseJsonResponse(
      transcribeResponse,
      'Could not transcribe the recording.'
    )
    if (!text || !text.trim()) {
      throw new Error('I could not clearly detect a question in that recording. Please try again.')
    }
    setTranscript(text)
    const transcriptionMs = Number((performance.now() - transcriptionStarted).toFixed(2))
    console.info('SAIIA transcript', { text, transcription_ms: transcriptionMs })

    setStatus('Classifying...')
    const classificationStarted = performance.now()
    const classifyResponse = await fetch(`${BACKEND_URL}/classify/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    const classifyPayload = await parseJsonResponse(
      classifyResponse,
      'Could not classify the question.'
    )
    const nextCategory =
      classifyPayload.category
    const classificationMs =
      classifyPayload.classification_ms ??
      Number((performance.now() - classificationStarted).toFixed(2))
    setCategory(nextCategory)
    console.info('SAIIA classification', {
      category: nextCategory,
      classification_ms: classificationMs,
    })

    setStatus('Loading answer...')
    const profileFetchStarted = performance.now()
    const profileResponse = await fetch(`${BACKEND_URL}/api/profile`)
    const profile = await parseJsonResponse(profileResponse, 'Could not load profile.')
    const profileFetchMs = Number((performance.now() - profileFetchStarted).toFixed(2))

    if (!validateProfile(profile)) {
      throw new Error('Please complete your profile before generating interview answers.')
    }

    const generateResponse = await fetch(`${BACKEND_URL}/generate/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: text,
        category: nextCategory,
        profile,
        transcription_ms: transcriptionMs,
        classification_ms: classificationMs,
        profile_fetch_ms: profileFetchMs,
      }),
    })
    const generatePayload = await parseJsonResponse(
      generateResponse,
      'Could not generate an answer right now.'
    )
    if (!generatePayload.answer || !generatePayload.answer.trim()) {
      throw new Error('Generation finished without a usable answer. Please try again.')
    }

    setAnswer(generatePayload.answer)
    setProvider(generatePayload.provider || '')
    setCategory(nextCategory)
    setGenerationMs(generatePayload.generation_ms ?? null)
    setTotalPipelineMs(
      generatePayload.total_pipeline_ms ??
        Number((performance.now() - pipelineStarted).toFixed(2))
    )
    setStatus('Latest answer ready.')

    console.info('SAIIA answer pipeline', {
      transcription_ms: transcriptionMs,
      classification_ms: classificationMs,
      profile_fetch_ms: profileFetchMs,
      generation_ms: generatePayload.generation_ms,
      total_pipeline_ms:
        generatePayload.total_pipeline_ms ??
        Number((performance.now() - pipelineStarted).toFixed(2)),
      provider: generatePayload.provider,
      model: generatePayload.model,
      fallback_used: generatePayload.fallback_used,
    })
  }

  const handleOverlayToggle = async () => {
    if (!window.electronAPI?.toggleOverlayVisibility) {
      return
    }

    const nextState = await window.electronAPI.toggleOverlayVisibility()
    if (typeof nextState?.visible === 'boolean') {
      setOverlayVisible(nextState.visible)
    }
  }

  const handleRecordToggle = async () => {
    if (!recording) {
      setError('')
      setStatus('Preparing microphone...')
      setAnswer('')
      setProvider('')
      setCategory('')
      setTranscript('')
      setGenerationMs(null)
      setTotalPipelineMs(null)

      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const mimeType = getPreferredRecorderMimeType()
        const recorder = mimeType
          ? new MediaRecorder(stream, { mimeType })
          : new MediaRecorder(stream)

        streamRef.current = stream
        mediaRecorderRef.current = recorder
        chunksRef.current = []

        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            chunksRef.current.push(event.data)
          }
        }

        recorder.onstop = async () => {
          try {
            const type = recorder.mimeType || chunksRef.current[0]?.type || 'audio/webm'
            const blob = new Blob(chunksRef.current, { type })
            await processAudioBlob(blob)
          } catch (err) {
            console.error('AI pipeline error', err)
            setAnswer('')
            setProvider('')
            setGenerationMs(null)
            setTotalPipelineMs(null)
            setError(normalizePipelineError(err, 'Could not process the recording.'))
            setStatus('Request failed.')
          } finally {
            streamRef.current?.getTracks().forEach((track) => track.stop())
            streamRef.current = null
            mediaRecorderRef.current = null
            chunksRef.current = []
            setRecording(false)
          }
        }

        recorder.start()
        setRecording(true)
        setStatus('Recording...')
      } catch (err) {
        console.error('Microphone error', err)
        setError('Could not access the microphone. Please check microphone permissions and try again.')
        setStatus('Microphone unavailable.')
      }
      return
    }

    setStatus('Stopping...')
    mediaRecorderRef.current?.stop()
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 20,
        left: 20,
        zIndex: 9999,
      }}
    >
      <div
        style={{
          WebkitAppRegion: 'drag',
          height: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'rgba(255,255,255,0.7)',
          cursor: 'move',
          userSelect: 'none',
        }}
      >
        ...
      </div>

      <div
        style={{
          WebkitAppRegion: 'no-drag',
          background: 'rgba(0,0,0,0.6)',
          padding: 12,
          borderRadius: 8,
        }}
      >
        <button
          onClick={() =>
            window.open(`${BACKEND_URL}/profile-setup`, '_blank', 'width=500,height=600')
          }
        >
          Setup Profile
        </button>

        <label style={{ color: 'white', display: 'block', marginTop: 12 }}>
          Font size:&nbsp;
          <input
            type="range"
            min="10"
            max="30"
            value={fontSize}
            onChange={(event) => setFontSize(Number(event.target.value))}
          />
          &nbsp;<strong>{fontSize}px</strong>
        </label>

        <button
          onClick={handleOverlayToggle}
          style={{ marginTop: 12, padding: '6px 12px', marginRight: 8 }}
        >
          {overlayVisible ? 'Hide Overlay' : 'Show Overlay'}
        </button>
        <span
          style={{
            color: 'rgba(255,255,255,0.72)',
            fontSize: 12,
            marginLeft: 8,
          }}
        >
          Ctrl+H also toggles overlay visibility.
        </span>

        <button
          onClick={handleRecordToggle}
          style={{ margin: '12px 0', padding: '6px 12px' }}
        >
          {recording ? 'Stop & Process' : 'Start Recording'}
        </button>

        {status && <p style={{ color: 'white', marginTop: 0 }}>{status}</p>}

        {error && (
          <div
            style={{
              marginBottom: 12,
              padding: 10,
              borderRadius: 6,
              background: 'rgba(255, 99, 71, 0.2)',
              color: 'white',
              maxWidth: 360,
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            padding: 12,
            background: 'rgba(255,255,255,0.1)',
            borderRadius: 6,
            color: 'white',
            maxWidth: 420,
          }}
        >
          <h3 style={{ marginTop: 0, marginBottom: 10 }}>Control Panel</h3>
          <p style={{ margin: '0 0 8px', fontSize: 13, color: 'rgba(255,255,255,0.78)' }}>
            Latest answer sent to overlay
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong>Status:</strong> {status || 'Waiting for a question...'}
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong>Transcript:</strong> {transcript || 'No transcript yet'}
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong>Category:</strong> {category || 'Waiting'}
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong>Provider:</strong> {provider || 'Waiting'}
          </p>
          <p style={{ margin: '0 0 6px' }}>
            <strong>Generation:</strong> {generationMs != null ? `${generationMs} ms` : 'Waiting'}
          </p>
          <p style={{ margin: 0 }}>
            <strong>Total pipeline:</strong> {totalPipelineMs != null ? `${totalPipelineMs} ms` : 'Waiting'}
          </p>
        </div>

        {answer && (
          <div
            style={{
              marginTop: 10,
              color: 'rgba(255,255,255,0.7)',
              fontSize: 12,
              maxWidth: 420,
            }}
          >
            Overlay is the primary answer display. Use Ctrl+H to hide or show it quickly.
          </div>
        )}
      </div>
    </div>
  )
}

function ProfileSetupForm() {
  const [resume, setResume] = useState('')
  const [role, setRole] = useState('')
  const [company, setCompany] = useState('')
  const [skills, setSkills] = useState('')
  const [experience, setExperience] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    const profile = { resume, role, company, skills, experience }
    localStorage.setItem('candidateProfile', JSON.stringify(profile))
    window.history.back()
  }

  return (
    <div
      style={{
        position: 'fixed',
        top: 20,
        left: 20,
        zIndex: 9999,
      }}
    >
      <div
        style={{
          WebkitAppRegion: 'drag',
          height: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'rgba(255,255,255,0.7)',
          cursor: 'move',
          userSelect: 'none',
        }}
      >
        ...
      </div>

      <div
        style={{
          WebkitAppRegion: 'no-drag',
          background: 'rgba(0,0,0,0.6)',
          color: 'white',
          padding: 20,
          borderRadius: 8,
          width: 300,
        }}
      >
        <h2>Profile Setup</h2>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Resume Text:</label>
            <textarea
              required
              value={resume}
              onChange={(event) => setResume(event.target.value)}
              style={{ width: '100%', height: 100 }}
              placeholder="Paste your resume here"
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Target Role:</label>
            <input
              required
              type="text"
              value={role}
              onChange={(event) => setRole(event.target.value)}
              style={{ width: '100%' }}
              placeholder="e.g. Site Reliability Engineer"
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Company Name:</label>
            <input
              required
              type="text"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              style={{ width: '100%' }}
              placeholder="e.g. Cogent Labs"
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Skills:</label>
            <textarea
              required
              value={skills}
              onChange={(event) => setSkills(event.target.value)}
              style={{ width: '100%', height: 80 }}
              placeholder="e.g. Python, FastAPI, React, MongoDB"
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4 }}>Experience / Projects:</label>
            <textarea
              required
              value={experience}
              onChange={(event) => setExperience(event.target.value)}
              style={{ width: '100%', height: 100 }}
              placeholder="Summarize your experience and key projects"
            />
          </div>
          <button type="submit" style={{ marginRight: 8, padding: '6px 12px' }}>
            Save & Return
          </button>
          <button
            type="button"
            onClick={() => window.history.back()}
            style={{ padding: '6px 12px' }}
          >
            Cancel
          </button>
        </form>
      </div>
    </div>
  )
}

export default function App() {
  const params = new URLSearchParams(window.location.search)
  const isOverlayView = params.get('view') === 'overlay'

  if (isOverlayView) {
    return <OverlayWindow />
  }

  return (
    <Routes>
      <Route path="/" element={<MainWindow />} />
      <Route path="/profile-setup" element={<ProfileSetupForm />} />
    </Routes>
  )
}
