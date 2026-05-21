# Physics KIM Reference (FAB + Modal) — Design

## Goal

Add a floating “?” button that opens a Physics-only KIM reference inside a modal window for students during solving:
- assignment solving flow (`student_solve_assignment`)
- practice flow (`student_practice`)

The reference must be available at any moment while solving, without leaving the page.

## Non-Goals

- Not a full physics handbook.
- No formulas or explanations beyond the official “spravochnye dannye” used in KIM.
- No server-side editing UI for the reference.

## UX

### Entry

- A circular floating action button (FAB) at bottom-right, label “?”.
- FAB is visible only when reference is enabled by gating rules.

### Modal

- Opens on FAB click.
- Closes on:
  - overlay click
  - Escape key
  - explicit close button
- Modal content scrolls vertically; horizontal scrolling is allowed for tables on mobile.

### Tabs

Tabbed layout with fixed tabs:
- Константы
- Приставки
- Единицы
- Прочее

Only one tab panel visible at a time.

## Gating Rules (When to show)

Widget is shown only for Physics and only for ЕГЭ/ОГЭ.

### Assignment solve page

Primary source:
- `assignment.exam_format.subject.name` contains `физ` (case-insensitive)
- `assignment.exam_format.name` contains `егэ` or `огэ` (case-insensitive)

Fallback (if `assignment.exam_format` is absent or incomplete):
- infer subject from the first task in `tasks` (topic → subject)

### Practice page

Use currently selected subject/profile:
- identify active subject by `subject_id` / `active_subject_id`
- check that subject name contains `физ`
- exam format name contains `егэ` or `огэ`

## Which reference to show

- If exam format name contains `егэ` → `kind="ege"`
- If exam format name contains `огэ` → `kind="oge"`

Expose the following template context:
- `physics_kim_ref_enabled: bool`
- `physics_kim_ref_kind: "ege" | "oge" | ""`

## Templates and Includes

### New templates

- `core/templates/core/includes/_physics_kim_reference_widget.html`
  - contains FAB + modal markup + tabs + minimal inline JS
  - guards itself with `{% if physics_kim_ref_enabled %}`
  - includes correct content fragment depending on `physics_kim_ref_kind`
  - contains stable marker `id="physics-kim-fab"` for tests

- `core/templates/core/includes/_physics_kim_reference_content_ege.html`
- `core/templates/core/includes/_physics_kim_reference_content_oge.html`

Each content file contains 4 tab panels with `data-panel="constants|prefixes|units|other"`.

### Integrations

- `core/templates/core/student_solve_assignment.html`
  - include widget in the page body (near end of body), so overlay/modals work reliably.

- `core/templates/core/student_practice.html`
  - include widget in the page body (near end of body).

## Frontend Behavior (JS)

Vanilla JS (no external deps):
- openModal(): show overlay+modal, lock background scroll
- closeModal(): hide, restore scroll
- switchTab(tabKey): activate tab button state, show matching panel

Keyboard behavior:
- Escape closes
- focus stays usable (minimum: modal is focusable; no advanced focus trap requirement)

## Content Sourcing

Reference content is sourced from official KIM materials (demo variants / official PDFs) and transferred into HTML without additions.

If an official newer year appears, update the HTML fragments to match it.

## Testing

Create `core/tests/test_physics_kim_reference_widget.py`:
- Solve assignment page includes `id="physics-kim-fab"` for Physics ЕГЭ assignment.
- Solve assignment page does not include marker for non-Physics.
- Practice page includes marker for Physics ОГЭ profile/subject.

Tests validate gating + template wiring (not JS behavior).

## Rollout Safety

- The widget is purely additive and gated.
- No user secrets processed.
- No new DB migrations required.
