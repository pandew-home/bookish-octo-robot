# Dual Auth Mode + Error Handling + Dark Theme

## Context

- Chatbot is hard-wired to Kion/STS/EKS in [`cluster_manager.py`](backend/cluster_manager.py), [`eks_auth.py`](backend/eks_auth.py)
- Need kubeconfig-based auth for local clusters (kind/k3s/minikube)
- Multiple error handling gaps identified during audit
- Current theme is default MUI light blue (#1976d2) — needs "Deep Space / Obsidian" dark theme with muted forest green accents

## Assumptions

- User may have both AWS credentials and local kubeconfig, wants to switch at runtime
- K8sGPT operator may or may not be deployed to any given cluster
- LLM provider may be intermittently unavailable or misconfigured
- Dark theme applies globally — no light/dark toggle needed

---

## Part 1: Dual Auth Mode (AWS + Kubeconfig)

### Frontend: Login with Auth Tabs

- Two-tab login form: "AWS (Kion)" and "Kubeconfig"
- AWS tab: existing credential fields (unchanged)
- Kubeconfig tab: path selector (default `~/.kube/config` or custom)

### Backend: Per-Session Auth Mode

- [`StoredCredentials`](backend/credential_store.py:14) gets `auth_mode` field
- `POST /api/credentials/kubeconfig` — new endpoint, validates kubeconfig
- `GET /api/clusters` + `POST /api/clusters/select` — delegate based on `creds.auth_mode`
- New module [`backend/local_k8s_auth.py`](backend/local_k8s_auth.py)

---

## Part 2: Error Handling Audit & Fixes

### 2a. Weather Widget — K8sGPT Absence

**Current** at [`api/weather.py:108-123`](backend/api/weather.py:108):
- `ApiException(404)` → returns `results=[]` → shows "☀️ Sunny" (misleading)

**Fix:** Add `k8sgpt_status` field:

| Scenario | `k8sgpt_status` | UI Behavior |
|----------|-----------------|-------------|
| Operator running, has results | `"available"` | Normal weather display |
| Operator running, 0 results | `"available"` | "☀️ Sunny" (correct) |
| CRD 404 (not installed) | `"not_installed"` | Info banner: "K8sGPT not installed" |
| RBAC 403 | `"unreachable"` | Warning with RBAC message |
| Connection/timeout | `"unreachable"` | Warning + retry |

### 2b. Chat Pipeline Errors

- Cluster unreachable → HTTP 503 + `error_code:"cluster_unreachable"`
- Auth expired → HTTP 401 + `error_code:"cluster_auth_failed"`
- LLM errors → response with `error_type` in metadata → amber Alert styling

### 2c. Enrichment Timeout

- Wrap `asyncio.gather()` in `asyncio.wait_for(timeout=self.timeout)` at [`enrichment_engine.py:140`](backend/enrichment_engine.py:140)

---

## Part 3: Dark Theme — "Deep Space / Obsidian"

### Color Palette

| Element | Hex | MUI Theme Role |
|---------|-----|---------------|
| Deep Background | `#0a1214` | `background.default` |
| Card / Surface | `#121d20` | `background.paper` |
| Primary Green | `#66a16e` | `primary.main` |
| Primary Light | `#88c490` | `primary.light` |
| Hover/Dark Green | `#4e8055` | `primary.dark` |
| Text Primary | `#ffffff` | `text.primary` |
| Text Secondary | `#a0b0b5` | `text.secondary` |
| Error | `#f44336` | `error.main` |
| Warning | `#ff9800` | `warning.main` |
| Info | `#4fc3f7` | `info.main` |
| Success | `#66bb6a` | `success.main` |
| Divider | `#1e2e32` | `divider` |

### Theme Implementation

Update [`App.tsx`](frontend/src/App.tsx:38) `createTheme()`:

```typescript
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#66a16e',
      light: '#88c490',
      dark: '#4e8055',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#4fc3f7',
    },
    background: {
      default: '#0a1214',
      paper: '#121d20',
    },
    text: {
      primary: '#ffffff',
      secondary: '#a0b0b5',
    },
    divider: '#1e2e32',
    error: { main: '#f44336' },
    warning: { main: '#ff9800' },
    info: { main: '#4fc3f7' },
    success: { main: '#66bb6a' },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid #1e2e32',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#0d1618',
          backgroundImage: 'none',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        containedPrimary: {
          '&:hover': { backgroundColor: '#4e8055' },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            '& fieldset': { borderColor: '#1e2e32' },
            '&:hover fieldset': { borderColor: '#66a16e' },
          },
        },
      },
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h4: { fontWeight: 600 },
    h6: { fontWeight: 500 },
  },
});
```

### Visual Elements Affected

| Component | Change |
|-----------|--------|
| AppBar | Dark `#0d1618` background, green text/logo |
| Login screen | Dark background, green "Login"/"Connect" buttons |
| Cards (Weather, Chat, Results) | `#121d20` with `#1e2e32` border |
| Chat messages (user) | Subtle `#1a2a2e` bubble |
| Chat messages (assistant) | `#121d20` bubble |
| Buttons | Green primary, ghost/outlined with green border |
| Text fields | Dark input, green focus ring |
| Alerts (error) | Red tinted dark card |
| Alerts (info) | Cyan tinted dark card |
| Chips (severity) | Muted colors on dark background |

---

## Tasks (ordered, atomic)

### Backend — Auth Provider (Tasks 1-5)

1. Update [`backend/credential_store.py`](backend/credential_store.py:14) — add `auth_mode`, `kubeconfig_path`, `kubeconfig_contexts` fields; make AWS fields optional
2. Create [`backend/local_k8s_auth.py`](backend/local_k8s_auth.py) — `discover_local_clusters()`, `get_local_k8s_clients()`, `validate_kubeconfig()`
3. Add `POST /api/credentials/kubeconfig` to [`backend/api/credentials.py`](backend/api/credentials.py); set `auth_mode="aws"` on existing endpoint
4. Update [`backend/api/clusters.py`](backend/api/clusters.py:49) — delegate based on `creds.auth_mode`
5. Update [`backend/api/chat.py`](backend/api/chat.py:132) — handle kubeconfig auth mode

### Backend — Error Handling (Tasks 6-10)

6. Update [`backend/api/weather.py`](backend/api/weather.py:29) — add `k8sgpt_status`/`k8sgpt_message` to response models; 404→`"not_installed"`, 403→`"unreachable"`
7. Update operator detection at [`api/weather.py:150-169`](backend/api/weather.py:150) — catch namespace-not-found
8. Update [`backend/api/chat.py`](backend/api/chat.py:259) — catch `ConnectionError`, `ApiException(401/403)` with distinct status codes + `error_code`
9. Update [`backend/rag_integration.py`](backend/rag_integration.py:325) — add `error_type` to metadata on LLM errors
10. Update [`backend/enrichment_engine.py`](backend/enrichment_engine.py:140) — wrap `asyncio.gather()` in `asyncio.wait_for(timeout=self.timeout)`

### Frontend — Dark Theme (Tasks 11-13)

11. Update [`frontend/src/App.tsx`](frontend/src/App.tsx:38) — replace `createTheme()` with Deep Space dark theme palette and component overrides
12. Update [`frontend/src/index.css`](frontend/src/index.css) — set `body` background to `#0a1214`, update font stack to include Inter
13. Review and adjust all components for dark theme contrast — [`LoginForm.tsx`](frontend/src/components/LoginForm.tsx), [`ChatInterface.tsx`](frontend/src/components/ChatInterface.tsx), [`WeatherWidget.tsx`](frontend/src/components/WeatherWidget.tsx), [`ResultsPanel.tsx`](frontend/src/components/ResultsPanel.tsx), [`ClusterSelector.tsx`](frontend/src/components/ClusterSelector.tsx), [`CredentialBadge.tsx`](frontend/src/components/CredentialBadge.tsx)

### Frontend — Login Tabs (Tasks 14-16)

14. Update [`frontend/src/types/credentials.ts`](frontend/src/types/credentials.ts) — add `KubeconfigCredentials`, `AuthMode` types
15. Update [`frontend/src/services/api.ts`](frontend/src/services/api.ts) — add `authApi.loginKubeconfig()` method
16. Update [`frontend/src/components/LoginForm.tsx`](frontend/src/components/LoginForm.tsx) — tabbed interface (AWS / Kubeconfig) with dark theme styling

### Frontend — Error UX (Tasks 17-20)

17. Update [`frontend/src/types/weather.ts`](frontend/src/types/weather.ts) — add `k8sgptStatus`, `k8sgptMessage` fields
18. Update [`frontend/src/components/WeatherWidget.tsx`](frontend/src/components/WeatherWidget.tsx:97) — info/warning banners for K8sGPT absence; update [`useWeather.ts`](frontend/src/hooks/useWeather.ts)
19. Update [`frontend/src/hooks/useChat.ts`](frontend/src/hooks/useChat.ts:86) — map 503→cluster unreachable, pass `metadata.error_type`
20. Update [`frontend/src/components/ChatInterface.tsx`](frontend/src/components/ChatInterface.tsx) — render LLM errors with amber Alert when `error_type` present

### Tests & Docs (Tasks 21-23)

21. Add [`backend/tests/test_local_k8s_auth.py`](backend/tests/test_local_k8s_auth.py) — kubeconfig parsing, cluster discovery, client creation
22. Update [`backend/tests/test_weather_api.py`](backend/tests/test_weather_api.py) — test `k8sgpt_status` scenarios
23. Update [`docs/development.md`](docs/development.md) — document dual auth, error handling, theme

---

## Acceptance Criteria

### Auth
- Login screen shows two tabs: "AWS (Kion)" and "Kubeconfig"
- AWS tab works as before
- Kubeconfig tab discovers contexts, creates session, populates cluster list
- Chat pipeline works identically regardless of auth mode

### Weather / K8sGPT
- K8sGPT not installed → info banner (not fake "Sunny")
- K8sGPT RBAC denied → warning with message
- K8sGPT unavailable → warning + retry
- K8sGPT present, 0 results → "☀️ Sunny" (correct)

### Chat Errors
- Cluster unreachable → actionable "Cluster not responding" message
- Auth expired → "Please re-authenticate" + login prompt
- LLM rate-limited → amber Alert
- LLM timeout → amber Alert
- LLM connection error → amber Alert

### Enrichment
- Timeout after 10s → partial data + error note

### Theme
- Dark background (`#0a1214`), dark cards (`#121d20`)
- Muted forest green buttons/accents (`#66a16e`)
- White primary text, muted secondary text (`#a0b0b5`)
- All components readable with proper contrast
- Consistent dark styling across login, cluster selector, chat, weather, results

---

Ready for review.
