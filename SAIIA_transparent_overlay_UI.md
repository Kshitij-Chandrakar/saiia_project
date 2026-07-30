# SAIIA Transparent Overlay UI — Final Implementation Report

## 1. Final Product Direction

SAIIA will become a desktop interview-assistant interface with two transparent Electron windows:

```text
1. Transparent Main Diagnostics Window
2. Transparent Floating Interview Overlay
```

The app should no longer feel like a normal React dashboard. It should feel like a lightweight desktop assistant that floats over the screen.

The goal is not to rebuild SAIIA from scratch. The backend flow should remain the same:

```text
Profile setup
→ audio/question capture
→ transcription
→ question classification
→ Groq answer generation
→ answer shown in overlay
```

This report only changes the UI/UX structure and the way controls are distributed between the main window and overlay window.

---

# 2. Final Window Architecture

## 2.1 Window 1 — Transparent Main Diagnostics Window

The main window should become a transparent glass-style diagnostics panel.

It should contain:

```text
Setup Profile
Transcript
Category
Provider
Generation time
Displayed answer
Control panel logs
Collapse/expand button
```

This window is mainly for:

```text
Profile setup
Developer/demo monitoring
Debugging pipeline status
Viewing detailed transcript/category/provider/timing/logs
```

It should not be the primary live interview controller.

### Main window should keep:

* Setup Profile button / profile form access
* Current transcript
* Current detected category
* Current provider
* Primary provider status
* Fallback/refinement status if used
* Generation time
* Total pipeline time
* Displayed answer
* Control logs
* Audio source state
* Last error
* Collapse button

### Main window should remove or move:

These should move to the floating overlay:

```text
Start Recording
Start Auto Mode
AI Help
Analyze Screen
Chat
Timer
Hide Overlay
Move overlay controls
Font-size controls for live answer
Audio source toggles
```

---

## 2.2 Window 2 — Transparent Floating Interview Overlay

This is the main live-use window.

It should look like a compact transparent floating toolbar, inspired by the reference layout.

Target structure:

```text
[SAIIA] [Soundwave] [Computer Audio] [Mic] [AI Help] [Analyze Screen] [Chat] [Timer] [Menu] [Move] [Collapse]
```

This window should be:

```text
Transparent
Always on top
Compact
Draggable
Resizable where needed
Readable
Minimal
Fast to hide/show
```

It should be used during the interview/demo.

---

# 3. Visual Design Specification

## 3.1 Overall Style

Use a dark transparent glass UI.

Recommended style:

```css
background: rgba(10, 12, 15, 0.58);
backdrop-filter: blur(18px);
border: 1px solid rgba(255, 255, 255, 0.12);
box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
border-radius: 18px;
color: #ffffff;
```

The UI should look:

```text
Professional
Minimal
Floating
Semi-transparent
Not childish
Not like a normal dashboard
Not too colorful
```

---

## 3.2 Main Window Visual Layout

Expanded state:

```text
┌────────────────────────────────────┐
│  SAIIA Control Panel          [<]  │
├────────────────────────────────────┤
│  [Setup Profile]                   │
│                                    │
│  Transcript: ...                   │
│  Category: Technical               │
│  Provider: Groq                    │
│  Generation: 1.8s                  │
│  Total pipeline: 4.2s              │
│                                    │
│  Displayed Answer:                 │
│  ...                               │
│                                    │
│  Logs:                             │
│  - Recording started               │
│  - Transcript received             │
│  - Category detected               │
└────────────────────────────────────┘
```

Collapsed state:

```text
[ > ]
```

The collapsed button should be a small transparent circular or pill-shaped handle.

It should behave like a side drawer:

```text
Expanded panel → click collapse → shrinks to tiny arrow button
Collapsed arrow → click → expands panel again
```

---

## 3.3 Floating Overlay Visual Layout

Default toolbar:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ SAIIA  〰  🖥🔴  🎙  [AI Help ✨] [Analyze Screen] [Chat] [00:12] ⋮ ⛶ ^ │
└──────────────────────────────────────────────────────────────────────┘
```

Expanded with transcript:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ SAIIA  〰  🖥🔴  🎙  [AI Help ✨] [Analyze Screen] [Chat] [00:12] ⋮ ⛶ ^ │
├──────────────────────────────────────────────────────────────────────┤
│ Transcript: Why do you want to work at Microsoft?             🗑 ˅ x │
└──────────────────────────────────────────────────────────────────────┘
```

