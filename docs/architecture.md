# Architecture

## Layers

- **Core** (`openklerk/core/`): BrowserEngine, BaseStateFiler, StateMachine, Orchestrator
- **Intelligence** (`openklerk/intelligence/`): OpenKlerk LLM service with pluggable backends
- **Filers** (`openklerk/filers/`): State-specific filing implementations
- **Contrib** (`openklerk/contrib/`): Scaffold generator, quality gate, screenshot analyzer

## Data Flow

1. CLI loads entity JSON into FilingContext
2. StandaloneOrchestrator gets the filer from the registry
3. BrowserEngine launches Playwright with stealth mode
4. Orchestrator calls filer.execute_step() for each step
5. OpenKlerk analyzes screenshots at page transitions
6. Results printed to stdout and optionally saved as JSON
