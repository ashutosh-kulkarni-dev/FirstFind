# Store UI Fixes — Implementation Plan

Six gaps between `FirstFind Store.dc.html` and the React `StoreDetail.jsx`.
Each fix is isolated to one or two files with no cross-cutting changes.

---

## Fix 1 — Save button hover: add `color` transition

**Files:** `app/frontend/src/styles.css`, `app/frontend/src/pages/StoreDetail.jsx`

**What:** Mockup spec is `border-color:#33a0e6; color:#0e5aa8` on hover.
React only swaps `borderColor` via inline `onMouseOver`/`onMouseOut`.

**Change:**
1. Add a `.save-btn` class to `styles.css`:
   ```css
   .save-btn {
     width: 100%; padding: 11px; border: 1px solid var(--line); border-radius: 11px;
     background: var(--surface); color: var(--ink); font-size: 13px; font-weight: 700;
     display: flex; align-items: center; justify-content: center; gap: 7px;
     transition: border-color .18s ease, color .18s ease;
   }
   .save-btn:hover { border-color: var(--brand-blue-2); color: var(--brand-blue-ink); }
   ```
2. In `StoreDetail.jsx`, replace the save `<button>` with `className="save-btn"` and remove the `onMouseOver`/`onMouseOut` handlers entirely.

---

## Fix 2 — Similar-store cards: hover lift + border highlight

**Files:** `app/frontend/src/styles.css`, `app/frontend/src/components/StoreCard.jsx`

**What:** Mockup spec: `transform:translateY(-2px); border-color:#33a0e6` on hover.
`.card` has no `:hover` rule. Cards are visually inert.

**Change:**
1. Add a modifier class to `styles.css`:
   ```css
   .card-link { transition: transform .18s ease, border-color .18s ease; }
   .card-link:hover { transform: translateY(-2px); border-color: var(--brand-blue-2); }
   ```
2. In `StoreCard.jsx`, add `card-link` to the `<Link>` `className`:
   ```jsx
   <Link to={...} className="card card-link" style={{ ... }}>
   ```

---

## Fix 3 — Similar-store rating: star emoji + score instead of `ScorePill`

**Files:** `app/frontend/src/components/StoreCard.jsx`

**What:** When used in the similar-stores sidebar, mockup shows `⭐ {rating}` in a
tinted chip + match %. Currently shows `ScorePill` (no star) in all contexts.

**Change:**
`StoreCard` already receives `match` only in the similar-stores context. Use that
to branch the score display:

```jsx
<div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
  {match != null ? (
    // Similar-stores context: star + numeric score matches mockup spec
    <ScorePill score={store.experience_score} star />
  ) : (
    <ScorePill score={store.experience_score} />
  )}
  ...
</div>
```

Add a `star` boolean prop to `ScorePill`:
```jsx
// ScorePill.jsx — prepend ⭐ when star prop is true
export default function ScorePill({ score, star }) {
  ...
  return <span className="score-pill" style={{ background, color }}>
    {star ? `⭐ ${display}` : display}
  </span>
}
```

---

## Fix 4 — Live sentiment: show to guests, not just logged-in users

**Files:** `app/frontend/src/pages/StoreDetail.jsx`

**What:** Mockup shows the live sentiment label whenever `hasDraft` is true —
no auth gate. React hides it with `user && livePreview`.

**Change:** Single-line removal of the `user &&` guard:

```jsx
// Before
{user && livePreview && (
// After
{livePreview && (
```

---

## Fix 5 — Optimistic review insert: appear instantly on post

**Files:** `app/frontend/src/pages/StoreDetail.jsx`

**What:** Mockup prepends the new review to local state immediately.
React waits for the API round-trip before the review appears.

**Change:** Add a single `pendingReview` state slot (null or a review object).

```js
const [pendingReview, setPendingReview] = useState(null)
```

In `postReview()`, before the API call:
```js
const optimistic = { id: '__pending', user_name: user?.name || 'You',
  rating: r, text, sentiment: null, _pending: true }
setPendingReview(optimistic)
setDraft(''); setRating(0)
```

On API success (after `await load()`):
```js
setPendingReview(null)
```

On API error:
```js
setPendingReview(null)
setDraft(text); setRating(r)   // restore draft so the user doesn't lose their text
```

Render reviews as:
```jsx
{[...(pendingReview ? [pendingReview] : []), ...(store.reviews || [])].map(r => (
  ...
))}
```

Style the pending item lightly (opacity) to signal it is being saved:
```jsx
<div key={r.id} className={`review-item ${flagged ? 'flagged' : ''}`}
  style={r._pending ? { opacity: .6 } : undefined}>
```

No new abstractions — one state slot, three call sites.

---

## Fix 6 — Review count: use live list length, not `ss.total`

**Files:** `app/frontend/src/pages/StoreDetail.jsx`

**What:** `ss.total` is computed by the backend asynchronously and lags after a
post. The count should reflect what is actually rendered.

**Change:** Replace `ss.total` in the count badge with the rendered list length.
After fix 5 is applied this naturally includes the pending entry:

```jsx
// Before
<span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>{ss.total} reviews</span>

// After
const reviewCount = (store.reviews || []).length + (pendingReview ? 1 : 0)
<span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>{reviewCount} reviews</span>
```

`ss.total` is still used for the sentiment bar proportions (positive/neutral/negative %)
which the backend owns — that's fine and unchanged.

---

## Execution order

Apply in this sequence to avoid merge conflicts:

1. `styles.css` — add `.save-btn`, `.card-link`, `.card-link:hover` (Fixes 1 & 2)
2. `ScorePill.jsx` — add `star` prop (Fix 3)
3. `StoreCard.jsx` — add `card-link` class, branch score display (Fixes 2 & 3)
4. `StoreDetail.jsx` — apply all four JSX changes (Fixes 1, 4, 5, 6)

Each fix touches a discrete part of the file. No shared state, no new components,
no helper files.
