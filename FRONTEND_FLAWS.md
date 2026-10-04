# ThriftFind Frontend — Audit of Flaws

> Audited: all pages (Landing, Explore, Chat, StoreDetail, Zones, Auth, Lists) and all components.  
> Severity: **Critical** → breaks a feature | **Significant** → degrades UX badly | **Minor** → cosmetic or edge-case

---

## Critical Bugs

### 1. Zones page ignores "Open on Map" deep-link URL params
**File:** `src/pages/Zones.jsx`  
**File:** `src/pages/Lists.jsx:54`

When Lists navigates to `/zones?lat=X&lng=Y&radius=Z&mode=draw`, Zones.jsx never reads `useSearchParams()`. The page always opens in `zones` mode centered on Indiranagar regardless of the URL. The "Open on Map" button in Lists is effectively a no-op — the user ends up in the wrong place.

**Fix:** Add `useSearchParams()` in Zones and apply `lat`/`lng`/`radius`/`mode` from the URL on mount.

---

### 2. Instagram link is a dead anchor (`href="#"`)
**File:** `src/pages/StoreDetail.jsx:99`

```jsx
{store.instagram && <a href="#">{store.instagram}</a>}
```

Clicking the Instagram handle does nothing — it just jumps to the top of the page. Should link to `https://instagram.com/${handle.replace('@', '')}` in a new tab.

---

### 3. DrawControls area selector has no fallback option for GPS / custom location
**File:** `src/components/zones/DrawControls.jsx:6-20`  
**File:** `src/pages/Zones.jsx:93-104`

When the user clicks GPS, `area` state is set to `''`. But the `<select>` has no `<option value="">` — so the select snaps back to whichever option renders first (Indiranagar visually), even though the actual map center is the GPS location. The UI lies about where the radius is centered.

**Fix:** Add `<option value="">Custom location</option>` as the first option.

---

## Significant Bugs

### 4. `window.location.href` used in Explore instead of React Router `navigate`
**File:** `src/pages/Explore.jsx:100`

```jsx
onView={(id) => { window.location.href = `/store/${id}` }}
```

This triggers a full browser page reload when clicking "View store →" in a map popup. All React state (filters, selected store) is lost. Should use `useNavigate` for a SPA transition.

---

### 5. `setTimeout(load, 3000/7000)` leaks after unmount in StoreDetail
**File:** `src/pages/StoreDetail.jsx:38-40`

After posting a review, two `setTimeout` calls fire at +3s and +7s to reload the store (waiting for the sentiment pipeline). There is no cleanup: if the user navigates away before these timers fire, they still execute and try to call `setStore()` on an unmounted component, causing a React warning and a wasted API call.

**Fix:** Store the timer IDs and cancel them in a `useEffect` cleanup.

---

### 6. Guest transcript claiming uses a stale `messages` closure
**File:** `src/components/ChatCore.jsx:38-47`

```js
useEffect(() => {
  if (!user || claimedRef.current) return
  const guestTurns = messages   // closure captures messages at time user changed
    .filter(...)
    ...
}, [user])   // messages NOT in deps
```

The `messages` array referenced here is the value at the time `user` first became truthy — if messages updated in the same render cycle, those turns are missed. The correct approach is to include `messages` in deps or use a ref to always hold the latest messages.

---

### 7. AbortController signal is never passed to `api.findCluster`
**File:** `src/hooks/useDrawCluster.js:22-24`

An `AbortController` is created on every debounce tick and the signal is checked (`controller.signal.aborted`), but the signal is **not passed** to `api.findCluster(...)`. In-flight requests are never actually cancelled at the network level — only their results are silently dropped. On a slow connection, many redundant requests pile up as the user drags the radius slider.

**Fix:** Pass `{ signal: controller.signal }` through `api.findCluster` → `req()`.

---

### 8. No 404 catch-all route
**File:** `src/App.jsx`

There is no `<Route path="*" element={...} />`. Navigating to any unknown path (e.g., `/about`, `/storee/xyz`) renders a completely blank page with no navigation. Users have no way to recover without using the browser back button.

---

### 9. "SAVED" counter links to `/explore`, not `/lists`
**File:** `src/components/Navbar.jsx:37`  
**File:** `src/pages/Landing.jsx:67`

```jsx
<Link to="/explore" className="nav-chip" title="Saved stores">♥ SAVED ({saved})</Link>
```

