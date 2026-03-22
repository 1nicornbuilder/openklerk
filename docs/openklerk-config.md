# OpenKlerk Configuration

## Backends

### Google Vertex AI (Default, Implemented)
```bash
export GCP_PROJECT_ID=your-project-id
export GCP_LOCATION=us-central1
```

### Anthropic, OpenAI, Ollama
Stubs -- contributions welcome. See `openclerc/intelligence/backends/`.

### Mock (Testing)
```bash
openclerc run --config entity.json --filer ca_soi --mock-llm
```

## Implementing a New Backend

```python
from openclerc.intelligence.backends.base import LLMBackend

class MyBackend(LLMBackend):
    async def call(self, system_prompt, user_prompt, screenshot=None) -> str:
        ...
    @property
    def name(self) -> str:
        return "my_backend"
```

Register in `openclerc/intelligence/backends/__init__.py`.
