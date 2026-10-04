# Help Desk Design System

A faithful design system for the **college student support ticketing platform** — a React/Vite web app that lets students navigate a guided decision-tree chat to self-serve answers or raise support tickets, and gives administrators a console to respond, update statuses, configure the decision tree, and view analytics.

---

## Sources

| Source | Path / Link |
|--------|-------------|
| Frontend codebase (React/Vite) | `mvp test/mvp18-frontend/` |
| Backend codebase (FastAPI/Python) | `mvp test/mvp18-backend/` |
| Product documentation | `mvp test/features_guide.md`, `mvp test/system_workflow.md`, `mvp test/UX_AND_RECOMMENDATIONS.md` |

---

## Products

| Surface | Accent | URL | Description |
|---------|--------|-----|-------------|
| **Student Help Desk** | Blue `#2563eb` | `/student` | Guided chat → self-serve answer or ticket creation; ticket list + thread panel |
| **Admin Portal** | Purple `#7c3aed` | `/admin` | Ticket management, decision-tree editor, analytics dashboard |

---

## Content Fundamentals

**Tone:** Warm, institutional, direct. The copy never talks down to students. Errors are informative, not alarming.

**Voice:** Second-person ("your ticket", "you will receive a response"). First-person only for the system voice ("Our team will respond…").

**Casing:** Sentence-case for all body copy, labels and messages. UPPERCASE is reserved for 10–12 px micro-labels and status badges only.

**Verbs:** Action-first in buttons ("Sign In", "Submit Feedback", "Raise a Ticket", "Start a new request"). Never passive ("Click here to submit").

**Numbers:** Time estimates are always a range ("within 24–48 hours", "3–5 working days"). Counts above 9 collapse to "9+" in badge chips.

**Emoji:** Used sparingly, in functional roles only (tab labels `🎟 🗂 📊`; notification bell `🔔`; attachment `📎`; link `🔗`; checkmark `✅`). Never decorative. Never in bubble copy.

**Markdown:** Support bubbles strip `**bold**` markers before rendering — the product intentionally renders plain text, not formatted markdown.

**Error messages:** Start with a clear statement of what failed ("Invalid credentials", "Could not send your message"). Never technical stack traces.

---

## Visual Foundations

### Colors
Two-brand system on a shared neutral base:
- **Student portal** — Blue accent (`#2563eb`) for all primary actions, chat bubble fills, focus rings and breadcrumbs.
- **Admin portal** — Purple accent (`#7c3aed`) swapped in via `.admin-portal` scope; same layout, different accent.
- **Neutral canvas** — Off-white `#f5f6f8` page, white `#ffffff` surfaces, `#e2e5ea` hairlines, `#6b7280` muted text, `#1a1d23` primary ink.
- **Semantic states** — Green (success/resolved), Orange (pending/warning/ticket), Red (danger/destructive). Each hue ships as base · tint · border triplet.

### Typography
Single font: **Inter** (weights 400/500/600, occasionally 700). Loaded from Google Fonts. No display faces. Type is dense and functional — 10 px micro-labels up to 28 px dashboard KPI values.

### Spacing & Layout
Base-8 rhythm. Header is always 56 px. Tickets panel is 380 px fixed. Chat column max 640 px centred. All page scrolling is internal (chat area, panel body, admin view) — the outer shell never scrolls (`overflow:hidden`).

### Cards & Surfaces
Flat — hairline `1px` borders carry visual separation; no box-shadows on cards or list items. Shadows only appear on floating surfaces (login card, modal, toast). Corner radii range from `4px` (bubble tail) to `16px` (login card), with `8px` for controls and `12px` for cards/panels.

### Animations
Fade-up entrance (`opacity 0→1, translateY 6px→0`, 200 ms ease) on chat messages and interactive cards. Skeleton shimmer on list loads. Typing indicator bouncing dots. Toast slides up from bottom. No decorative loops or physics-based spring — transitions are quick and functional.

### Hover / Press states
- Solid buttons: darken the accent (`blue-dk` / `purple-dk`).
- Outline / ghost buttons: tint background to `accent-lt`, border to accent.
- List items: tint to `--bg`.
- Destructive actions: two-click "arm" pattern instead of window.confirm — first click shows an inline red warning, second executes. Replaces native dialogs.
- Disabled: opacity reduces (buttons to disabled colour, dimmed elements to ~55–60%).