The saved-stores counter chip in both the Navbar and the Landing page hero nav links to `/explore`, not `/lists`. Clicking "SAVED (N)" takes the user to the generic store browser, not their saved collections.

---

### 10. Floating chat widget and `/chat` page have separate, isolated message state
**File:** `src/components/ChatWidget.jsx`  
**File:** `src/pages/Chat.jsx`

`ChatWidget` mounts its own `<ChatCore compact />` instance; the Chat page mounts a second independent `<ChatCore />`. Conversation state (messages) is held in component state and is not shared. If a user starts a conversation in the floating widget and then navigates to `/chat`, their conversation is gone. The session ID (`tf_chat_session`) is shared via sessionStorage so the backend thinks it's the same session, but the frontend shows an empty thread.

---

## UX / Design Issues

### 11. Hardcoded "4.8 / 360 reviews" in Landing Discover section
**File:** `src/pages/Landing.jsx:103-108`

The DISCOVER section always shows `4.8` average rating and `360 verified reviews` as static JSX strings — these are never fetched from the API. They present demo data as live facts.

---

### 12. Landing stats show hardcoded fallback values as real numbers
**File:** `src/pages/Landing.jsx:35`

```js
const [stats, setStats] = useState({ stores: 48, areas: 12, zones: 4 })
```

If any API call fails, the UI shows `48 verified stores across 12 Bengaluru neighbourhoods` as if it were accurate. The fallback should be `null` or a loading state, not specific numbers.

---

### 13. Zones map badge is misleading when center is already placed
**File:** `src/components/ZonesMap.jsx:119`

```js
const badge = mode === 'draw' ? 'DRAW MODE · CLICK TO SET CENTER' : ...
```

On entering Draw mode, the map center defaults to Indiranagar and the cluster immediately loads. The badge says "CLICK TO SET CENTER" even though the center is already set. It should say "CLICK OR DRAG TO MOVE CENTER".

---

### 14. "Open on Map" button in Lists only appears after expand + API load
**File:** `src/pages/Lists.jsx:112-114`

```jsx
{detail?.center_lat != null && openId === lst.id && (
  <button ...>◉ Map</button>
)}
```

The map button is inside the collapse-toggle header row, but it only renders after the user (a) expands the list AND (b) the detail API call has returned with geo data. The button appears mid-interaction, inside a clickable row, which is jarring. Consider showing it as a list-level action at all times when `lst.center_lat` is available (from the list index response).

---

### 15. Restored chat history loses store cards and maps
**File:** `src/components/ChatCore.jsx:66-75`

When reopening a saved conversation from history, all messages are restored with `stores: []`, `suggestions: []` hardcoded. Any store cards, MiniMaps, or action buttons from the original session are gone. The user sees only text bubbles.

---

### 16. `<a>` tag used as a toggle button without `href` (Auth page)
**File:** `src/pages/Auth.jsx:120-123`

```jsx
<a style={{ cursor: 'pointer', fontWeight: 700 }}
   onClick={() => { setError(''); setMode(...) }}>
  {mode === 'login' ? 'Register' : 'Log in'}
</a>
```

This is an `<a>` element with no `href`. It is not focusable by keyboard by default, has no semantic role, and triggers an accessibility violation. Should be a `<button>`.

---

### 17. `mapRef.invalidateSize` is exposed but never called
**File:** `src/components/ZonesMap.jsx:32-35`  
**File:** `src/pages/Zones.jsx:34`

`ZonesMap` uses `forwardRef` and exposes an `invalidateSize()` handle. Zones.jsx holds the ref (`const mapRef = useRef(null)`) but never calls `mapRef.current.invalidateSize()`. If the sidebar changes width (e.g., a future resize feature), the Leaflet map will render incorrectly until the window is resized. Either remove the `forwardRef` pattern or wire it up.

---

### 18. Score display is inconsistent: "—" in UI, "?" in map markers
**File:** `src/lib/map/leaflet.js:15`  
**File:** `src/components/ScoreRing.jsx:19`

When `score` is null, the `ScoreRing`, `ScorePill`, and most UI elements show `—`. But the Leaflet map marker shows `?` for the same null score. Small but noticeable inconsistency if a user notices a `?` marker and then sees `—` in the sidebar.

---

## Accessibility Issues

### 19. Icon buttons have no accessible labels
**File:** `src/components/Navbar.jsx:38-40`  
**File:** `src/pages/Landing.jsx:68`