Answer panel:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ ‹  ›                                           🗑  x                 │
│ Question: Why do you want to work at Microsoft?                      │
│                                                                      │
│ Answer:                                                              │
│ • I want to work at Microsoft because it is known for building...     │
│ • My experience with Java/Python/FastAPI aligns with...               │
│ • I am excited about contributing to scalable products...             │
│                                                                      │
│                                                       resize handle ↘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

# 4. Audio Source Toggle Feature

## 4.1 Required Buttons

The overlay must include two independent audio buttons:

```text
Computer icon = system/interviewer audio
Mic icon = user microphone audio
```

Each button has a red dot indicator.

## 4.2 Red Dot Meaning

```text
Red dot = ON / actively listening
No red dot = OFF / not listening
```

## 4.3 Audio Source States

| Computer Audio | Microphone | Meaning                                                            |
| -------------- | ---------- | ------------------------------------------------------------------ |
| ON             | OFF        | SAIIA listens only to interviewer/system audio                     |
| OFF            | ON         | SAIIA listens only to user microphone                              |
| ON             | ON         | SAIIA listens to both interviewer/system audio and user microphone |
| OFF            | OFF        | SAIIA is not listening                                             |

## 4.4 Default State

Recommended default:

```text
Computer audio: ON if available
Microphone: OFF
```

Reason:

During an interview, the most important source is the interviewer’s question.

## 4.5 Technical Reality

Microphone capture is already easier because browser/Electron can request mic permission.

System audio capture is more difficult and OS-dependent.

Implementation should be staged:

### Stage A — UI and state support

Add the system audio button and mic button.

Even if system audio is not fully implemented yet, the UI state should exist.

### Stage B — Mic capture stable

Keep existing MediaRecorder mic flow working.

### Stage C — System audio implementation

Try Electron desktop audio capture where supported.

Potential paths:

```text
Electron desktopCapturer
getDisplayMedia with audio
Windows loopback capture
Virtual audio cable fallback
```

System audio should be treated as a feature that must be tested on the target OS.

---

# 5. Source-Aware Listening Logic

When both system audio and mic are ON, SAIIA should not blindly treat everything as an interviewer question.

Recommended source logic:

```text
System audio transcript = primary question source
Mic transcript = user response/context source
```

This means:

* System audio should trigger question detection.
* Mic audio should be used as optional context.
* Mic audio should not automatically trigger answer generation unless user manually requests it.
* Auto Mode should prioritize system/interviewer transcript.

This prevents SAIIA from generating answers based on the user’s own spoken response.

---

# 6. Transcript Strip Feature

## 6.1 Purpose

The transcript strip shows what SAIIA is currently hearing.

Example:

```text
Transcript: Why do you want to work at Microsoft?
```

## 6.2 Controls

The transcript strip should include:

```text
Soundwave icon = show/hide transcript
Trash icon = clear transcript
Arrow icon = expand/collapse transcript
X icon = hide transcript strip
Autoscroll toggle = keep latest transcript visible
```

## 6.3 Transcript Modes

### Collapsed transcript

Shows one latest line:

```text
Why do you want to work at Microsoft?
```

### Expanded transcript

Shows more text:

```text
Interviewer: Tell me about yourself.
Interviewer: Why do you want to work at Microsoft?
Candidate: Sure, I can answer that...
```

## 6.4 Transcript Storage

For MVP:

```text
Keep transcript in memory during session.
Do not save transcript permanently by default.
```

Optional future setting:

```text
Save transcript: ON/OFF
```

---

# 7. AI Help Feature

## 7.1 Purpose

AI Help is manual answer generation.

The user clicks AI Help when the full question is visible in the transcript.

Flow:

```text
Click AI Help
→ take latest complete question
→ classify question
→ generate answer using Groq
→ show answer panel
```

## 7.2 Question Selection Logic

When AI Help is clicked:

1. Check latest transcript.
2. Extract the most recent question.
3. Prefer system audio transcript.
4. If no question is detected, use the latest meaningful transcript chunk.
5. If still unclear, show error:

```text
No clear question detected yet. Please wait for the full question or type it in Chat.
```

