# G13: Audio clock and endpoint review (2026-10-20)

This review concerns PR #50, branch `feat/grpc-computer-combined-audio`, at `b8b6dc7`. The current working branch additionally contains local answer-streaming commit `cd5b899`; it is excluded from this audio patch. Historical verification below describes the pre-commit review. The timestamp fix was published in `5c5abd3`; the subsequent suspended-clock fix and documentation disposition are published separately on PR #50. No environment, protobuf, migration, runtime activation, physical capture/playback or live provider operation is part of this work. The recovery migration remains paused.

## Windows endpoint finding: confirmed, native follow-up explicitly deferred

`SystemAudioCaptureService.get_default_loopback_device()` creates a `PyAudio()` wrapper and asks `get_default_wasapi_loopback()` for the current default. Inspection of the installed PyAudioWPatch Python source shows this reads the PortAudio host API's cached `defaultOutputDevice`. PortAudio reference-counts initialization; another wrapper does not rebuild the device table while capture retains an initialized instance. The wrapper's loopback-analogue lookup uses a name-substring comparison. That is not a reliable endpoint mapping, especially with duplicate names or a stale device table.

The inspected PyAudioWPatch WASAPI source initializes its default render selection with `GetDefaultAudioEndpoint(eRender, eMultimedia)`. A replacement monitor must query that same role, not assume eConsole or communications. The exact installed native build must also be verified against its source/build provenance before claiming role parity. See [PyAudioWPatch WASAPI implementation](https://github.com/s0d3s/PyAudioWPatch/blob/master/portaudio_v19/src/hostapi/wasapi/pa_win_wasapi.c), [PortAudio initialization](https://github.com/PortAudio/portaudio/blob/master/src/common/pa_front.c), and [Microsoft endpoint API](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-immdeviceenumerator-getdefaultaudioendpoint).

The installed PyAudioWPatch **0.2.12.8** reports PortAudio **V19.7.0-devel, revision unknown**. Its `_portaudiowpatch.cp310-win_amd64.pyd` exposes neither endpoint-ID Python methods nor an exported `PaWasapi_GetIMMDevice` function. This was checked by inspecting the installed shim/API and resolving native exports, without initializing PortAudio or opening devices. Existing declared dependencies provide no native capture-index-to-IMMDevice mapping. A separate Core Audio query can obtain a live default endpoint ID, but cannot prove which endpoint this already-selected cached loopback index captures. Names, indices and sample formats cannot close that gap.

The user explicitly selected **separate native follow-up; finish timestamp fix**. No speculative COM wrapper, name-based endpoint mapping, replacement capture library or process-global PortAudio reset was added. Native/non-Windows and explicit-device behavior are unchanged. The legacy monitor remains a cached comparison; it must **not** be described as reliable live Windows default-endpoint detection. This corrects the stronger monitoring claim in earlier G10/G12 records without rewriting their historical evidence.

Required native follow-up:

- Expose stable `IMMDevice::GetId` identity for the actual selected loopback capture through a supported binding/native build, including before/after-open default-role race handling. Do not map by friendly name.
- Query current eRender/eMultimedia independently of PortAudio on a dedicated control worker. Bound query work and failure reporting away from native reads and realtime mixing. A confirmed ID change stops the run and requires explicit restart; query failure is a separate error with a defined retry/fail-stop budget, not evidence that an endpoint changed.
- Initialize COM on its owning worker, handle apartment initialization results correctly, release interfaces/allocated ID memory on that worker and balance successful initialization with uninitialization. Do not share raw apartment-bound interfaces across capture/threadpool workers.
- Test the independent Windows query boundary, stable IDs despite identical names/formats, role differences, startup races, bounded query errors/stalls, COM cleanup and worker shutdown. Existing mocked `get_default_loopback_device` tests do **not** verify this.

No independent Core Audio monitor is implemented/tested by this timestamp patch. Reliable endpoint detection remains unimplemented and is tracked in [native follow-up #51](https://github.com/Kshitij-Chandrakar/saiia_project/issues/51). The PR thread is addressed through its offered documented-limitation alternative, not by claiming a runtime fix.

## Microphone timestamps: confirmed and fixed

Previously, `createGrpcMicTest.enqueue()` called `Date.now()` for each newly split frame. Multiple frames from one callback received enqueue timestamps rather than their audio-start times; retained tail bytes lost their original start. Queue age also used wall time. Electron compared the supplied epoch value with current wall time and could replace valid timestamps after a system-clock adjustment.

The current source has one `sendGrpcRealtimeAudioChunk` call in the queued send path. The apparent duplicate lines in the review excerpt were not present. Tests assert one transmission per emitted frame.

The fix carries a nominal Web Audio sample timeline:

1. Combined capture supplies output sample rate, first output-sample time on the renderer's monotonic clock and a discontinuity marker. The first nominal block interval uses Web Audio playback/context timing and input sample duration, not the assumption that callback arrival is exactly the end of captured audio. `playbackTime` describes output scheduling: the input/driver offset remains unknown. This is a software timeline estimate, **not a hardware ADC timestamp**.
2. Stateful resampling output counts advance that timeline at the actual output rate (16 kHz under the gRPC contract), including irregular input-rate/callback boundaries. Each 1,600-sample frame starts 100 ms after the previous one. Retained tail bytes retain their start time. Skipped capture blocks reset conversion/tail timing instead of stitching pre-gap audio into a later interval.
3. Once per run, renderer wall time and renderer monotonic time establish a fixed epoch offset. `timestamp_ms` is the rounded nominal **frame audio-start time**, expressed on that fixed per-run epoch. Later wall-clock changes cannot rewrite its elapsed durations. No renderer monotonic value crosses IPC or is compared with an unrelated main/backend monotonic value.
4. Local age checks use only renderer monotonic time. The existing 300 ms queue-wait limit is retained. An additional 500 ms audio-start-age limit accounts for the 256 ms ScriptProcessor callback block and retained sub-100 ms tail while bounding already-old source audio. Stale frames are discarded before the IPC send. The eight-frame capture gate, acknowledged main-process backpressure, pacing cancellation and sequence handling remain intact.
5. Electron validates a finite positive safe wire timestamp and relays it without replacing it based on current wall time. Missing/invalid legacy timing retains the old send-time fallback. The backend continues anchoring the first sender timestamp to local arrival and comparing elapsed durations; its 300 ms relative lateness budget and legacy zero-metadata behavior are unchanged. First-frame transit/input latency cannot be reconstructed from this protocol.

Microphone-only clients without timing metadata preserve their existing capture/framing/pacing behavior. No answer, token, selected-model, persistence or streaming state-machine behavior is changed.

## Scope and verification

Implementation: `frontend/src/live_mic_transport.js`, `frontend/src/grpc_mic_test.js`, timestamp validation only in `frontend/electron/grpc_realtime_client.cjs`, and the timing-contract comment in `backend/app/pcm_mixer.py`.

Regressions: new `frontend/src/grpc_mic_timing.test.js`; timing additions in `frontend/src/grpc_realtime_client.test.js`, a monotonic-clock injection in `frontend/src/grpc_combined.test.js`, and bounded-jitter/legacy acceptance in `backend/tests/test_grpc_combined.py`. This record is the only new documentation file.

Verification results:

- Current working tree: `node --test frontend/src/grpc_mic_timing.test.js frontend/src/grpc_mic_test.test.js frontend/src/grpc_combined.test.js frontend/src/grpc_realtime_client.test.js frontend/src/realtime_lifecycle.test.js` ? **91 passed**.
- Current working tree: `python -m pytest backend/tests/test_grpc_combined.py backend/tests/test_grpc_computer_devices.py backend/tests/test_grpc_computer_lifecycle.py backend/tests/test_grpc_system_audio.py -q -p no:cacheprovider` ? **34 passed**. The device tests are legacy cached-boundary tests, not verification of an independent Core Audio monitor.
- Isolated audio base `b8b6dc7`: `node --test --test-reporter=tap` over all `frontend/src/**/*.test.js` ? **571 passed**.
- Isolated audio base: `python -m pytest` over all `backend/tests/test_grpc*.py` plus `backend/tests/test_session_generation.py -q -p no:cacheprovider` ? **161 passed**.
- Isolated `frontend`: `npm ci --no-audit --no-fund`, then `npm run build` ? **passed** (existing large-bundle advisory).
- `node --check` for `frontend/electron/grpc_realtime_client.cjs`, `frontend/src/grpc_mic_test.js`, `frontend/src/live_mic_transport.js`, and `git diff --check` ? **passed**. Existing backend Swig deprecation warnings remain.
- Graphify code-only update/query performed before and after; output remains ignored local tooling.

No native endpoint mapping/COM boundary was added, so no mocked result is presented as proving that deferred fix. The exact unstaged diff is applied to a detached `b8b6dc7` checkout, without the real environment or `cd5b899`, to prove separation from answer streaming. Original index/head/environment/unrelated-source hashes are checked at handoff.

## Remaining physical Windows checks

- With headphones, exercise combined Auto at 44.1/48 kHz device input and a 16 kHz context where supported; inspect cadence and stale-drop behavior under short UI/IPC stalls, permission delay, Stop/restart and sleep/wake.
- Verify wall-clock adjustment does not change the sample timeline or revive old queued audio. Assess actual input latency/clock accuracy and long-duration drift separately; synthetic tests do not establish these physical properties.
- Real output-endpoint switching, duplicate endpoint names, role-specific defaults and COM ownership acceptance belong to the deferred native follow-up. Earlier user-reported device-loss success does not prove the cache issue is resolved.

These audio hunks should be reviewed on PR #50's audio branch. Do not push the local answer-streaming commit as a dependency, and do not claim reliable native endpoint detection is implemented.


### Suspended AudioContext follow-up

Continuous capture compares monotonic elapsed time against AudioContext elapsed
time from the current clock anchor. Divergence greater than 300 ms matches the
backend mixer's late-frame tolerance. Scheduling delay advancing both clocks
alone does not reset continuity. On divergence or an inactive capture callback,
the next active block re-anchors the nominal Web Audio timeline and resets the
continuous resampler/sample count. These remain nominal Web Audio timestamps,
not hardware ADC timestamps.

The discontinuity discards retained tail bytes and invalidates unsent pre-gap
frames. An already submitted IPC call cannot be recalled; its backend failure
still closes capture. No session is reopened automatically. Backend source-loss
termination requires explicit restart. Non-continuous capture is unchanged.

Synthetic fake-clock regressions cover repeated freezes/resumes, jitter,
fractional resampler reset, tail/queue invalidation and termination fencing.
Windows acceptance still requires user-controlled suspension/resume and verifying
that an already terminated Auto run stays stopped; mocks establish neither real
hardware timing accuracy nor physical device behavior.


## Accepted Windows default-output limitation

Default-output changes are **not reliably detected during active capture**.
Capture may remain attached to the original output device while it remains
connected, even if that stream becomes silent. Users must **Stop Auto Mode and
restart after changing Windows output devices**. Reliable endpoint mapping and
detection are deferred to [issue #51](https://github.com/Kshitij-Chandrakar/saiia_project/issues/51).
No native binding, capture library or runtime behavior changes implement that
follow-up here; independent Core Audio queries alone cannot establish the actual
captured endpoint's identity.

The existing `test_output_change_requires_restart_before_another_native_read`
replaces `get_default_loopback_device` with changed metadata. It establishes that
such a supplied change raises before another native read; it does not test live
Windows defaults, PortAudio cache refresh, or stable endpoint mapping. The test
is retained. G10/G11/G12 historical records now carry superseding limitations.
