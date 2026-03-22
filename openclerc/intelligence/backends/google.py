"""Google Vertex AI (Gemini) backend for OpenKlerk."""
import asyncio
import logging
from typing import Optional

from openclerc.intelligence.backends.base import LLMBackend

logger = logging.getLogger("openclerc")


class GoogleVertexBackend(LLMBackend):
    """Google Vertex AI backend using Gemini models."""

    def __init__(
        self,
        project_id: str = "",
        location: str = "us-central1",
        model_name: str = "gemini-2.5-flash-preview-05-20",
        **kwargs,
    ):
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        """Lazy-initialize the Vertex AI model client."""
        if self._model is not None:
            return self._model
        try:
            from google.cloud import aiplatform
            from vertexai.generative_models import GenerativeModel

            aiplatform.init(project=self.project_id, location=self.location)
            self._model = GenerativeModel(self.model_name)
            return self._model
        except Exception as e:
            logger.error(f"GoogleVertexBackend: Failed to initialize: {e}")
            return None

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot: Optional[bytes] = None,
    ) -> str:
        model = self._get_model()
        if model is None:
            return ""

        try:
            from vertexai.generative_models import Part, Image

            parts = [user_prompt]
            if screenshot:
                parts.append(Part.from_image(Image.from_bytes(screenshot)))

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: model.generate_content(
                    parts,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 1024,
                    },
                ),
            )
            return response.text or ""
        except Exception as e:
            logger.error(f"GoogleVertexBackend: API call failed: {e}")
            return ""

    @property
    def name(self) -> str:
        return "google"