## 7.3 Recommended Delay

When the user clicks AI Help, wait around 500–1000 ms if audio is still active.

This helps capture the final words of the question.

---

# 8. Auto Mode Feature

## 8.1 Purpose

Auto Mode automatically generates answers when SAIIA detects an interview question.

## 8.2 Flow

```text
Audio segment captured
→ transcription
→ clean transcript
→ question detector
→ duplicate filter
→ cooldown check
→ classify
→ generate answer
→ display answer panel
```

## 8.3 Question Detection Rules

Auto Mode should only trigger when:

```text
Transcript is not empty
Transcript is long enough
Transcript looks like a question
Transcript is not a filler sentence
Transcript is not a duplicate of recent transcript
Cooldown has passed
```

## 8.4 Cooldown

Recommended:

```text
10 seconds cooldown after generating an answer
```

This avoids repeated answers for the same question.

## 8.5 Duplicate Filter

Store the last few generated questions.

If the new question is very similar to a recent one, do not generate again.

## 8.6 Auto Mode Button State

In toolbar menu or button:

```text
Auto Mode: ON
Auto Mode: OFF
```

When ON, show a small active indicator.

---

# 9. Analyze Screen Feature

## 9.1 Purpose

Analyze Screen handles cases where the interviewer shows a question/problem on screen instead of speaking it.

Example:

```text
Interviewer: "Solve the question shown on the screen."
```

Flow:

```text
Click Analyze Screen
→ capture user-approved screen
→ OCR/extract visible text
→ detect question/problem
→ allow user to edit extracted text
→ classify
→ generate answer
→ show answer panel
```

## 9.2 Important UX Rule

Do not silently capture repeatedly.

The user should initiate screen analysis by clicking the button or shortcut.

## 9.3 Privacy Rule

Screenshot should be temporary.

Recommended:

```text
Do not store screenshot permanently.
Do not commit screenshot files.
Delete temporary screenshots after OCR.
```

## 9.4 Extracted Question Review

After OCR, show a small editable preview:

```text
Detected question:
[ text area with extracted question ]

[Generate Answer] [Cancel]
```

This improves reliability because OCR can be wrong.

---

# 10. Chat Feature

## 10.1 Purpose

Chat is manual typed fallback.

Use cases:

```text
Audio did not detect question
Screen OCR failed
User wants to ask a custom interview question
Demo reliability
```

## 10.2 Flow

```text
Click Chat
→ small transparent chat input opens
→ user types question
→ send
→ classify
→ generate answer
→ show answer panel
```

## 10.3 Chat UI

```text
┌──────────────────────────────┐
│ Ask SAIIA manually            │
│ [Type question here...]       │
│ [Send] [Cancel]               │
└──────────────────────────────┘
```

---

# 11. Answer Panel Feature

## 11.1 Purpose

The answer panel displays the generated response.

It should be separate from the toolbar but visually connected to it.

## 11.2 Content

The answer panel should show:

```text
Question
Answer
Category
Provider
Generation time
```

Example:

```text
Question: Why do you want to work at Microsoft?

Answer:
• I want to work at Microsoft because it is known for building products that impact millions of users.
• My experience with Python, FastAPI, and React aligns with building scalable software.
• I am excited about working in a culture that values learning, collaboration, and technical growth.

Category: HR
Provider: Groq
Generated in: 1.6s
```

## 11.3 Controls

The answer panel should include:

```text
Previous answer
Next answer
Clear answers
Hide answer panel
Resize handle
Scroll area
```

## 11.4 Answer History

Maintain an array:

```js
answers = [
  {
    id,
    question,
    answer,
    category,
    provider,
    model,
    generationTimeMs,
    createdAt
  }
]
```

Allow:

```text
Ctrl + Left = previous answer
Ctrl + Right = next answer
Ctrl + Backspace = clear answers
```

---

# 12. Timer Feature

## 12.1 MVP Behavior

For SAIIA, the timer should be simple.

Recommended:

```text
Session duration timer
```

Example:

```text
00:12
05:42
27:25
```

It starts when:

```text
User starts listening/session
```

It stops when:

```text
User ends session
```

## 12.2 Avoid for MVP

Do not add:

```text
Credits
Payments
Auto-renew session billing
Subscription timers
```

---

# 13. Menu Feature

