# BLAZE — changes made in this session

This documents exactly what changed relative to `Blaze.zip`, across two
parts of the same session: (1) the initial GUI build + wiring, and (2)
four batches porting every feature from `blaze/gui/app.py` (the original
tkinter GUI) into the new chatbot-mode window specifically — talk mode
stays untouched, per your instruction.

## Part 1 — new GUI + wiring (see git history / earlier delivery for full detail)
- `blaze/gui/orb_widget.py`, `chat_mode_window.py`, `talk_mode_window.py`,
  `app_shell.py`, `blaze/services/hw_stats.py` — the talk-mode orb,
  chat-mode window shell, and controller tying both to the real backend.
- `blaze/intelligence/nlp.py` — added `mode_switch_talk`/`mode_switch_chat`
  intents.
- Wired `nlp` intent routing, `ai/engine.py`'s `BlazeAI.chat()` (background
  thread), and `system_monitor.py`'s previously-uncalled `alert_check()`.

## Part 2 — Batch 1: core interaction loop
- **Thinking animation**: animated "●○○ processing..." indicator above the
  input row while a request is in flight.
- **Cancel button**: best-effort cancel via a `threading.Event` checked
  before/after the blocking `ai.chat()` call — same semantics as the
  original (can't abort mid-network-call, but a cancelled reply is
  dropped). Tested specifically: started a slow request, cancelled it,
  confirmed the late reply never got appended.
- **Command history**: up/down arrow recalls previous messages
  (`_HistoryLineEdit`). Down-arrow support is a small addition beyond the
  original, which only bound Up.
- **Mic push-to-talk**: wired to `voice_engine.trigger_manual_listen()`,
  same contract as `app.py`'s `_activate_voice`.
- **Feedback rating**: 👍/👎 buttons in the titlebar call
  `ai.save_feedback()`.

## Part 2 — Batch 2: content features
- **Full quick actions list**: all 16 items from the original (was 6),
  left panel wrapped in a scroll area so it doesn't blow up the window.
- **Live weather**: real fetch via `system_monitor.weather.get()` (no API
  key required — open-meteo/wttr.in), refreshed every 10 minutes.
- **Reminders display**: pulled from `db.get_all_reminders()`.
- **Startup boot sequence**: exact message list (platform, model, vault
  status, plugin count) with the same 0.25s-per-line timing, followed by
  a time-aware greeting and a real TTS-readiness wait (not a blind sleep).
- **Morning Brief bypass**: checked *before* `nlp.analyze()`, same as the
  original — uses real weather/news/system data directly instead of
  asking the LLM, avoiding hallucinated numbers. Tested that `ai.chat()`
  is never called for this path.

## Part 2 — Batch 3: background systems
- **`ReminderEngine`**: instantiated and wired into `ai._reminder_engine`
  — this was previously `None` in the new GUI, meaning "remind me to X"
  would be classified correctly by nlp but silently fail to actually
  store anything. Fixed.
- **`ProactiveMonitor`**: wired for alert/briefing/suggestion callbacks.
  Runs alongside (not instead of) the existing 5s alert poll — that one
  drives the orb's visual danger state fast; this one pushes a deduped,
  slower (60s, 5min cooldown) notification into chat. Orb "flashes" to
  its danger visual for a reminder/alert then auto-reverts after 4s,
  matching `app.py`'s exact behavior including its one inherited quirk:
  if a real danger state is already active when a reminder fires, the
  4s auto-revert will incorrectly clear it — same limitation as the
  original, not introduced here.

## Part 2 — Batch 4: standalone features
- **File attachment**: 📎 button, reads up to 2000 chars of a text/markdown
  file, drops it into the input box as a prompt — same as `_attach_file`.
- **Session lock (PIN)**: opt-in — only activates if a PIN is actually set
  via Settings. Checked every 60s against `SESSION_TIMEOUT`. Locked state
  blocks message processing and mic activation; wrong PIN keeps it
  locked; correct PIN unlocks. Tested all four of those paths directly,
  plus confirmed the lock never fires at all when no PIN is configured.
- **Settings dialog** (`blaze/gui/settings_dialog.py`): full port of all
  six sections from `dialogs.py` — Personal Info (name/city/API keys),
  Voice & TTS (tone/verbosity/speed), BLAZE Voice (Edge TTS neural voice
  list + Windows voice fallback + preview button), Security (PIN),
  Knowledge Base (view + add fact), Automation Rules (view + add rule).
  Save only reports fields that actually changed, only restarts the TTS
  thread if voice/speed changed — same logic as the original.

## What was tested vs. genuinely not testable here

