# Home UI Changes — Implementation Plan

## Affected files
- `app/frontend/src/pages/Landing.jsx`
- `app/frontend/src/styles.css`

No new files. No new dependencies.

---

## Change 1 — Remove "First-visit match rate" card

**What:** Delete the `lp-stat-num` article (the animated `95%` counter) and the dead code it leaves behind.

**Lines to delete in `Landing.jsx`:**
- `useCountUp` hook — lines 12–28 (entire function, remove completely)
- `const pct = useCountUp(95, mounted)` — line 41
- `const [mounted, setMounted] = useState(false)` — line 37
- `setMounted(true)` inside the second `useEffect` — line 52
- The `<article className="lp-stat-num">…</article>` block — lines 185–191

The `lp-stat-num` CSS class stays in `styles.css`; it is reused in Change 3.

---

## Change 2 — Page exit animation (Landing → other pages only)

**What:** When any nav link on the Landing page leads away from `/`, play a short fade-out-up before navigating. No animation fires on any other page-to-page transition.

**`styles.css` — add inside the landing block:**
```css
@keyframes ffExitUp {
  to { opacity: 0; transform: translateY(-20px); }
}
.lp-exit {
  animation: ffExitUp .26s cubic-bezier(.4,0,1,1) forwards;
  pointer-events: none;
}
```

**`Landing.jsx` — wiring:**
1. Add `useNavigate` to the react-router-dom import line.
2. Inside `Landing()`, add:
   ```js
   const navigate = useNavigate()
   const exitTo = (dest) => (e) => {
     e.preventDefault()
     document.querySelector('.lp').classList.add('lp-exit')
     setTimeout(() => navigate(dest), 260)
   }
   ```
3. Replace every `<Link>` in the Landing nav/hero that points away from `/` with a plain `<a>` using `onClick={exitTo(dest)}`. Specifically:
   - `<Link to="/explore">EXPLORE</Link>` → `<a href="/explore" onClick={exitTo('/explore')}>EXPLORE</a>`
   - `<Link to="/chat">ASSISTANT</Link>` → `<a href="/chat" onClick={exitTo('/chat')}>ASSISTANT</a>`
   - `<Link to="/lists" …>♥ SAVED</Link>` → `<a href="/lists" … onClick={exitTo('/lists')}>♥ SAVED ({saved})</a>` (keep `ref={savedRef}` and `onClick` combined via wrapper or merge handlers)
   - `<Link to="/auth" …>LOG IN</Link>` → `<a href="/auth" … onClick={exitTo('/auth')}>LOG IN</a>`
   - `<Link to="/explore" className="lp-cta-sm lp-open">OPEN APP</Link>` → `<a … onClick={exitTo('/explore')}>OPEN APP</a>`
   - `<Link to="/explore" className="lp-explore-btn">` → `<a … onClick={exitTo('/explore')}>`
4. The `<Link to="/">HOME</Link>` nav item stays as-is (same-page, no exit animation).
5. The `<Link to="/" className="lp-logo">` stays as-is.

> Scope guarantee: `exitTo` and `.lp-exit` only exist inside `Landing`. No other page carries this logic.

---

## Change 3 — Rename section header

**`Landing.jsx` line 179:**

```jsx
// Before
<h2 className="anton" style={{ color: '#fff', fontSize: 'clamp(26px,3.4vw,36px)' }}>TRUST &amp; STATS</h2>

// After
<h2 className="anton" style={{ color: '#fff', fontSize: 'clamp(26px,3.4vw,36px)' }}>OUR FEATURES</h2>
```

---

## Change 4 — Redesign the three feature cards

The `lp-stats` grid currently holds: `[lp-stat-img] [lp-stat-num] [lp-stat-img]`.
After Change 1, the middle card (`lp-stat-num`) is empty — it is repurposed here, not removed.

### Card 1 — Explore / Map (image background, same style)
- Keep `lp-stat-img` class and existing Unsplash image.
- Wrap the entire `<article>` in `<a href="/explore" onClick={exitTo('/explore')}>` so clicking navigates with the exit animation.
- Inside the caption overlay (`lp-stat-cap`), add a small heading above the caption text:
  ```jsx
  <div className="lp-stat-cap">
    <span style={{ display: 'block', fontWeight: 700, color: '#fff', fontSize: 13, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.5px' }}>Explore</span>
    Explore stores around you on our live map
  </div>
  ```
- Add `style={{ cursor: 'pointer' }}` to the article so hover signals interactivity.

### Card 2 — Live store count (white numeric background, middle card)
- Keep `lp-stat-num` class (same white-card style).
- Replace content entirely:
  ```jsx
  <article className="lp-stat-num">
    <small>Stores in<br />Bengaluru</small>
    <div className="anton" style={{ fontSize: 46, lineHeight: 1, marginTop: 10, color: 'var(--ink)' }}>
      {stats?.stores ?? '—'}
    </div>
    <div style={{ marginTop: 6, color: 'var(--ink)', fontSize: 11.5, lineHeight: 1.35 }}>
      verified thrift stores, updated as new ones join.
    </div>
  </article>
  ```
- `stats.stores` is already fetched on mount (line 54–56) — no new API call needed. The number updates automatically when new stores are added because it reads from the live API on each page load.

### Card 3 — Chat assistant (image background, same style)
- Keep `lp-stat-img` class and existing Unsplash image.
- Wrap in `<a href="/chat" onClick={exitTo('/chat')}>` (consistent with Card 1).
- Inside the caption overlay (`lp-stat-cap`), add a small heading above the caption text:
  ```jsx
  <div className="lp-stat-cap">
    <span style={{ display: 'block', fontWeight: 700, color: '#fff', fontSize: 13, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.5px' }}>Assistant</span>
    Chat with our AI assistant — let us plan your perfect thrift trip
  </div>
  ```

---

## State/hook cleanup summary

| Item | Action | Reason |
|------|--------|--------|
| `useCountUp` hook | Delete | Only fed `pct` |
| `pct` variable | Delete | No longer rendered |
| `mounted` state | Delete | Only used as `run` flag for `useCountUp` |
| `setMounted(true)` call | Delete | `mounted` removed |
| `savedRef` | Keep | Still used by `pulseSaved` |
| `cardOpen / cardRef / cardMove / cardLeave` | Keep | Glass card still present |
| `stats` state | Keep | Now powers Card 2 store count |

---

## Implementation order (safe, non-breaking)

1. Do Change 1 first — remove dead code before touching layout.
2. Add CSS in Change 2 (`ffExitUp` + `.lp-exit`) before wiring JS.
3. Wire `exitTo` in Change 2 — test navigation works.
4. Apply Change 3 (one-line text swap).
5. Apply Change 4 card redesigns top-to-bottom.
6. Smoke-test: visit `/`, verify store count shows, click each card/nav link, confirm animation fires only from `/`.
