# SAIIA Demo Script

## Goal

Show the working MVP flow clearly and honestly.

## Before the Demo

1. Start the backend on port `8000`.
2. Start Electron with `npm run electron:dev`.
3. Confirm the overlay window is visible.
4. Confirm the Groq API key is configured locally.

## Demo Walkthrough

1. Explain SAIIA in one sentence.

SAIIA is a Smart AI Interview Assistant that turns a live spoken question into a concise, profile-aware answer suggestion shown in a separate overlay window.

2. Explain what SAIIA is not.

It is not RAG, not an analytics dashboard, not an auth/payments product, and not a guaranteed invisible screen-sharing tool.

3. Open `Setup Profile`.

Mention that SAIIA uses only the saved profile and should not invent fake experience.

4. Record an HR question.

Use:
`Tell me about yourself.`

Show:
- transcript
- category
- provider
- overlay answer

5. Record a technical question.

Use:
`What is JavaScript?`

Show:
- fast classification
- Groq provider
- concise technical answer in the overlay

6. Record a behavioral question.

Use:
`Tell me about a time you solved a difficult bug.`

Show:
- behavioral classification
- compact STAR-style answer

7. Demonstrate overlay controls.

- Press `Ctrl+H` to hide the overlay
- Press `Ctrl+H` again to show it
- Drag the overlay
- Adjust font size from the main control panel

8. Explain privacy honestly.

SAIIA does not guarantee invisibility during screen sharing. Visibility depends on OS, meeting app, and whether the user shares full screen, window, or browser tab.

## If Something Fails

- Backend offline: restart FastAPI on port `8000`
- ffmpeg missing: install `ffmpeg` or fix `FFMPEG_PATH`
- Groq key missing: add `GROQ_API_KEY` locally
- Ctrl+H conflict: use the `Show/Hide Overlay` button

