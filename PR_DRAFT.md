Title: dispatch: sqlite durable queue & improvements

Body:
Added a SQLite-backed durable queue integrated with the dispatch manager, jittered retry/backoff, and telemetry hooks. Also added OpenCV multi-scale matching with preprocessing and E2E tests for Windows (Notepad/Explorer). CI workflow updated with an e2e Windows job gated by RUN_E2E.

Files changed:
- backend/dispatch/sql_queue.py (new)
- backend/dispatch/manager.py (modified)
- backend/tests/test_dispatch_sqlite.py (new)
- backend/desktop_automation/utils.py (modified)
- backend/desktop_automation/core.py (modified)
- backend/connectors/chrome_devtools.py (modified)
- backend/tests/test_e2e_notepad.py (new)
- backend/tests/test_e2e_explorer.py (new)
- .github/workflows/dispatch-ci.yml (modified)
- backend/tests/E2E_README.md (new)

Why:
- Durable task queue for at-least-once execution.
- Improved reliability for image-based desktop automation across DPI settings.
- CI matrix for broader coverage and optional E2E on Windows.

Reviewers: @your-org/backend-team

Checklist:
- [ ] Run full test suite locally
- [ ] Push branch desktop/dispatch-improvements
- [ ] Create PR with this body
- [ ] Verify Windows E2E on self-hosted runner
- [ ] Add Redis/RabbitMQ adapter in follow-up

Local push commands (run from repo root):
1) git checkout -B desktop/dispatch-improvements
2) git add -A
3) git commit -m "dispatch: sqlite durable queue, SQL-integrated manager, CI, retry/backoff improvements\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
4) git push --set-upstream origin desktop/dispatch-improvements
5) gh pr create --title "dispatch: sqlite durable queue & improvements" --body "$(cat PR_DRAFT.md)" --head desktop/dispatch-improvements --base main
