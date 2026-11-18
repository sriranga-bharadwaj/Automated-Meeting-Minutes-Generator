# Frontend validation and sprint demos

Run commands from `frontend/`:

- `npm ci`
- `npm run coverage`: unit and component tests, HTML line/branch reports, LCOV and JSON summary in `docs/coverage/frontend/`.
- `Install Google Chrome and Microsoft Edge`
- `npx playwright test`: Chrome and Edge checks with report in `docs/browser-report/`.
- `npm run build`: TypeScript and production build.

## Test cases

| Area | Cases | Evidence |
| --- | --- | --- |
| UI | Required meeting fields, valid submission, trimmed attendees, add/remove attendees | `src/ui.test.tsx` |
| Usability | Invalid audio recovery, disabled submit/upload controls, microphone denial with alternative, processing completion | `src/ui.test.tsx` |
| Accessibility | Keyboard entry focus, accessible field names, axe scan of validation state | `e2e/ui.spec.ts` |
| Compatibility | Meeting creation, invalid audio handling and 375px layout in Chrome and Edge | `e2e/ui.spec.ts` |
| Boundaries | Supported formats, empty files, exact 25 MB boundary, confidence cutoff, API error messages | `src/utils.test.ts` |

Coverage includes React components and API code; gaps are visible rather than excluded. Automated accessibility checks do not replace screen-reader or manual usability review. Playwright engines do not certify every branded browser or operating system.

## Demo recordings

Recordings use the application's existing offline mock API and are labelled on screen. They demonstrate frontend behavior, not actual backend transcription. Sprint 1 demonstrates meeting creation, validation and audio selection; Sprint 2 adds simulated processing, minutes editing and Markdown export. These are current-code demonstrations grouped by sprint scope, not historical sprint builds.

To reproduce, start `VITE_USE_MOCK=true npm run dev -- --port 5181` (PowerShell: `$env:VITE_USE_MOCK='true'; npm run dev -- --port 5181`), then run `node scripts/record-demos.mjs` in a second terminal. Videos are written to `docs/demos/sprint-1.webm` and `sprint-2.webm`.

## Recorded results

- 18 unit/component tests passed.
- 4 browser tests passed (2 each in Google Chrome and Microsoft Edge).
- TypeScript check and production build passed.
- All-source coverage: 43.03% lines/statements, 69.23% branches, 39.68% functions.
- MeetingForm: 98.48% lines, 86.36% branches. MinutesEditor and App remain uncovered by component tests; browser tests exercise the create/upload flow. The mock demonstrations are separate from automated test evidence.
- axe reported no violations in the tested meeting form validation state. Screen-reader review, recording hardware, backend integration, Firefox and Safari remain outside this run.
