# Vero.ai — V1 Scope

**Status:** Target scope for V1 launch (Phase 20). Almost none of this is implemented today — see [ROADMAP.md](ROADMAP.md) for current status.

## V1 AI features

1. Person detection
2. Person tracking
3. People counting
4. Entry/exit counting
5. Customer-defined entry/exit lines
6. Heatmaps
7. Vehicle detection
8. Vehicle counting
9. Custom zones
10. OCR
11. QR code scanning
12. Barcode scanning
13. Per-camera AI module selection
14. Events
15. Historical analytics

The architecture must allow future AI modules to be added without rewriting the system.

## V1 platform features

- Windows desktop application (Tauri v2 + React + TypeScript)
- Python AI engine
- FastAPI backend
- PostgreSQL
- User accounts, organizations, locations
- Camera management, multiple cameras, RTSP support, live camera status
- Local AI processing
- Cloud synchronization of structured events/analytics (not raw video)
- 3-day free trial (enforced server-side)
- Subscription system
- Licensing system
- Own Hardware plan
- Vero Cloud plan
- PayPal subscriptions
- Automatic license/entitlement updates
- Windows installer that fully self-installs (no manual Python/Uvicorn steps)
- Automatic local service management
- Logging, error handling
- Update-ready architecture

## Explicitly out of V1 scope (V2 candidates)

Not part of the current implementation unless explicitly moved into the roadmap later:

- Dwell time
- Queue detection
- Occupancy intelligence
- Staff vs. customer differentiation
- PPE detection
- Fire/smoke detection
- Restricted-area alerts
- License plate recognition
- Parking analytics
- Warehouse intelligence
- Retail intelligence
- AI-generated insights / reports
- Multi-location advanced analytics
- Mobile application
- Third-party API integrations
- POS integrations
- AI video search
