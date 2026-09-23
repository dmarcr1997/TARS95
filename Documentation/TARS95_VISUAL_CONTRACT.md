# TARS/95 Visual Contract

**Work action:** UI-007

**Status:** Active design authority; visual proof approval is due in UI-012

**Primary target:** Raspberry Pi 5 robot displays at 480×320 landscape and 480×800 portrait

**Direction:** 60% Windows 95 interaction grammar / 40% original late-90s anime instrumentation

## 1. Purpose and authority

This document is the binding visual and interaction contract for UI-008 onward. New device and web interface work must use these rules unless a later reviewed commit changes the contract explicitly.

TARS/95 should feel like a practical robot operating system from an alternate timeline where the Windows 95 era never ended. It combines sturdy desktop controls with dense, high-contrast machine instrumentation. The result must remain original: use the eras as design inputs, but do not reproduce Microsoft trademarks, character art, production logos, or recognizable interface compositions from specific anime.

The interface is not generic cyberpunk. Avoid glassmorphism, neon-purple gradients, excessive glow, rounded mobile-app cards, decorative particle fields, and animation without state meaning.

## 2. Product hierarchy

### Eyes is home

The robot boots through a short self-test and lands on **Eyes**. Eyes is the living home surface, not a secondary app or screensaver. It gets the largest uninterrupted visual area and the clearest expression of machine state.

From Eyes, the operator must have an obvious touch-accessible way to open the shell or launcher. A hidden gesture may be an optional shortcut, never the only route. A Home action from any other surface returns to Eyes. Warning and fault presentation can override any surface.

The target robot information architecture is:

1. **Eyes** — home, presence, immediate machine state, and concise alerts.
2. **Systems** — power, CPU, network, temperature, memory, and subsystem health.
3. **Comms** — microphone, wake/listening state, speech processing, TTS, audio, and conversation.
4. **Vision** — camera availability, privacy, processing, detections, and errors.
5. **Motion** — locomotion and deliberate safety controls.

Clock information belongs in idle/status presentation. Avatar presentation is secondary to Eyes. Existing remote-control behavior should be consolidated into Motion. Detailed logs, configuration, editing, and administration should primarily live in the web console. This is the target architecture for the UI-012 proof and later build work; UI-007 does not change runtime navigation.

## 3. Display and performance contract

| Target | Physical output | Logical draw surface | Production transform |
|---|---:|---:|---|
| Primary robot display | 480×320 landscape | 320×480 portrait | Rotate 270° |
| Secondary display | 800×480 landscape | 480×800 portrait | Rotate 270° |
| Installed portrait display | 480×800 portrait | 800×480 landscape | Rotate 270° |

Review device compositions at the **physical output size**. Build pygame layouts against the logical surface used by production. Do not treat the desktop preview control rail as part of the robot canvas.

- Target 30 FPS on Raspberry Pi 5.
- Derive UI scale from the limiting axis: `min(width / 480, height / 320)`. Extra portrait height creates layout space; it must not enlarge typography past the available width.
- Prefer opaque fills, cached text, integer-aligned geometry, and small dirty regions.
- Avoid continuous full-screen alpha effects, blur, heavy particles, and unnecessary per-frame asset scaling.
- Static chrome may be detailed; moving elements should be sparse and purposeful.
- Primary critical touch targets are at least 40×40 physical pixels.
- Secondary touch targets are at least 32×32 physical pixels, with at least 8 physical pixels between unrelated actions.
- Critical controls must not depend on hover or precision input.

## 4. Color system

These tokens are the shared source values for pygame primitives and the offline web theme.

