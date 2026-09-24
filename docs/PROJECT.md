# Vero.ai — Project Definition

**Status:** Authoritative specification, recorded at Phase 0 (documentation only — no implementation yet).
**Supersedes:** Any prior roadmap drafts, phase-completion claims, or the former product name "AI Vision".

## What Vero.ai is

Vero.ai is a Windows desktop computer vision SaaS product, by AI Dev Guy, that turns existing CCTV cameras into AI-driven analytics — without requiring the business to build their own computer vision system.

## Target customers (initial)

- Retail stores
- Warehouses
- Parking businesses
- Offices
- Construction / security environments
- Other SMEs with existing CCTV

## Business model — two infrastructure plans

### A. Vero Own Hardware

The customer already owns suitable hardware (PC, GPU workstation, AI box, local server). AI/video processing runs on the customer's hardware; the cloud side only handles accounts, licensing, and structured events/analytics sync. Raw CCTV video stays local whenever possible.

Because Vero.ai is not paying for the customer's compute, this plan carries a significantly lower monthly price, with limits such as camera count, enabled AI modules, and possibly device entitlement.

### B. Vero Cloud

The customer lacks suitable hardware. Vero.ai supplies the cloud AI infrastructure end-to-end.

This plan is priced from real infrastructure economics — GPU/CPU compute, camera count/resolution/FPS, bandwidth, database, storage, monitoring, payment fees, operating overhead, and profit margin — calculated in a dedicated phase (**Phase 14**) once the cloud architecture is defined. **Phase 14 calculated a cost-derived price of approximately $150–155/camera/month** (CPU-only compute matching the actual built architecture, 70% gross margin, 24/7 tracking — see [PRICING-MODEL.md](PRICING-MODEL.md) for the full breakdown). This is not yet a locked, marketing-ready price, is not wired into the app, and does not cover the Own Hardware plan (a separate, market-positioning decision).

## Core product principles

Vero.ai should be: easy to install, easy to configure, camera-agnostic where practical, compatible with existing CCTV systems, local-first where the customer owns hardware, efficient with compute, secure, scalable, modular, suitable for multiple cameras and multiple locations, and commercially maintainable.

Raw CCTV video is **not** uploaded or continuously stored in the cloud by default. Cloud storage holds structured data only: accounts, organizations, locations, cameras, events, analytics, configuration, subscription information, and licensing information.

## Naming

- Current/final product name: **Vero.ai**
- Former/obsolete name: "AI Vision" — any remaining references in existing files (e.g. `README.md` setup paths) are stale documentation, not a naming decision. See "Conflicts / stale artifacts" in [ROADMAP.md](ROADMAP.md).