**Tested in this sandbox (all passing):**
- Full syntax check (`py_compile`) across every `.py` file — clean.
- Every module imports cleanly (only failures: `tkinter` not installed in
  this Linux sandbox — irrelevant on your Windows machine where it ships
  with Python).
- All four batches: thinking/cancel/history/mic/feedback (5 tests),
  quick actions/weather/boot/briefing (5 tests), reminder engine
  wiring/proactive callbacks/orb flash (6 tests), settings dialog
  save/knowledge base/automation rules/session lock/unlock/file attach
  (10 tests) — 26 targeted tests total, `ai.chat()`/`ai.speak()`/
  `weather.get()`/engine constructors mocked out where they'd need real
  network or hardware this sandbox doesn't have.

**NOT tested here, needs verification on your machine:**
- Real Groq API calls, real microphone/hotword capture, real TTS audio
  playback — same gap as before, this sandbox has no network path to
  Groq and no audio hardware.
- The settings dialog's "Preview Voice" button, which shells out to
  PowerShell's `System.Windows.Media.MediaPlayer` — Windows-only code
  path, identical to the original, untestable here by definition.
- The frameless/translucent/always-on-top talk-mode window's actual
  appearance on a real Windows compositor.

## Part 3 — Quick Actions removed, replaced with embedded phone mirror
- **Removed** the 16-button Quick Actions list from the chat-mode left
  panel (`chat_window.py`) entirely, along with the now-unused
  `QUICK_ACTIONS` constant.
