# Technical Design: Universal Auth, Invite Codes, and Admin Roles

## 1. Universal Registration Flow
- **Goal**: `/register/` should create a `User` with `role='unassigned'` instead of forcing `role='student'`.
- **Flow**: After successful email registration, redirect to `/select-role/`. The `CustomAccountAdapter` already handles this for social auth, so we just need to align standard auth with it.

## 2. Admin Account & CSV Import
- **Goal**: Only Admins can upload tasks to the global bank.
- **Action**: Create a superuser `admin` with password `123123` via management script.
- **UI Update**: Move the "Импорт CSV" button from `tutor_task_bank.html` to `admin_dashboard.html`. Update `import_tasks_view` to restrict access strictly to `role='admin'`.

## 3. Invite Codes (Tutor-Student Links)
- **Database Changes**:
  - Add `invite_code` (CharField, max_length=10, unique, null=True) to `User` model.
  - Create a new model `TutorStudentLink`:
    - `tutor` (ForeignKey to User)
    - `student` (ForeignKey to User)
    - `created_at` (DateTimeField)
- **Logic**:
  - When a user selects the "Tutor" role, generate a unique 6-character alphanumeric `invite_code`.
  - In `student_dashboard`, add a form: "Ввести код репетитора".
  - Submit form -> Find tutor by code -> Create `TutorStudentLink`.
- **UI Update**:
  - Tutor Dashboard: Display the invite code prominently.
  - Student Dashboard: Display a small form to enter the code, or show the connected tutor's name if already linked.

## 4. Tutor Trial Period
- **Database Changes**:
  - Add `role_assigned_at` (DateTimeField, null=True) to `User` model.
- **Logic**:
  - When role changes to 'tutor', set `role_assigned_at = now()`.
  - In `tutor_dashboard.html`, calculate days remaining: `7 - (now - role_assigned_at).days`.
  - Display a banner indicating the trial status.