### Borders & Separation
`1px solid var(--border)` everywhere. No outer glow, no double-border effects. Left-border accent rail used only on KPI tiles (`.dash-kpi-card.accent-*`) — avoid elsewhere.

### Backgrounds
Flat. No gradients, no full-bleed images, no textures. The light grey canvas (`#f5f6f8`) is the only background variation — all panels and the chat view sit on white surfaces inside it.

### Use of Blur / Transparency
Modal scrim is `rgba(0,0,0,.35)` — simple dim, no blur. No backdrop-filter anywhere.

### Imagery
No photography or illustrations in the UI. Icons are inline stroke SVGs (Feather / Lucide style: 2px stroke, round caps/joins) for structural marks, supplemented by emoji for tab labels and inline accents.

---

## Iconography

- **Structural icons**: Inline SVGs, Feather/Lucide style. 2px stroke, round line caps and joins. Sizes: 16×16 px in header chips, 22×22 px in login/header icons, 10×10 px in status-card circles.
- **Tab labels**: Emoji (🎟 🗂 📊) — functional, not decorative.
- **Inline accents**: Emoji (📎 🔗 ✅ 🔔 ✏️) used at 13–14 px adjacent to text. Not in headings.
- **Brand marks**: Two marks are saved under `assets/`:
  - `mark-student.svg` — speech-bubble SVG (stroke, Feather style); renders white on the blue chip.
  - `mark-admin.svg` — person-in-circle SVG (fill); renders white on the purple chip.
- **No icon font** — the product does not use Font Awesome, Heroicons or any icon web font. All icons are inline SVG or emoji.

---

## File Index

```
styles.css                          ← link this one file; it imports everything

tokens/
  colors.css                        ← full colour palette + semantic aliases
  typography.css                    ← Inter font family, scale, weights
  spacing.css                       ← spacing scale, radii, shadows, motion tokens
  fonts.css                         ← Google Fonts @import (Inter)

base/
  reset.css                         ← box-sizing, body font, .hd-shell
  components.css                    ← all product component classes (faithful port)
  primitives.css                    ← DS-only generics: .hd-btn, .hd-input, .hd-choice, …

assets/
  mark-student.svg                  ← speech-bubble brand mark (stroke)
  mark-admin.svg                    ← person-in-circle admin mark (fill)

guidelines/
  colors-neutrals.card.html         ← [Colors] Neutral palette specimen
  colors-blue.card.html             ← [Colors] Blue / student accent ramp
  colors-purple.card.html           ← [Colors] Purple / admin accent ramp
  colors-semantic.card.html         ← [Colors] Green / Orange / Red semantics
  type-family.card.html             ← [Type] Inter weights specimen
  type-scale.card.html              ← [Type] 10–28 px scale specimen
  spacing-scale.card.html           ← [Spacing] Spacing bar chart
  radii-elevation.card.html         ← [Spacing] Radii + shadow specimen
  brand-marks.card.html             ← [Brand] Two portal marks in context

components/
  buttons/    Button, OptionButton, ChoiceButtons   ← action buttons + chat controls
  forms/      Input, Textarea, Select, ChoiceTile   ← all form fields
  feedback/   StatusBadge, Badge, StarRating,        ← status, ratings, loaders, toasts
              Toast, Skeleton
  overlay/    Modal                                  ← dialog / node editor
  navigation/ Tabs                                   ← admin underline tab bar
  chat/       ChatBubble, TypingIndicator,            ← chat & thread bubbles
              ThreadMessage
  data/       KpiCard                                ← dashboard metric tiles

ui_kits/
  student/    index.html + StudentApp.jsx + data.js  ← interactive student portal
  admin/      index.html + AdminApp.jsx + data.js    ← interactive admin console
```

---

## Quick-start for consumers

```html
<!-- 1. Link the single stylesheet -->
<link rel="stylesheet" href="path/to/styles.css" />

<!-- 2. Load the component bundle -->
<script src="path/to/_ds_bundle.js"></script>

<!-- 3. Mount a component -->
<script type="text/babel">
  const { Button, StatusBadge } = window.HelpDeskDesignSystem_60f508;
  // …use in your JSX
</script>
```

For admin surfaces, wrap the root element in `class="admin-portal"` to switch the accent from blue to purple.
