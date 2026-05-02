# Tex Scale Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить на странице «Банк заданий» слайдер для подбора масштаба формул (MathJax и inline-изображений формул), с сохранением значения в браузере.

**Architecture:** Страница выставляет CSS-переменную `--tex-scale` на корневом элементе. CSS применяет масштаб к `mjx-container` и `.prose img.tex`. JS синхронизирует слайдер, значение и `localStorage`.

**Tech Stack:** Django templates, inline JS/CSS, MathJax v3 (tex-mml-chtml), Tailwind CDN.

---

## File Structure

- Modify: `core/templates/core/tutor_task_bank.html`
  - Добавить UI слайдера над списком карточек задач
  - Добавить CSS для масштабирования MathJax контейнеров
  - Добавить JS для управления `--tex-scale` и сохранения значения
- Modify: `core/templates/core/image_modal.html`
  - Перевести стиль `.prose img.tex` на использование `--tex-scale` (чтобы слайдер влиял и на формулы-изображения)

---

### Task 1: Add Slider UI Above Task List

**Files:**
- Modify: `core/templates/core/tutor_task_bank.html`

- [ ] **Step 1: Добавить блок управления масштабом в разметку**

Вставить блок после формы фильтров (в верхней части страницы) и перед выводом задач:

```html
<div class="mt-4 mb-6 bg-white border border-gray-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
    <div class="font-bold text-gray-800">Масштаб формул</div>
    <div class="flex items-center gap-3">
        <input id="tex-scale-range" type="range" min="90" max="180" step="5" value="100" class="w-56">
        <span id="tex-scale-value" class="font-mono font-bold text-indigo-700 w-14 text-right">100%</span>
    </div>
</div>
```

- [ ] **Step 2: Проверить, что блок отображается на странице без ошибок шаблона**

Run:

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

---

### Task 2: Apply Scale via CSS Variable (MathJax)

**Files:**
- Modify: `core/templates/core/tutor_task_bank.html`

- [ ] **Step 1: Добавить CSS для `--tex-scale` и применения к MathJax**

Добавить в `<head>` (после подключения MathJax или рядом с конфигурацией) стиль:

```html
<style>
    :root { --tex-scale: 1; }
    mjx-container { font-size: calc(var(--tex-scale, 1) * 1em); }
</style>
```

- [ ] **Step 2: Проверить, что CSS не ломает страницу**

Run:

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

---

### Task 3: Apply Scale to Inline TeX Images (`img.tex`)

**Files:**
- Modify: `core/templates/core/image_modal.html`

- [ ] **Step 1: Обновить `.prose img.tex` на использование `--tex-scale`**

Заменить текущее правило на:

```html
<style>
    .prose img.tex {
        display: inline-block;
        margin: 0;
        vertical-align: middle;
        height: calc(var(--tex-scale, 1) * 1.584em);
        max-height: none;
        width: auto;
    }
</style>
```

- [ ] **Step 2: Быстрая проверка синтаксиса**

Run:

```bash
python -m compileall -q .
```

Expected: no output, exit code 0.

---

### Task 4: Add JS Controller + Persistence

**Files:**
- Modify: `core/templates/core/tutor_task_bank.html`

- [ ] **Step 1: Добавить JS, который инициализирует значение из localStorage и ставит `--tex-scale`**

Добавить в конец `tutor_task_bank.html` (перед `</body>`) скрипт:

```html
<script>
    (function () {
        const RANGE_ID = "tex-scale-range";
        const VALUE_ID = "tex-scale-value";
        const STORAGE_KEY = "texScalePercent";

        function clamp(n, min, max) { return Math.min(max, Math.max(min, n)); }

        function applyPercent(pct) {
            const scale = pct / 100;
            document.documentElement.style.setProperty("--tex-scale", String(scale));
        }

        function setValueText(el, pct) {
            el.textContent = `${pct}%`;
        }

        document.addEventListener("DOMContentLoaded", () => {
            const range = document.getElementById(RANGE_ID);
            const value = document.getElementById(VALUE_ID);
            if (!range || !value) return;

            const saved = parseInt(localStorage.getItem(STORAGE_KEY) || "100", 10);
            const pct = clamp(Number.isFinite(saved) ? saved : 100, 90, 180);

            range.value = String(pct);
            setValueText(value, pct);
            applyPercent(pct);

            range.addEventListener("input", () => {
                const next = clamp(parseInt(range.value, 10), 90, 180);
                setValueText(value, next);
                applyPercent(next);
                localStorage.setItem(STORAGE_KEY, String(next));
            });
        });
    })();
</script>
```

- [ ] **Step 2: Проверить, что скрипт не вызывает ошибок при отсутствии элементов**

Run:

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

---

### Task 5: Manual Verification + Commit

**Files:**
- Modify: `core/templates/core/tutor_task_bank.html`
- Modify: `core/templates/core/image_modal.html`

- [ ] **Step 1: Локальная ручная проверка**
  - Открыть страницу `/tutor/tasks/` (Банк заданий)
  - Убедиться, что слайдер стоит над списком задач
  - Подвигать слайдер и убедиться, что:
    - MathJax формулы меняют размер
    - Inline формулы-изображения (`img.tex`) меняют размер
  - Перезагрузить страницу и убедиться, что значение сохранилось

- [ ] **Step 2: Commit**

```bash
git add core/templates/core/tutor_task_bank.html core/templates/core/image_modal.html
git commit -m "feat: add tex scale slider on task bank"
git push origin main
```