The dark-mode toggle button has a `title` attribute but no `aria-label`. The floating chat FAB has a `title` but no `aria-label`. Screen readers and keyboard navigators get no meaningful label for these controls.

---

### 20. Star rating buttons in StoreDetail have no screen-reader text
**File:** `src/pages/StoreDetail.jsx:164-168`

```jsx
{[1,2,3,4,5].map(n => (
  <button key={n} className="star-btn" ...>{n <= rating ? '★' : '☆'}</button>
))}
```

The star buttons expose only a unicode character to screen readers. There is no `aria-label="N stars"` or `<span className="sr-only">` equivalent.

---

## Mobile / Responsive

### 21. No responsive layout — all pages are desktop-only
**Files:** `src/pages/Explore.jsx:39`, `src/pages/Zones.jsx:170`, `src/styles.css`

Explore uses a fixed `332px` sidebar + map column. Zones uses `360px` sidebar + map. The Chat page is capped at `720px`. There are no media queries in `styles.css` for mobile breakpoints. On viewports under ~700px, the two-column layouts break and sidebar content overflows or gets cut off.

---

## Code Quality / Edge Cases

### 22. `useEffect` in StoreDetail registers `postReview` without it being in deps
**File:** `src/pages/StoreDetail.jsx:47`

```js
useEffect(() => registerActionHandler('post_review', postReview), [id])
```

`postReview` is an `async function` defined in the component body (recreated each render). The effect only re-registers when `id` changes, so if any of `postReview`'s dependencies changed without `id` changing, a stale handler is registered. In practice this is benign here, but it's an easy mistake to introduce regressions with.

---

### 23. Chat session ID not reset on logout
**File:** `src/api.js:19-26`

The `tf_chat_session` key in `sessionStorage` is set once and never cleared. If a user logs out and a different user logs in on the same tab (same session), the second user's chat messages are sent with the first user's session ID, potentially mixing conversation history on the backend.

---

### 24. `auth/pendingAction.js` import path differs between component and page
**File:** `src/pages/StoreDetail.jsx:7`  
**File:** `src/pages/Zones.jsx:6`

Both pages import from `'../auth/pendingAction'`, which resolves correctly to `src/auth/pendingAction.js`. No breakage today — but when the auth directory was previously listed as `src/components/auth/`, this would have been a broken import. Worth double-checking the actual path resolves in the build.

---

## Summary Table

| # | Severity | Area | Description |
|---|----------|------|-------------|
| 1 | Critical | Zones / Lists | "Open on Map" deep-link URL params ignored |
| 2 | Critical | StoreDetail | Instagram `href="#"` — broken link |
| 3 | Critical | Zones / DrawControls | No fallback `<option>` for GPS location |
| 4 | Significant | Explore | `window.location.href` causes full page reload |
| 5 | Significant | StoreDetail | setTimeout review reload leaks on unmount |
| 6 | Significant | ChatCore | Stale `messages` closure in guest transcript claim |
| 7 | Significant | useDrawCluster | AbortController signal never passed to fetch |
| 8 | Significant | App | No 404 catch-all route |
| 9 | Significant | Navbar / Landing | SAVED chip links to `/explore` not `/lists` |
| 10 | Significant | ChatWidget / Chat | Widget and page have separate isolated message state |
| 11 | Minor | Landing | Hardcoded "4.8 / 360 reviews" presented as live data |
| 12 | Minor | Landing | Hardcoded fallback stats shown as accurate numbers |
| 13 | Minor | Zones | Badge says "CLICK TO SET CENTER" when center is set |
| 14 | Minor | Lists | "Open on Map" button appears late / inside collapse row |
| 15 | Minor | ChatCore | Restored history loses store cards and maps |
| 16 | Minor | Auth | `<a>` used as button without `href` |
| 17 | Minor | ZonesMap | `invalidateSize` exposed via ref but never called |
| 18 | Minor | Markers | Score null shown as "—" in UI but "?" in map markers |
| 19 | Minor | Navbar | Icon buttons missing `aria-label` |
| 20 | Minor | StoreDetail | Star buttons have no screen-reader label |
| 21 | Minor | All Pages | No responsive / mobile layout |
| 22 | Minor | StoreDetail | `postReview` not in `useEffect` deps |
| 23 | Minor | api.js | Chat session ID not cleared on logout |
| 24 | Minor | Auth imports | `pendingAction` import path assumption |