## 13.1 Three-Dot Menu

The overlay menu should include:

```text
Auto-generate: ON/OFF
Language
Answer style
Simple mode: ON/OFF
Font size
Overlay opacity
Clear transcript
Clear answers
Open main panel
End session
```

## 13.2 MVP Menu Items

For the first implementation, keep only:

```text
Auto-generate toggle
Font size
Overlay opacity
Clear transcript
Clear answers
Open main window
End session
```

Language and answer style can come after the core UI works.

---

# 14. Move and Collapse Behavior

## 14.1 Move Button

The move button should allow the overlay to be dragged.

Implementation:

```css
.drag-region {
  -webkit-app-region: drag;
}

button,
input,
textarea,
.no-drag {
  -webkit-app-region: no-drag;
}
```

## 14.2 Collapse Button

The collapse button should shrink the overlay to a small pill or icon.

Expanded:

```text
[SAIIA] [System] [Mic] [AI Help] [Analyze Screen] [Chat] [Timer] ...
```

Collapsed:

```text
[SAIIA >]
```

Clicking the collapsed pill expands it again.

## 14.3 Main Window Collapse

The main diagnostics window should also collapse.

Expanded:

```text
Full transparent diagnostics panel
```

Collapsed:

```text
Small arrow button on side of screen
```

---

# 15. Keyboard Shortcuts

## 15.1 Required Shortcuts

Use Windows-friendly shortcuts:

| Shortcut                  | Action                 |
| ------------------------- | ---------------------- |
| Ctrl + Enter              | Trigger AI Help        |
| Ctrl + Shift + Enter      | Trigger Analyze Screen |
| Ctrl + H                  | Hide/show overlay      |
| Ctrl + Shift + Arrow Keys | Move overlay           |
| Ctrl + Left               | Previous answer        |
| Ctrl + Right              | Next answer            |
| Ctrl + Backspace          | Clear answers          |
| Ctrl + Shift + Backspace  | Clear transcript       |

## 15.2 Shortcut Handling

Register shortcuts in Electron main process using `globalShortcut`.

Rules:

```text
Log shortcut registration success/failure.
Do not crash if a shortcut is unavailable.
Keep button actions and shortcut actions using the same handler.
Avoid state desync between UI and shortcut behavior.
```

---

# 16. Electron Implementation Plan

## 16.1 Windows

Create/maintain two BrowserWindow instances:

```text
mainWindow
overlayWindow
```

### mainWindow

Purpose:

```text
Profile + diagnostics
```

Suggested config:

```js
new BrowserWindow({
  width: 420,
  height: 720,
  transparent: true,
  frame: false,
  resizable: true,
  alwaysOnTop: false,
  backgroundColor: '#00000000',
  webPreferences: {
    preload: path.join(__dirname, 'preload.cjs'),
    contextIsolation: true,
    nodeIntegration: false
  }
})
```

### overlayWindow

Purpose:

```text
Live interview toolbar + transcript + answer panel
```

Suggested config:

```js
new BrowserWindow({
  width: 1200,
  height: 220,
  transparent: true,
  frame: false,
  resizable: true,
  alwaysOnTop: true,
  skipTaskbar: true,
  backgroundColor: '#00000000',
  webPreferences: {
    preload: path.join(__dirname, 'preload.cjs'),
    contextIsolation: true,
    nodeIntegration: false
  }
})
```

Important:

Because the overlay contains clickable buttons, do not make it fully click-through by default.

Only consider click-through mode later for read-only collapsed display.

---

## 16.2 Routes / Views

Use query params or hash routes:

```text
/?view=main
/?view=overlay
```

React decides which UI to render:

```js
const view = new URLSearchParams(window.location.search).get("view");

if (view === "overlay") {
  return <OverlayWindow />;
}

return <MainDiagnosticsWindow />;
```

---

## 16.3 IPC Events

Add clear IPC event names.

From overlay to main process:

```text
overlay:ai-help
overlay:analyze-screen
overlay:chat-submit
overlay:toggle-system-audio
overlay:toggle-mic
overlay:toggle-auto-mode
overlay:clear-transcript
overlay:clear-answers
overlay:collapse
overlay:expand
overlay:move
overlay:end-session
```

From main process to renderer:

```text
app:state-update
app:answer-update
app:transcript-update
app:error
app:shortcut-triggered
```

