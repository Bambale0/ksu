# Tanyapi parity roadmap

Implement product capability parity without copying the legacy monolithic structure.

## Order

1. #41 Trends catalog
2. #42 Image and prompt analysis
3. #43 Reference library and presets
4. #44 Batch generation
5. #45 Partner approval lifecycle
6. #46 Feed and profile parity polish
7. #47 Mini App product UX parity
8. #48 QA and release hardening
9. #49 Model and provider expansion
10. #50 Optional payment and channel expansion

#51 tracks the overall program.

## Delivery rules

- One epic per implementation branch and PR.
- Keep model validation, pricing and permissions server-side.
- Reuse the existing KSU domain services and provider abstractions.
- Include tests and documentation in every implementation PR.
- Keep CI green between phases.
- Phases 1-8 are core parity. Phases 9-10 are business-driven extensions.