| Token | Hex | Use |
|---|---|---|
| `canvas-black` | `#050708` | Deep background and inactive display area |
| `desktop-teal` | `#167C79` | Desktop field and non-critical identity color |
| `chrome-face` | `#D8C99B` | Warm manila window, button, and toolbar face |
| `chrome-highlight` | `#FFF2C2` | Warm raised top/left bevel |
| `chrome-mid` | `#8E805C` | Secondary bevel and disabled detail |
| `chrome-shadow` | `#222222` | Recessed edge and strong outline |
| `title-navy` | `#031C55` | Active title bar and selected structural region |
| `screen-ink` | `#081116` | Instrument display background |
| `text-paper` | `#E8E3D1` | Primary text on dark surfaces |
| `phosphor-cyan` | `#16D9C4` | Listening, live link, and active sensor data |
| `phosphor-green` | `#38E878` | Talking, confirmed success, and healthy live output |
| `signal-amber` | `#FFB000` | Thinking, caution, attention, and scan accents |
| `fault-red` | `#F04436` | Faults, destructive actions, and hard stops |
| `offline-gray` | `#6F777A` | Unknown, disabled, disconnected, or unavailable |

Do not use accent colors as decoration everywhere. Warm manila is structural chrome, not a warning or a paper-texture effect. Chrome supplies the Windows-era structure; signal colors communicate live state. Every status color must be paired with a label and, where space permits, a distinct icon or shape.

## 5. Machine-state presentation

The same state name and meaning must appear on Eyes, the shell, diagnostics, and the web console.

| State | Primary signal | Eyes behavior | Required label | Motion rule |
|---|---|---|---|---|
| Booting | `#2F77D0` blue | Eyes unavailable until self-test handoff | `BOOTING` | Stepped progress only |
| Standby | `#78909C` gray-blue | Calm neutral eyes; normal blink | `STANDBY` | Minimal ambient motion |
| Listening | `#16D9C4` cyan | Alert/open expression tied to actual mic state | `LISTENING` | Respond to real input level, not a fake waveform |
| Thinking | `#FFB000` amber | Focused expression | `PROCESSING` | Restrained stepped scan at 8–12 FPS |
| Talking | `#38E878` green | Expressive eyes coordinated with real playback | `TALKING` | Activity follows actual audio output |
| Warning | `#FFB000` amber | Concerned expression; alert summary stays visible | `WARNING` | Pulse no faster than 2 Hz |
| Fault | `#F04436` red | Decoration yields to the fault and next safe action | `FAULT` | No strobe; only acknowledgement feedback |
| Offline | `#6F777A` gray | Eyes may remain present, but affected links are explicit | `OFFLINE` | No simulated activity |

State transitions should feel mechanical: hard cuts or stepped changes lasting 80–160 ms. Do not use bounce, elastic easing, or cinematic wipes. Organic eye blinks and gaze movement are allowed because they express presence, not interface decoration. Reduced-motion settings remove sweeps, pulses, and nonessential transitions without hiding state.

## 6. Typography

Core UI must work without internet access. Use repository-owned font files and system fallbacks only; do not load Google Fonts or another CDN.

| Role | Preferred local asset | Physical size | Rule |
|---|---|---:|---|
| Window titles and compact controls | `pixelmix.ttf` | 12–14 px | Short labels; high contrast |
| Telemetry, console, and values | `mono.ttf` or `assets/vga.ttf` | 11–14 px | Tabular alignment where possible |
| Primary Eyes status | `assets/AlteHaasGroteskBold.ttf` or `assets/retro.ttf` | 18–24 px | One dominant line only |
| Captions and identifiers | `mono.ttf` | 9–10 px | Never smaller than 9 physical px |

Use all caps for state names, subsystem labels, and compact commands. Use sentence case for explanations and conversational content. Do not put long body copy in a decorative pixel face. Preserve exact wording for safety states across device and web surfaces.

## 7. Geometry and chrome

- Use a 4 px base grid.
- Use 8 px outer margins and 4 or 8 px internal gaps.
- Use 1 px rules. Reserve 2 px bevels for manila shell chrome and deliberate physical controls; dark instrument panels stay flat and never receive neon bevels. Do not stack more than three visible border layers.
- Standard physical title bar height is 22 px.
- Standard physical status strip height is 18 px.
- Standard physical taskbar/launcher rail height is 28 px.
- Device surfaces use square corners. Web surfaces may use at most a 2 px radius where platform rendering needs it.
- Raised controls use highlight on top/left and shadow on bottom/right. Pressed or recessed controls invert that relationship.
- Anime-influenced asymmetry belongs in readouts, crops, index marks, and instrumentation—not in the placement of core safety controls.
- Hazard stripes are reserved for warnings, faults, maintenance, and motion boundaries. They are not general decoration.