Between main window and overlay:

```text
profile:updated
diagnostics:update
answer:display
transcript:update
settings:update
```

---

# 17. Frontend State Model

Use a single shared app state.

Recommended structure:

```js
const appState = {
  session: {
    active: false,
    startedAt: null,
    elapsedSeconds: 0
  },

  audio: {
    systemEnabled: false,
    micEnabled: false,
    systemAvailable: false,
    micAvailable: false,
    listening: false,
    sourceMode: "none"
  },

  transcript: {
    text: "",
    expanded: false,
    visible: true,
    autoscroll: true,
    source: "system",
    updatedAt: null
  },

  question: {
    current: "",
    category: "Waiting",
    confidence: "low"
  },

  generation: {
    provider: "Waiting",
    model: "",
    generationTimeMs: null,
    totalPipelineTimeMs: null,
    fallbackUsed: false,
    status: "idle"
  },

  answers: {
    items: [],
    currentIndex: -1,
    visible: false
  },

  overlay: {
    visible: true,
    collapsed: false,
    opacity: 0.58,
    fontSize: 16,
    position: { x: 100, y: 50 },
    size: { width: 1200, height: 220 }
  },

  mainPanel: {
    collapsed: false,
    visible: true
  },

  logs: [],

  error: null
};
```

---

# 18. Backend API Mapping

Do not rewrite the backend unless necessary.

Keep existing routes:

```text
POST /api/profile
GET /api/profile
POST /transcribe/
POST /classify/
POST /generate/
```

## 18.1 Manual AI Help Flow

```text
Overlay AI Help click
→ frontend extracts latest question
→ POST /classify/
→ POST /generate/
→ update answer panel
→ update main diagnostics
```

If the transcript is only audio and not yet transcribed:

```text
record segment
→ POST /transcribe/
→ POST /classify/
→ POST /generate/
```

## 18.2 Auto Mode Flow

```text
short audio segment
→ POST /transcribe/
→ question-detect
→ POST /classify/
→ POST /generate/
```

## 18.3 Chat Flow

```text
typed question
→ POST /classify/
→ POST /generate/
```

## 18.4 Analyze Screen Flow

```text
screen capture
→ OCR/extract text
→ user edits extracted question
→ POST /classify/
→ POST /generate/
```

## 18.5 Future Unified Endpoint

Only after the split routes are stable, add:

```text
POST /api/interview/assist
```

Payload:

```json
{
  "question": "Why do you want to work at Microsoft?",
  "source": "manual | audio | screen | chat",
  "profile": {},
  "options": {
    "simpleMode": false,
    "language": "English"
  }
}
```

Response:

```json
{
  "transcript": "Why do you want to work at Microsoft?",
  "category": "HR",
  "answer": "...",
  "confidence": "medium",
  "provider": "groq",
  "model": "llama-3.1-8b-instant",
  "fallback_used": false,
  "generation_time_ms": 1600,
  "error": null
}
```

---

# 19. Answer Generation Rules

The output must remain:

```text
Short
Natural
Speakable
Personalized
Category-aware
Profile-grounded
```

Do not allow answers that:

```text
Invent fake experience
Overclaim skills
Sound like essays
Expose prompts
Use irrelevant jargon
Repeat the question unnecessarily
```

Recommended answer formats:

### HR

```text
3 short bullets or one spoken paragraph
```

### Technical

```text
direct explanation + example from profile
```

### Behavioral

```text
compact STAR format
```

### General

```text
short practical response
```

---

# 20. Error Handling

## 20.1 Required User-Facing Errors

Show these clearly in overlay and main diagnostics:

```text
Microphone permission denied.
System audio capture is not available on this device.
No audio source is enabled.
No clear question detected yet.
Transcript is empty.
Could not transcribe audio. Please check ffmpeg.
Backend is offline.
Profile is incomplete.
Groq API key is missing.
Groq request timed out.
Could not generate an answer.
Ollama fallback is unavailable.
Screen capture was cancelled.
Could not read question from screen.
```

## 20.2 Stale Answer Rule

If generation fails:

```text
Do not keep showing old answer as if it is new.
```

Instead:

```text
Keep previous answer in history
Show error in status area
Mark current generation as failed
```

---

# 21. File-Level Implementation Plan

