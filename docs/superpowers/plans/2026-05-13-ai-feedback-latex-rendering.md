# LaTeX в фидбеке ИИ + рендер MathJax — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Научить ИИ писать формулы LaTeX в `feedback` и отрисовывать их у ученика (MathJax) при динамическом показе результата проверки.

**Architecture:** Добавляем инструкции в prompt (views.py). В JS на странице решения добавляем `escapeHtml()` + `typesetMath(el)` и вызываем typeset после вставки текста (обычная проверка и compare). MathJax уже подключён, поэтому переиспользуем его.

**Tech Stack:** Django views/templates/tests, MathJax v3.

---

## Files (map)

**Modify**
- `/workspace/core/views.py` — prompt в `api_verify_with_ai`
- `/workspace/core/templates/core/student_solve_assignment.html` — экранирование + вызов MathJax.typesetPromise
- `/workspace/core/tests/test_submission_verify_openrouter.py` — тест на наличие LaTeX-инструкций в prompt

---

### Task 1: RED — тест: prompt содержит инструкцию про LaTeX ($...$, $$...$$)

**Files:**
- Modify: `/workspace/core/tests/test_submission_verify_openrouter.py`

- [ ] **Step 1: Add failing assertion**

В тесте `test_verify_uses_openrouter_when_configured` после получения `prompt_text` добавить:

```python
        self.assertIn("$...$", prompt_text)
        self.assertIn("$$...$$", prompt_text)
```

- [ ] **Step 2: Run to verify fails**

```bash
python manage.py test core.tests.test_submission_verify_openrouter -v 1
```

- [ ] **Step 3: Commit failing test**

```bash
git add core/tests/test_submission_verify_openrouter.py
git commit -m "test: require latex formatting instructions in AI feedback"
```

---

### Task 2: GREEN — добавить LaTeX-инструкции в prompt

**Files:**
- Modify: `/workspace/core/views.py`

- [ ] **Step 1: Update prompt text**
В `api_verify_with_ai` добавить в промпт фразу:
> “В поле feedback используй Markdown. Все формулы записывай в LaTeX: инлайн `$...$`, блочно `$$...$$`.”

- [ ] **Step 2: Run tests**

```bash
python manage.py test core.tests.test_submission_verify_openrouter -v 1
```

- [ ] **Step 3: Commit**

```bash
git add core/views.py
git commit -m "feat: request latex formulas in AI feedback"
```

---

### Task 3: GREEN — безопасный вывод feedback и typeset MathJax в UI (обычный и compare)

**Files:**
- Modify: `/workspace/core/templates/core/student_solve_assignment.html`

- [ ] **Step 1: Add escape + typeset helpers**
Добавить в JS:
```js
function escapeHtml(s) {
  return String(s || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function typesetMath(el) {
  if (window.MathJax && MathJax.typesetPromise) {
    try { MathJax.typesetClear && MathJax.typesetClear([el]); } catch(e) {}
    return MathJax.typesetPromise([el]);
  }
}
```

- [ ] **Step 2: Normal AI verify**
Заменить подстановку `${data.feedback}` на `${escapeHtml(data.feedback)}` и после обновления результата вызывать:
`typesetMath(resultDiv);`

- [ ] **Step 3: Compare render**
В `renderCompareResults()` использовать `escapeHtml(r.feedback)` и после заполнения контейнера:
`typesetMath(resultDiv);`

- [ ] **Step 4: Run relevant tests**

```bash
python manage.py test core.tests.test_student_solve_assignment_part2_photo core.tests.test_ai_verify_compare_mode -v 1
```

- [ ] **Step 5: Commit**

```bash
git add core/templates/core/student_solve_assignment.html
git commit -m "feat: render latex in AI feedback via MathJax"
```

---

### Task 4: Full regression + push

- [ ] **Step 1: Run full suite**

```bash
python manage.py test core.tests -v 1
```

- [ ] **Step 2: Push**

```bash
git push origin main
```

