# Vero.ai — Development Rules

These rules are mandatory for every phase of Vero.ai development.

## Process rules

1. Work strictly phase-by-phase.
2. Never jump ahead.
3. Do not implement features belonging to a future phase unless explicitly instructed.
4. Before coding a phase, inspect the existing implementation.
5. Do not assume a feature exists because an earlier conversation said it existed.
6. Do not claim a phase is complete based only on internal/self-run tests.
7. Report exactly what was changed.
8. Report every file created/modified.
9. Report commands used for testing.
10. Report test results honestly.
11. If something cannot be verified on the user's Windows machine, say so explicitly.
12. Do not silently change architecture.
13. If the architecture needs changing, explain why and wait for approval before proceeding.
14. Avoid unnecessary dependencies.
15. Keep modules maintainable.
16. Do not create fake/mock functionality and present it as production functionality.
17. Do not hard-code secrets.
18. Do not upload raw CCTV footage to the cloud unless explicitly required by a future feature.
19. Keep the system extensible for future AI modules.
20. Prioritize reliability over adding features quickly.

## Testing philosophy

No phase is considered complete simply because Claude Code says it works — the project owner manually tests important functionality. Every phase must include:

- Automated tests where appropriate
- Exact commands to run
- Expected results
- Manual verification steps
- Failure scenarios

Eventual full test coverage must include: backend, database, AI engine, RTSP, camera reconnect, multiple cameras, detection, tracking, counting, zones, heatmaps, OCR, QR, barcode, authentication, trial, licensing, PayPal sandbox, installer, clean Windows machine, long-running operation, resource usage, network failure.

## Security requirements

See [ARCHITECTURE.md](ARCHITECTURE.md#security-requirements-target).
