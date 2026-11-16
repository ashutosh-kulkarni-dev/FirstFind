# FirstFind frontend

React 18 + Vite + Leaflet.

## Layout

| Folder | What lives there |
|---|---|
| `src/pages/` | One file per screen. A page owns its state and data loading. |
| `src/pages/explore/` | The pieces of the Explore sidebar (filters, cluster, selected store, lists, save dialog). |
| `src/components/` | Pieces used by more than one page (map, store card, score pill, chat). |
| `src/api/` | Calls to the backend, one file per area. Import everything as `import { api } from '../api'`. |
| `src/auth/` | Login state and "log in to continue" helpers. |
| `src/lib/` | Plain functions with no React in them. |
| `src/styles.css` | All styling. |

Rules that keep it tidy:

- A new backend call goes in the matching `src/api/*.js` file, never a `fetch` in a component.
- Styling goes in `styles.css` as a class. Use an inline `style` only for a value computed at runtime (a colour from a score, a width from data).
- When a page passes ~300 lines, move what it draws into a folder next to it, as `pages/explore/` does.

## Commands (run from `app/frontend`)

```bash
npm run dev      # local dev server; /api is proxied to a backend on port 8000
npm run lint     # ESLint
npm run build    # production build
```