## 21.1 Frontend Files

Recommended component split:

```text
frontend/src/App.jsx
frontend/src/components/MainDiagnosticsWindow.jsx
frontend/src/components/OverlayWindow.jsx
frontend/src/components/OverlayToolbar.jsx
frontend/src/components/AudioSourceToggle.jsx
frontend/src/components/TranscriptStrip.jsx
frontend/src/components/AnswerPanel.jsx
frontend/src/components/ChatPanel.jsx
frontend/src/components/MenuPanel.jsx
frontend/src/components/CollapseHandle.jsx
frontend/src/components/ProfileSetupPanel.jsx
frontend/src/styles/glass.css
```

If you want fewer files for now, at minimum create:

```text
OverlayWindow.jsx
MainDiagnosticsWindow.jsx
glass.css
```

## 21.2 Electron Files

Expected files to update:

```text
frontend/electron/main.cjs
frontend/electron/preload.cjs
```

Main process responsibilities:

```text
create main window
create overlay window
register global shortcuts
send shortcut events to renderer
move overlay window
hide/show overlay
collapse/expand overlay
handle screen capture permission if needed
```

Preload responsibilities:

```text
expose safe IPC methods
do not expose full Node.js APIs
```

## 21.3 Backend Files

Backend should only change if required for:

```text
Question detect
System-audio transcription support
Screen OCR support
Unified assist endpoint
Better error shape
```

Expected possible files:

```text
backend/app/api/transcribe.py
backend/app/api/classify.py
backend/app/api/generate.py
backend/app/api/question_detect.py
backend/app/nlp/classifier.py
backend/app/nlp/answer_generator.py
backend/app/main.py
```

---

# 22. Implementation Phases

## Phase UI-1 — Preserve Existing Working Flow

Before UI refactor:

```text
Confirm current manual recording flow works
Confirm answer reaches overlay
Confirm Ctrl+H still works
Confirm profile validation still works
```

Do not start UI restructuring before confirming baseline.

---

## Phase UI-2 — Create Transparent Main Diagnostics Window

Tasks:

```text
Make main window transparent
Apply glass UI
Keep Setup Profile
Keep transcript/category/provider/timing/logs
Add collapse arrow button
Remove live interview controls from main window
```

Acceptance:

```text
Main window looks transparent
Profile still works
Diagnostics still update
Collapse/expand works
```

---

## Phase UI-3 — Create Transparent Floating Toolbar

Tasks:

```text
Build compact overlay toolbar
Add SAIIA brand/logo area
Add soundwave icon
Add computer audio toggle
Add mic toggle
Add AI Help button
Add Analyze Screen button
Add Chat button
Add timer
Add menu button
Add move button
Add collapse button
```

Acceptance:

```text
Overlay toolbar appears always-on-top
Buttons are clickable
Drag works
Collapse works
UI matches target transparent style
```

---

## Phase UI-4 — Move Live Controls to Overlay

Tasks:

```text
Move Start Recording / AI Help behavior to overlay
Move Auto Mode control to overlay menu
Move Analyze Screen to overlay
Move Chat to overlay
Move font size control to overlay menu
```

Acceptance:

```text
User can run the full interview flow from overlay only
Main window is only profile + diagnostics
```

---

## Phase UI-5 — Add Audio Source Toggle Logic

Tasks:

```text
Add systemAudioEnabled state
Add micEnabled state
Add red dot indicators
Connect mic toggle to existing mic recording
Add system audio availability detection
Show useful error if system audio is unavailable
```

Acceptance:

```text
Mic red dot ON means mic capture active
Computer red dot ON means system audio intended/active
OFF means disabled
No audio source ON means no listening
```

---

## Phase UI-6 — Transcript Strip

Tasks:

```text
Add transcript strip below toolbar
Add show/hide via soundwave icon
Add clear transcript
Add expand/collapse
Add autoscroll
Send transcript updates to main diagnostics
```

Acceptance:

```text
Live transcript appears in overlay and main diagnostics
Transcript can be hidden, expanded, cleared, restored
```

---

## Phase UI-7 — Answer Panel

Tasks:

```text
Create transparent answer panel
Show question and answer
Show category/provider/timing
Add previous/next answer navigation
Add clear answer button
Add hide answer button
Add resize handle
Add scroll support
```

