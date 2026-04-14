---
paths:
  - services/frontend/**
---
# Frontend — Path Rules

## Stack (locked)
- React 18 + TypeScript strict (`"strict": true` in tsconfig)
- Vite build tool; env var `VITE_API_URL` for API base URL
- TailwindCSS for all styling — no inline `style={}`, no CSS modules
- Recharts for all charts (LineChart, BarChart, etc.)

## API integration
```typescript
const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const authHdr = () => ({ Authorization: `Bearer ${localStorage.getItem("access_token") ?? ""}` });
// Parallel fetches:
const [infoR, driftR] = await Promise.all([
  fetch(`${API}/ml/model/info`, { headers: authHdr() }),
  fetch(`${API}/ml/drift`,      { headers: authHdr() }),
]);
```
- Poll interval: 15 s for ML metrics; 10 s for training status
- Always check `r.ok` before parsing JSON
- Never expose tokens in console.log

## Component conventions
- One page per file in `src/pages/`; reusable atoms in `src/components/`
- Toast: fixed top-right, auto-dismiss 3.5 s, separate ok/err variants
- Confirmation modal before any destructive action (rollback, delete)
- Animated `animate-pulse` badge for active background tasks

## Active learning UI
- 5 label colors: confirmed=green, corrected=yellow, new_profile=blue, intruder=red, rejected=gray
- Top-k candidate panel: clickable rows pre-fill `correctedId`
- Progress bar: `labeled % threshold` toward next fine-tuning trigger
- Training status polls `/review/training/status` every 10 s
- Frame supports zoom-to-fullscreen modal

## MonitoringML page
- 6 metric cards: FAR (red), FRR (orange), EER (purple), TAR (green), Drift (yellow), Queue AL (blue)
- Collapsible config panel (admin only) via `PUT /review/training/config`
- Rollback button only for runs where `outcome === "deployed"`
- Chart: FAR + EER evolution over runs (Recharts LineChart, chronological)

## TypeScript rules
- `null` for missing API values; `interface` for API response shapes
- Helper `pct(v: number | null): string` formats to `X.XXX%` or `—`
- No `any` except for `import.meta.env` access pattern

## Accessibility
- Keyboard-navigable (Tab + Enter/Space)
- Never rely on color alone — add text label or icon
- ARIA labels on icon-only buttons
