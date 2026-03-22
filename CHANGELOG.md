# Changelog

## [0.1.0] - 2026-03-22

### Added
- Initial extraction from NeverMissAFiling monorepo
- Core engine: BrowserEngine, BaseStateFiler, FilingStateMachine, StandaloneOrchestrator
- Intelligence layer: OpenKlerk service with multi-backend support (Google Vertex AI, Anthropic stub, OpenAI stub, Ollama stub)
- Filers: California SOI, Delaware Franchise Tax, San Francisco ABR
- CLI: `openclerc run`, `openclerc new-filer`, `openclerc check`, `openclerc analyze`, `openclerc post`
- Contributor tools: scaffold generator, screenshot analyzer, quality gate, leaderboard
- Demo tools: recorder, overlay, viral post generator
- Documentation: quickstart, architecture, contributing guide, filer reference
- GitHub CI/CD: test workflow, quality gate workflow, PR/issue templates