Acceptance:

```text
Generated answer appears in readable transparent panel
User can resize, scroll, hide, clear, and navigate answers
```

---

## Phase UI-8 — Chat and Analyze Screen

Tasks:

```text
Add chat modal
Send typed question to classify/generate
Connect Analyze Screen button
Capture screen only after user action
Run OCR or existing screen-read flow
Allow editing extracted question before generation
```

Acceptance:

```text
Chat can generate answer
Analyze Screen can extract or accept question and generate answer
```

---

## Phase UI-9 — Keyboard Shortcuts

Tasks:

```text
Ctrl+Enter → AI Help
Ctrl+Shift+Enter → Analyze Screen
Ctrl+H → hide/show overlay
Ctrl+Shift+Arrow → move overlay
Ctrl+Left/Right → previous/next answer
Ctrl+Backspace → clear answers
Ctrl+Shift+Backspace → clear transcript
```

Acceptance:

```text
Shortcuts trigger same handlers as buttons
No UI state desync
Failures are logged
```

---

## Phase UI-10 — Testing and Polish

Tasks:

```text
Test full manual flow 5 times
Test auto mode
Test transcript clear/hide/expand
Test answer history
Test collapse/expand
Test profile validation
Test error states
Test no backend
Test missing API key
Test empty audio
Test screen capture cancel
```

Acceptance:

```text
Full demo works repeatedly without code changes
```

---

# 23. Acceptance Criteria

## 23.1 Main Window

Must pass:

```text
Main window is transparent
Setup Profile works
Transcript updates
Category updates
Provider updates
Generation time updates
Displayed answer updates
Logs update
Collapse/expand works
No live interview controls remain in main window
```

## 23.2 Overlay Toolbar

Must pass:

```text
Toolbar is transparent and compact
Always-on-top works
Computer/mic buttons show red dot correctly
AI Help triggers answer generation
Analyze Screen opens screen-read flow
Chat opens manual input
Timer works
Menu opens
Move works
Collapse works
Ctrl+H hides/shows overlay
```

## 23.3 Transcript

Must pass:

```text
Transcript appears in overlay
Transcript appears in main diagnostics
Clear transcript works
Expand/collapse works
Hide/show works
Autoscroll works
```

## 23.4 Answer Panel

Must pass:

```text
Question shown
Answer shown
Category shown
Provider shown
Generation time shown
Scroll works
Resize works
Hide works
Clear works
Previous/next works
```

## 23.5 Backend Pipeline

Must pass:

```text
Profile is loaded
Question is classified
Groq generates answer
Ollama fallback does not break flow
Errors are user-friendly
No stale answer after failure
```

---

# 24. Important Technical Risks

## 24.1 System Audio Risk

System audio capture may not work consistently across all devices and operating systems.

Mitigation:

```text
Keep mic capture stable
Keep Chat fallback
Keep Analyze Screen fallback
Show clear system-audio unavailable message
Do not block MVP on perfect system audio
```

## 24.2 Overlay Visibility Risk

Do not claim guaranteed invisibility during screen sharing.

Mitigation:

```text
Use separate Electron overlay
Provide Ctrl+H emergency hide
Allow dragging/collapsing
Recommend sharing only browser tab/window during demo
```

## 24.3 UI Clickability Risk

If overlay is made click-through, buttons will stop working.

Mitigation:

```text
Keep overlay interactive by default
Only add click-through mode later for collapsed/read-only mode
```

## 24.4 Scope Creep Risk

Avoid adding:

```text
Payments
Credits
Admin dashboard
Complex RAG
Full auth system
Browser extension
Mobile app
Over-polished animations
```

---

# 25. Final Implementation Summary

SAIIA should now be implemented as:

```text
Transparent Main Diagnostics Window
+
Transparent Floating Interview Overlay
+
Audio source toggles
+
Transcript strip
+
AI Help manual generation
+
Auto Mode generation
+
Analyze Screen
+
Chat fallback
+
Answer panel with history
+
Timer
+
Menu
+
Keyboard shortcuts
```

The main window is for setup and debugging.

The floating overlay is for live interview/demo usage.

The backend flow remains:

```text
transcript/question
→ classify
→ Groq generate
→ answer response
→ overlay display
```

This is the final ready implementation plan for the new SAIIA transparent overlay experience.