- **New `blaze/gui/phone_mirror.py`** — `PhoneMirrorPanel`, dropped into
  the exact spot Quick Actions used to occupy. It's a live(-ish) view of
  your phone's screen embedded directly in the BLAZE window, not a
  separate scrcpy window to alt-tab to:
  - A background `QThread` polls `adb` (~1-2 fps — each frame is a real
    screencap + PNG encode on the phone + transfer, not a video stream;
    see the docstring for why that's the honest ceiling here) and streams
    frames into a `QLabel`.
  - **Click-to-tap**: clicking anywhere on the mirrored image forwards a
    real tap to the phone at the equivalent scaled coordinate.
  - **Back / Home / Recents** buttons send the matching Android keyevents.
  - **Rename button (✎)**: renames the connected device with a friendly
    name of your choice, persisted by serial (not connection order) via
    a new `device_names_json` pref key — so "Kartik's Pixel" survives
    reconnects and future sessions, and stays correct if you ever pair a
    second phone (each serial gets its own name).
  - Fails gracefully at every stage — no adb installed, no phone paired,
    device disconnects mid-session — with a status dot + message instead
    of an exception.
- **`blaze/services/android_control.py`**: added `list_devices()` (all
  adb-visible devices, not just the first), `screencap_png_bytes()` (raw
  PNG bytes, no disk write — the mirror's frame source), `screen_size()`
  (needed to convert a tap's on-screen fraction into real device pixels),
  and threaded an optional `serial=` param through `_run`/`tap`/
  `press_key`/`battery_status`/etc. so commands can target a *specific*
  paired phone once more than one exists — previously every call
  silently used whichever device adb picked first.
- **`blaze/core/devices.py`**: added `get_device_name()` / `set_device_name()`
  / `get_device_names()` — a serial→friendly-name store, deliberately
  separate from the existing `alias`/`resolve_devices` system just above
  it in the same file (that one routes *spoken phrases* like "my phone"
  to a device *type* for voice commands; this one labels a *specific
  physical device* by its adb serial for display/picking purposes — same
  storage pattern, different concern, so they don't collide).
- **Tested in this sandbox**: `ChatWindow` and `ChatModeWindow` both
  construct and close cleanly headless (`QT_QPA_PLATFORM=offscreen`) with
  the panel wired in; `closeEvent` correctly stops the polling thread
  (verified `ChatModeWindow.closeEvent` forwards to the child widget,
  since `ChatWindow` is a central *widget* here, not top-level, so its
  own `closeEvent` would otherwise never fire). Every `android_control`/
  `devices` addition tested with no adb installed and fails gracefully
  (`adb_available() == False` path) rather than raising. **Not testable
  here**: the actual mirror against a real phone — frame rate, tap
  accuracy, and the rename UX all need a live device on your machine to
  confirm end-to-end.

## Part 4 — "open it again" bug (BLAZE forgot the last thing it opened)
You'd say "open my github profile in chrome" (works), then "open it
again" and BLAZE would reply "Attempting to open 'it again', sir." —
i.e. it tried to launch something literally named "it again", not your
GitHub profile. **This wasn't actually a missing-memory problem** — the
full conversation history genuinely is sent to the LLM every turn (see
`chat()`), so the model could see the earlier exchange. The real bug:
`domain.py`'s system prompt has a rule — "App name in tag must be
lowercase exactly as user said it" — needed so real app names survive
verbatim into `[SYSTEM:open_app:...]` tags, but with no carve-out for
vague follow-ups, so "it again" got the same literal treatment and was
passed straight to the launcher as if it were an app name.

Fixed at two levels:
- **Deterministic** (`blaze/ai/engine.py`): `BlazeAI` now tracks
  `_last_open_target`/`_last_close_target` — the actual resolved target
  string from the last successful `open_app`/`close_app`, not the raw
  words the user said. `_dispatch()` runs any `open_app`/`close_app` arg
  through a new `_resolve_vague_target()` first: if the arg is just a
  vague reference ("it", "it again", "that", "same thing", etc. — see
  `_VAGUE_REF_RE`) it's swapped for the last real target before it ever
  reaches `launcher.open()`. Real app names ("youtube", "instagram",
  "github profile in chrome") pass through completely unchanged.
- **Prompt-level** (`blaze/intelligence/domain.py`): `build_system_prompt`
  now takes the current `last_open_target` and states it explicitly in
  the CURRENT CONTEXT block, plus an explicit exception to the
  verbatim-copy rule telling the LLM to substitute the real prior target
  for "it"/"that"-style follow-ups instead of copying those words in —
  belt-and-suspenders with the deterministic fix above, since an LLM
  won't always follow prompt instructions perfectly on its own.
- **Tested in this sandbox**: unit-tested the regex/resolution helper
  directly (vague references resolve to the last target; real app names
  are untouched; no-op when nothing's been opened yet) and ran
  `BlazeAI._dispatch()` end-to-end with `launcher.open` mocked out —
  `open_app:"github profile in chrome"` → `open_app:"it again"` →
  correctly re-opened `"github profile in chrome"`, then
  `open_app:"youtube"` updated the tracked target normally. Not
  independently re-verified against a live Groq call in this sandbox
  (no network path here), so worth trying the exact "open X" → "open it
  again" sequence once on your machine.

## Part 5 — Phone mirror was ~1fps (worse than intended)
The mirror was always going to be modest (real screencap + PNG encode +
transfer per frame, not video), but it was doing noticeably worse than
even that honest ceiling, because of two bugs in `_MirrorWorker.run()`:
- **Double adb round trip per frame**: `list_devices()` (which runs
  `adb devices`) was being called on *every single loop iteration*, even
  once we already knew which phone we were mirroring — so every frame
  paid for two full adb subprocess calls instead of one.
- **Additive, not paced, sleep**: after each capture it did an
  *unconditional* `sleep(poll_ms)` on top of however long the capture
  itself had already taken — so a ~700ms screencap plus a flat 800ms
  sleep gave a real cadence of ~1.5s/frame, worse than "1fps."

Fixed both: device list is now only rechecked every ~3s (or immediately
after a failed capture, to catch a real disconnect), and the wait between
frames is now `max(0, floor - elapsed)` instead of always adding the full
floor on top. Modeled this with a quick timing simulation (see session
scratch) — roughly a 2.4x improvement under the same assumed per-call
costs. The phone-side PNG encode/transfer itself is still the real floor
underneath all this (genuinely ~1-2fps), so don't expect smooth video —
if that's actually what you need, that's the case for wiring up scrcpy's
real H.264 stream (`android_control.mirror_screen()`) instead, which is a
materially bigger job than this fix. **Not testable here**: actual fps
against a real phone — I can model the loop's timing logic but can't
measure a real screencap round trip without a device attached.

## Part 6 — actual real-time mirroring (embedded scrcpy), not just a faster poll
Part 5 fixed real bugs, but polling screenshots was always going to have a
real ceiling (~1-3fps, still a fresh capture+encode+transfer per frame) —
that's not "no lag," it's "less lag." Real "no lag" means genuine video,
which is a different mechanism entirely. Added it:

- **`blaze/gui/phone_mirror.py` now has two modes.** Mode 1 (new): launch
  `scrcpy` targeting the paired phone, then reparent its actual native
  window directly inside the panel via the Win32 `SetParent` API
  (`_ScrcpyEmbed`). What you see is scrcpy's own live H.264 decode — its
  real latency is tens of milliseconds, not the ~1-3fps ceiling of
  screenshot polling — and mouse clicks/drags on it go straight to
  scrcpy's window and are handled natively (real phone control, not our
  tap-forwarding approximation). Mode 2 is the Part 5 snapshot-polling
  panel, kept running the whole time as both the connection watcher (how
  we notice the phone connect/disconnect at all) and the automatic
  fallback the instant mode 1 isn't usable.
- **Mode 1 requires**: Windows, the `scrcpy` binary on PATH
  (already used by `android_control.mirror_screen()`), and the `pywin32`
  package (`pip install pywin32`) for `win32gui`/`win32con`. All three
  are checked via `embedding_supported()`; if any is missing, or scrcpy
  fails to open a window within 6s, or the reparent call itself errors,
  it fails over to mode 2 automatically — a small "live" (green) vs
  "snapshot" (grey) label in the panel header always shows which mode is
  actually active, so it's honest about what you're looking at rather
  than silently degrading.
- **Added `android_control.scrcpy_available()`**, mirroring the existing
  `adb_available()` pattern.
- **Tested in this sandbox**: the Win32 reparenting path itself
  (`_ScrcpyEmbed`) is fundamentally untestable here — no Windows, no
  pywin32, no scrcpy, no phone. It's written to the standard, documented
  Win32 pattern for embedding a foreign top-level window, but that's a
  code-review-level claim, not a verified one. What I *could* and did
  test, end-to-end, with real (not stubbed) code: the automatic-fallback
  wiring — forced `embedding_supported()` to report `True` (simulating a
  Windows+pywin32+scrcpy machine) and confirmed the panel attempts the
  embed, catches the real failure this sandbox naturally produces
  ("pywin32 not installed"), tears the failed embed down, and falls back
  to snapshot mode with the mode label and stacked-widget both updating
  correctly — all resolving synchronously within a single call, which is
  correct (same-thread direct Qt connection, not a queued one). Also
  separately verified the success path (mode label → "live", widget stack
  swaps to the embed, snapshot capture pauses to stop wasting adb calls)
  using a stand-in for `_ScrcpyEmbed` so that half of the panel's own
  logic — everything except the genuinely OS-specific reparenting call —
  is actually confirmed working, not just written. **Please test the real
  embed path on your machine** and tell me what happens; it's the one
  piece here I can't self-verify.

## Part 7 — real embed was live but blank; then letterboxed
Confirmed working on a real Windows machine with a real phone ("Motorola",
green dot, "live") — two visual bugs surfaced from that, both fixed:

- **Blank/black mirror despite "live" status.** The first embedding
  implementation used raw Win32 `SetParent` directly on the foreign HWND.
  That reparents it well enough to receive input (hence the correct
  "live" status), but Qt's own compositor has no idea a foreign window is
  sitting there and keeps painting over it — a known failure mode of that
  raw technique. Fixed by switching to the officially supported Qt
  mechanism instead: `QWindow.fromWinId()` wraps the foreign HWND as a
  real `QWindow`, then `QWidget.createWindowContainer()` embeds it
  properly inside Qt's widget/compositor hierarchy, which is what that
  API exists for. Dropped the manual `WS_CHILD`/style bit-twiddling and
  `MoveWindow` calls that came with the old approach too — Qt's layout
  system now handles sizing the container like any other widget.
- **Black bars down both sides once it was actually visible.** The mirror
  box was a fixed 200×400 (1:2), but phone screens are usually closer to
  9:19.5-9:20 — narrower — so the video was being pillarboxed inside a
  container shaped wrong for it. Fixed by deriving the panel's height
  from the phone's *actual* resolution (`android_control.screen_size()`,
  already being fetched) instead of a guessed fixed box —
  `_resize_mirror_to_aspect()` sets the container to the phone's real
  aspect ratio the moment it's known, capped at a sane max height as a
  guard against a bogus resolution value.
- **Tested in this sandbox**: same limits as before apply to the
  `createWindowContainer` embedding itself (still fundamentally needs a
  real Windows box + scrcpy + phone to verify visually) — but this time
  I could at least verify the *aspect-ratio math* concretely: stubbed
  `screen_size()` to a real-world 1080×2400 (20:9, close to what a
  Motorola typically reports) and confirmed the container resizes from
  the 200×400 placeholder to 200×444, matching that ratio to within
  rounding. Also re-ran the Part 6 fallback/success-path regression tests
  to confirm neither fix broke that wiring.

## Running it
```
pip install PySide6 psutil groq pyttsx3 SpeechRecognition edge-tts pyaudio
python -m blaze.gui.app_shell
```
For real-time (not snapshot) phone mirroring, also on Windows:
```
pip install pywin32
```
and install `scrcpy` (github.com/Genymobile/scrcpy) and put it on PATH.
Without those, the phone mirror panel still works, just in the slower
snapshot-polling mode.
Copy `.env.example` to `.env` and fill in your real keys.

