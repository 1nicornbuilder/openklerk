# OpenKlerk Configuration

## Backends

### Google Vertex AI (Default, Implemented)
```bash
export GCP_PROJECT_ID=your-project-id
export GCP_LOCATION=us-central1
```

### Anthropic, OpenAI, Ollama
Stubs -- contributions welcome. See `openklerk/intelligence/backends/`.

### Mock (Testing)
```bash
openklerk run --config entity.json --filer ca_soi --mock-llm
```

## Implementing a New Backend

```python
from openklerk.intelligence.backends.base import LLMBackend

class MyBackend(LLMBackend):
    async def call(self, system_prompt, user_prompt, screenshot=None) -> str:
        ...
    @property
    def name(self) -> str:
        return "my_backend"
```

Register in `openklerk/intelligence/backends/__init__.py`.