Eyes should not be trapped inside a tiny desktop window. The home composition may use edge chrome and a compact status/launcher layer, but the eyes remain visually dominant.

## 8. Icons and marks

Use an original pixel icon set at 16×16 and 24×24. Icons must remain legible without antialiasing at the primary display size. Critical actions always include text; icon-only controls are limited to familiar, reversible actions with sufficient context.

Do not copy Windows icons, anime insignia, faction marks, title treatments, or character silhouettes. TARS/95 needs its own system mark and subsystem symbols.

## 9. Sensor truthfulness

The interface reports known machine state and never fabricates reassuring telemetry.

- Microphone states: `MUTED`, `READY`, `LISTENING`, `CLIPPING`, or `ERROR`. A waveform moves only from actual sampled input.
- Vision states: `OFF`, `READY`, `PROCESSING`, `PRIVACY`, or `ERROR`. Camera activity and privacy must be visible whenever vision is accessible.
- Audio states: `MUTED`, `READY`, `PLAYING`, or `ERROR`. Playback animation follows real output.
- Battery and thermal values use `N/A` when unavailable; they never default to a healthy-looking number.
- Connectivity distinguishes local robot availability from internet availability. A disconnected link is never green.
- Stale data is labeled `STALE` with age when available.

## 10. Interaction and safety

- `STOP`, `NEUTRAL`, and `DISABLE SERVOS` are visually and behaviorally distinct.
- Destructive, movement-enabling, shutdown, restart, and configuration-reset actions require a deliberate second step.
- Emergency and stop controls are never hidden below scroll, behind a gesture, or inside a generic overflow menu.
- Touch, mouse, and web keyboard focus have a visible state.
- Disabled controls remain legible and explain why they are unavailable when space permits.
- Faults identify the affected subsystem and give the next safe operator action.
- Initial Raspberry Pi validation runs with servo power disconnected or movement otherwise disabled.

## 11. Copy and personality

System copy is terse, factual, and calm:

- `LISTENING`
- `PROCESSING 02.4s`
- `VISION LINK LOST`
- `MIC INPUT CLIPPING`
- `BATTERY N/A`
- `MOTION DISABLED`

Do not use playful error copy such as “Oops.” TARS may use dry humor in conversation and non-critical reactions, but safety, privacy, warnings, and faults stay unambiguous.

## 12. Relationship to the web console

The device and web console share tokens, state names, icons, and safety meanings. They do not need identical layouts. The device prioritizes presence, immediate status, and touch. The web console may expose denser telemetry, configuration, logs, content editing, and responsive desktop/mobile navigation.

Core web theme CSS, fonts, icons, and scripts must load offline. Responsive layouts must keep connection state and critical actions visible without horizontal scrolling.

## 13. Acceptance gate for UI-008 through UI-012

The foundation phase is ready for approval when:

- UI-008 implements these color/type tokens as a selectable offline web theme.
- UI-009 implements matching pygame window, title, panel, button, lamp, label, and hazard primitives.
- UI-010 supplies original 16 px and 24 px icons with labeled critical actions.
- UI-011 maps all eight machine states to consistent device/web copy, color, icon/shape, and motion behavior.
- UI-012 produces a static 480×320 physical proof with Eyes dominant, an obvious launcher path, visible machine state, and one representative sensor or fault condition.
- The UI-012 proof is reviewed at exact physical size before the production shell or app screens are rebuilt.
- No foundation change reaches hardware, camera, microphone, audio output, GPIO, servos, shutdown, Wi-Fi mutation, or tunnel actions from preview mode.

## 14. Phase 2 entry information

Before the first Raspberry Pi display/touch integration, record the exact touchscreen/controller model, native orientation, connection type, touch-driver behavior, and enclosure viewing constraints. Microphone, camera, speaker/audio output, power telemetry, and servo safety paths should each have an explicit available/unavailable/error fixture before their production surfaces are connected.

Until the UI-012 proof is approved, visual work should remain in tokens, primitives, icons, state definitions, and static proof composition rather than a broad production rewrite.
