# ReshuEGE Retry Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist import errors for ReshuEGE массового импорта and allow re-importing only failed IDs via a “Повторить ошибки” button.

**Architecture:** Frontend (admin import page) tracks failed IDs (status=error) and stores them in browser `localStorage` under a deterministic key; the same step endpoint is reused to retry those IDs later.

**Tech Stack:** Django templates + vanilla JS; existing `admin_reshuege_import_start/step` endpoints.

---

## Files & Responsibilities

- Modify: [admin_reshuege_import.html](file:///workspace/core/templates/core/admin_reshuege_import.html) — add error persistence, retry UI, and “clear errors”.
- No backend changes required for MVP (reuses existing `/platform-admin/reshuege-import/step/`).
- Create: `docs/superpowers/specs/2026-05-08-reshuege-import-retry-errors-design.md` already exists (reference spec).

---

### Task 1: Add localStorage persistence helpers

**Files:**
- Modify: [admin_reshuege_import.html](file:///workspace/core/templates/core/admin_reshuege_import.html)

- [ ] **Step 1: Add helper functions (key + load/save)**

Add inside the existing `<script>` block (near other helpers like `setProgress`):

```js
function reshuegeErrorsKey(formData) {
  const exam = String(formData.get('exam_format') || '');
  const type = String(formData.get('type_number') || '');
  const theme = 'classic';
  const idsRaw = String(formData.get('task_ids') || '').trim();
  const source = idsRaw.slice(0, 2000);
  return `reshuege_import_errors:v1:${exam}:${type}:${theme}:${source}`;
}

function loadReshuegeErrors(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveReshuegeErrors(key, items) {
  try {
    localStorage.setItem(key, JSON.stringify(items || []));
  } catch {}
}
```

- [ ] **Step 2: Define error item shape**

Use a simple array of objects:

```js
// { taskId: "27238", detail: "Read timed out", ts: 1710000000000 }
```

- [ ] **Step 3: Manual check**

Open the import page, run a short import, open DevTools → Application → Local Storage and confirm the key appears when an error occurs.

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/admin_reshuege_import.html
git commit -m "feat: persist reshuege import errors in localStorage"
```

---

### Task 2: Track errors during import loop

**Files:**
- Modify: [admin_reshuege_import.html](file:///workspace/core/templates/core/admin_reshuege_import.html)

- [ ] **Step 1: Compute storage key at import start**

Inside submit handler after `const formData = new FormData(form);`:

```js
const errKey = reshuegeErrorsKey(formData);
```

- [ ] **Step 2: On each step response, record errors**

After `const status = step?.status || 'unknown';`:

```js
if (status === 'error') {
  const existing = loadReshuegeErrors(errKey);
  const next = existing.filter(x => x && x.taskId !== String(taskId));
  next.push({ taskId: String(taskId), detail, ts: Date.now() });
  saveReshuegeErrors(errKey, next);
}
```

- [ ] **Step 3: Optional: also record network/parse failures**

If `stepRes.ok` is false or JSON parsing fails, treat as error for this ID and store a synthetic detail like `http ${stepRes.status}`.

- [ ] **Step 4: Manual check**

Trigger a timeout (or temporarily set small timeout in backend), confirm error count grows in localStorage.

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/admin_reshuege_import.html
git commit -m "feat: record per-id reshuege import errors"
```

---

### Task 3: Add “Повторить ошибки” + “Очистить ошибки” UI

**Files:**
- Modify: [admin_reshuege_import.html](file:///workspace/core/templates/core/admin_reshuege_import.html)

- [ ] **Step 1: Add buttons to progress block**

In the existing progress controls block (near “Остановить”), add:

```html
<button id="reshuege-import-retry-errors" type="button" class="w-full sm:w-auto px-4 py-2 rounded-lg bg-white text-primary font-bold text-sm border border-primary hover:bg-indigo-50 transition hidden">
  Повторить ошибки
</button>
<button id="reshuege-import-clear-errors" type="button" class="w-full sm:w-auto px-4 py-2 rounded-lg bg-gray-100 text-gray-700 font-bold text-sm hover:bg-gray-200 transition hidden">
  Очистить ошибки
</button>
<div id="reshuege-errors-saved" class="text-xs text-gray-500"></div>
```

- [ ] **Step 2: Toggle visibility based on localStorage**

On DOMContentLoaded compute key from current form values and show buttons if errors exist:

```js
function refreshErrorUi(errKey) {
  const retryBtn = document.getElementById('reshuege-import-retry-errors');
  const clearBtn = document.getElementById('reshuege-import-clear-errors');
  const label = document.getElementById('reshuege-errors-saved');
  const items = loadReshuegeErrors(errKey);
  const n = items.length;
  if (label) label.textContent = n ? `Ошибок сохранено: ${n}` : '';
  if (retryBtn) retryBtn.classList.toggle('hidden', n === 0);
  if (clearBtn) clearBtn.classList.toggle('hidden', n === 0);
}
```

- [ ] **Step 3: Implement “Очистить ошибки”**

```js
clearBtn.onclick = () => {
  localStorage.removeItem(errKey);
  refreshErrorUi(errKey);
};
```

- [ ] **Step 4: Implement “Повторить ошибки”**

Behavior:
- disables main submit button while retry runs
- reuses existing `step` endpoint
- iterates over stored error IDs; on `ok` remove from stored list; on `error` update detail/ts

Pseudo-code:

```js
retryBtn.onclick = async () => {
  const items = loadReshuegeErrors(errKey);
  const ids = items.map(x => x.taskId);
  // loop same as import, but only ids
};
```

- [ ] **Step 5: Manual check**

1) Run import until you have a few ERR saved  
2) Reload page  
3) Click “Повторить ошибки”  
4) Confirm success removes items from localStorage and “Ошибок сохранено: N” decreases.

- [ ] **Step 6: Commit**

```bash
git add core/templates/core/admin_reshuege_import.html
git commit -m "feat: retry and clear reshuege import errors"
```

---

### Task 4: Harden UX around stopping + retries

**Files:**
- Modify: [admin_reshuege_import.html](file:///workspace/core/templates/core/admin_reshuege_import.html)

- [ ] **Step 1: Ensure “Остановить” aborts retry flow too**

Reuse the same abort controller for import and retry.

- [ ] **Step 2: Prevent concurrent runs**

Disable “Повторить ошибки” while main import is running, and vice versa.

- [ ] **Step 3: Manual check**

Click retry during active import → should be disabled and not start second loop.

- [ ] **Step 4: Commit**

```bash
git add core/templates/core/admin_reshuege_import.html
git commit -m "fix: prevent concurrent reshuege import loops"
```

---

## Verification

- Run: `python -m compileall -q /workspace/core` (syntax check)
- Manual: open `/platform-admin/reshuege-import/` and confirm:
  - ERRs are counted and persisted across reload
  - “Повторить ошибки” retries only failed IDs
  - “Очистить ошибки” removes saved errors

---

## Spec coverage self-check

- “Не терять список ошибок” → Task 1–2
- “Докачать ошибки” → Task 3–4
- “localStorage” → Task 1
