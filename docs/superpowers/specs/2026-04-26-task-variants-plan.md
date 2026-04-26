# Implementation Plan: Task Variants & CSV Import

## Phase 1: Database Updates (Models & Migration)
1. **Add `preferred_theme` to User Model**:
   - Update `core/models.py`: `User` class gets a `preferred_theme` field (CharField, default='classic', choices=[('classic', 'Классика'), ('dota', 'Dota 2'), ('ussr', 'СССР'), ('cs2', 'CS2')]).
2. **Add `subtype_tag` to Task Model**:
   - Update `core/models.py`: `Task` class gets a `subtype_tag` field (CharField, max_length=100, null=True, blank=True).
3. **Create `TaskVariant` Model**:
   - Update `core/models.py`: `TaskVariant` class with `task` (ForeignKey), `theme` (CharField, default='classic'), `content` (TextField), `solution` (TextField, null=True, blank=True).
4. **Data Migration (Crucial Step)**:
   - Generate an empty migration.
   - Write a Python script inside the migration to iterate over all existing `Task` objects.
   - For each `Task`, create a `TaskVariant` with `theme='classic'` and `content=task.content`.
   - Also, `solution` can be set to null for now.
5. **Remove `content` from Task Model**:
   - Update `core/models.py`: Remove `content` field from `Task`.
   - Run `makemigrations` and `migrate`.

## Phase 2: CSV Import Logic (The Parser)
1. **Create Image Downloader Utility**:
   - Create `core/utils.py` (or similar).
   - Function `download_and_replace_images(html_content, task_fipi_id, theme)`:
     - Parses HTML using BeautifulSoup.
     - Finds all `<img>` tags.
     - Downloads the `src` URL using `requests`.
     - Saves the file to `media/tasks/` using a unique filename (e.g., `{fipi_id}_{theme}_img1.jpg`).
     - Updates the `src` attribute to the new local path (`/media/tasks/...`).
     - Returns the modified HTML string.
2. **Create CSV Import Service**:
   - Function `import_tasks_from_csv(file_obj)`:
     - Reads the CSV file using Python's `csv` module.
     - Iterates row by row.
     - Maps `type_number` to an existing `TaskType` (using the `ExamFormat` from the previous step).
     - Updates/creates `Task` (`fipi_id`, `task_type`, `subtype_tag`, `correct_answer`, `difficulty`, `exam_points`).
     - Passes `content` and `solution` through `download_and_replace_images`.
     - Updates/creates `TaskVariant` for the specified `theme`.

## Phase 3: UI Integration (Upload & Display)
1. **Upload Form (Tutor Dashboard)**:
   - Create a view `import_tasks_view` handling file uploads (POST request with `enctype="multipart/form-data"`).
   - Add a button "Загрузить задания (CSV)" in `tutor_task_bank.html`.
   - Render the upload form in a modal or a separate page (`core/templates/core/import_tasks.html`).
2. **Theme Selection (Student Dashboard)**:
   - Add a dropdown menu in `student_dashboard.html` (header or settings area) to select `preferred_theme`.
   - Create a view to update the user's `preferred_theme` via AJAX or a simple POST request.
3. **Task Rendering Logic**:
   - Update `student_practice.html`, `tutor_task_bank.html`, and `student_practice_result.html`.
   - Since `task.content` no longer exists, we must fetch the correct variant.
   - Add a helper property/method to `Task` model: `get_content_for_theme(theme)` and `get_solution_for_theme(theme)`.
   - In templates, use `task.get_content_for_theme(user.preferred_theme)` instead of `task.content`.

## Phase 4: Testing & Deployment
1. Generate a dummy CSV file with remote images to test the import functionality.
2. Run the server locally, upload the CSV, verify database records and downloaded images in `media/tasks/`.
3. Verify that changing the user's theme correctly updates the task text in the student dashboard.
4. Commit changes and deploy to VPS.