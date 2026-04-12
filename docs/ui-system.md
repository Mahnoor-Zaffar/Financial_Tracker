# FinTrack UI System

## 1. Visual System

- Visual tone: editorial, restrained, calm.
- Theme strategy: light-first palette with full dark token set (`data-theme="dark"`).
- Typography:
  - Display/headings: `Literata` (high-contrast serif for hierarchy)
  - UI/body: `Manrope` (compact, highly legible controls/tables)
- Rhythm:
  - 8-step spacing scale from `0.35rem` to `3.2rem`.
  - Repeated panel/grid cadence to keep dashboard pages scannable.
- Surface model:
  - Canvas (`--bg`) with subtle radial atmosphere.
  - Content on bordered, low-shadow surfaces (`--surface`, `--surface-soft`).
  - Accent (`--brand`) reserved for primary actions and selected states only.
- State colors:
  - Positive = green (`--positive`)
  - Warning = amber (`--warning`)
  - Danger = rust (`--danger`)
  - Each has soft background companion for alerts/badges.

## 2. Component Inventory

- Layout primitives:
  - `app-shell`, `app-sidebar`, `app-topbar`, `app-content`, `public-shell`
  - `grid two`, `grid four`, `stack`, `transactions-layout`
- Navigation:
  - brand lockup (`brand`, `brand-mark`, `brand-copy`)
  - contextual sidebar links (`sidebar-link.active`)
  - mobile sidebar backdrop and toggle
- Content containers:
  - `panel`, `panel-soft`, `chart-panel`, `page-header`, `panel-head`
- Data display:
  - `stat-card`, `badge`, `table`, `tag-chip`, `list-row`, `budget-row`, `progress-track`
- Feedback:
  - `flash` stack with dismiss and auto-hide
  - `notice` (warning), `empty-state`, error-state blocks (`403/404/500`)
  - modal confirmation for destructive actions
- Forms:
  - `field-group` + accessible labels/helpers/errors
  - keyboard-visible focus ring tokens
  - submit loading states (`form-auto-loading`)
- Actions:
  - Button variants: `btn-primary`, `btn-ghost`, `btn-muted`, `btn-danger`
  - consistent size, focus, and loading behavior
- Charts:
  - Chart.js wrappers with CSS-token-driven colors
  - in-canvas empty-state fallback text

## 3. Page-by-Page UX Goals

- Landing:
  - communicate value fast, with clear typography and concise proof points.
- Login/Register:
  - low-friction auth flow with strong focus order and clean validation.
- Dashboard:
  - immediate monthly signal: KPI cards, budgets, account balances, recent ledger.
- Transactions:
  - filter-first workspace with sticky controls and dense-but-readable table.
- Add/Edit Transaction:
  - single-focus form; transfer type progressively reveals destination account field.
- Accounts/Categories/Tags:
  - setup pages that mix create + registry actions in one glanceable layout.
- Budgets:
  - month picker + progress bars with over-limit emphasis and edit/delete controls.
- Analytics:
  - visually integrated trend and category charts with no-data handling.
- Profile/Settings:
  - simple profile defaults and concise security notes without clutter.

## 4. Macro Contracts

- `templates/components/ui.html`
  - `flash_block()`
  - `page_header(title, subtitle, actions='')`
  - `stat_card(label, value, hint='', tone='neutral')`
  - `badge(text, tone='neutral')`
  - `empty_state(title, body, action_href=None, action_label=None)`
  - `budget_progress(name, spent, limit, ratio, overspent=False)`
  - `pagination_nav(pagination, endpoint, query_args=None)`
- `templates/components/forms.html`
  - `field(field, placeholder='', helper='', input_class='')`
