Copyright (c) 2026 Namitaro. All rights reserved. No permission is granted to copy, distribute, or modify this software.

# Promin (Promin CRM)

A web application for the IT club of the Boiarka Professional College of NULES of Ukraine. It improves communication between teachers and students about events held inside the college:

- **teachers** publish posts about events and about scientific, sports, civic and creative activities;
- **students** find events and report that they took part;
- **teachers** confirm the students' participation.

The interface is meant to be simple and clear for every generation. The site is optimised for phones first, with good desktop support. Gamification (rating, leaderboard) and an events calendar are planned.

> **This is an internal college system.** The project is not intended to be run or deployed by third parties. A single instance runs, managed by the author. Accounts are created by an administrator; there is no public sign-up.

## Features

### Public part
- Home page and "About" page.
- Log in, log out and password change (standard Django authentication).

### User dashboard (`/dashboard/`)
- Dashboard home: greeting, rating, role and status.
- User profiles.
- **Post feed.** Users in the **Editor** group create and edit posts. Only the author of a post can edit it.

### Event participation requests
- **Submitting a request.**
  - Any user except the post's author can submit one request under a post: a description of their role (e.g. "first place, team captain") and, optionally, a certificate.
  - While the request is pending, it can be edited or withdrawn.
  - A rejected request can be corrected and resubmitted.
- **Review.**
  - The post's author sees the requests on the post page and on a separate "Requests to confirm" page (Заявки на підтвердження). They can approve a request or reject it, optionally giving a reason.
  - The **Root Editor** role (a Django group) can review requests under any post.
  - Nobody can review their own request.
- **Certificates.** JPG, PNG and PDF. They are compressed **in the browser** to ≤ 100 KB, because Supabase storage is limited and the server on Vercel must not do heavy processing.
  - Images are downscaled and re-encoded to WebP, or to JPEG if the browser cannot encode WebP.
  - The first three pages of a PDF are stitched into a single image.
  - The server only performs cheap checks of the size and the real file type.
  - A file is removed from storage together with its request, or when it is replaced by a new one.
- **Admin.** Django admin shows requests together with their certificates. It has bulk "Approve" and "Reject" actions, and files uploaded through the admin go through the same validation as on the site.

## Stack

| Part | Technologies |
|---|---|
| Backend | Python 3.14, Django 6.0 |
| Database | PostgreSQL (Supabase) via `dj-database-url` and `psycopg` 3; SQLite locally when `DATABASE_URL` is not set |
| Files | Supabase Storage (S3-compatible) via `django-storages` and `boto3`; file links are temporary and signed |
| File processing | Pillow (server-side validation); in the browser, the Canvas API and [pdf.js](https://mozilla.github.io/pdf.js/) 4.10.38 (legacy build, Apache-2.0, vendored in `users/static/vendor/pdfjs/`) |
| Frontend | Django templates, CSS, plain JavaScript with no framework or build step |
| Hosting | Vercel |

## Structure

```
promin/      project settings, root URLs
frontpage/   public pages (home, "About")
users/       users, dashboard, posts, participation requests
  models.py        User, Post, PostAttendance, Attachment
  views.py         dashboard, posts, requests, review page
  forms.py         PostForm, AttendanceForm
  validators.py    server-side certificate validation
  signals.py       removal of files from storage
  static/js/certificate_compress.js   in-browser file compression
templates/   login and password change pages
```

## Administration

- Users are created by an administrator in the admin (`/admin/`).
- The **Editor** (publishing posts) and **Root Editor** (reviewing any request) roles are assigned in the user's "Groups" field. Both groups are created automatically by the migrations.

## Tests

For the developer:

```bash
python manage.py test users
```

The tests use a temporary database and in-memory storage, so nothing is uploaded to Supabase.

## Use of AI in development

The author wrote the base of the project by hand, without AI: the project structure, the public pages and their styles, authentication, the user and post models, creating and editing posts, and the Supabase and Vercel setup. In the git history, these are all commits up to and including `a29e0bf`.

**Developed with the help of AI:** everything that comes after commit `a29e0bf` in the git history (merged from the `feature/attendance-requests` branch):

- the participation request feature: statuses, resubmission, rejection reason, the Root Editor role, the "Requests to confirm" page, the admin;
- in-browser certificate compression, server-side file validation and removal of files from storage;
- the automated tests (`users/tests.py`);
- minimal dashboard styles (`users/static/css/dashboard.css`), temporary until the design is developed;
- small fixes: only the author can edit a post, handling of a deleted author, `ALLOWED_HOSTS` from an environment variable, removing compiled files from git;
- this README.

**How AI was used.** Tool: Claude Code (Anthropic Claude models), with a clear division of roles.

- **Claude Opus:**
  - analysed the project and the specification;
  - drew up a stage-by-stage plan and proposed solution options with arguments (for example, ways to compress files);
  - reviewed the code written by the other models and tested it in the browser;
  - prepared mock-ups of a possible dashboard design (not part of the code).
- **Claude Sonnet and Claude Haiku** wrote the code and ran the commands: Sonnet the more complex parts, Haiku the simpler edits, migrations and commits.
- **The author** set the requirements, answered architecture questions and approved every stage. Before each change, the AI explained what would change and why (in a before/after format). New parts were introduced only after approval.
- **Every change** is a separate git commit with an English message. Commits created by AI carry a `Co-Authored-By: Claude …` line.
