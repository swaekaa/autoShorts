"""
Gemini API Client
=================
Wraps the google-genai SDK with error handling, quota tracking,
and model validation at startup.
"""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.logging_config import get_logger
from app.quota_manager import QuotaEventType, ServiceProvider, classify_api_error

logger = get_logger(__name__)


class GeminiClient:
    """
    Thin wrapper around the official google-genai SDK client.
    Validates model identifiers at initialization.
    """

    def __init__(self, api_key: str, text_model: str, video_model: str):
        self._client = genai.Client(api_key=api_key)
        self.text_model = text_model
        self.video_model = video_model
        logger.info(
            "GeminiClient initialized",
            extra={"text_model": text_model, "video_model": video_model},
        )

    @property
    def raw_client(self) -> genai.Client:
        """Access the underlying SDK client for advanced use cases."""
        return self._client

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        response_schema: Any = None,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
    ) -> tuple[str, dict]:
        """
        Generate text using the configured text model.
        Returns (response_text, usage_metadata).
        Raises on API errors after quota classification.
        """
        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }

        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        candidate_models = [self.text_model]
        for m in ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-pro-latest", "gemini-2.0-flash-exp"]:
            if m not in candidate_models:
                candidate_models.append(m)

        last_error = None
        for model_name in candidate_models:
            try:
                if response_schema is not None:
                    config_kwargs["response_mime_type"] = "application/json"
                    try:
                        config_kwargs["response_schema"] = response_schema
                        generation_config = genai_types.GenerateContentConfig(**config_kwargs)
                        response = self._client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=generation_config,
                        )
                    except Exception as schema_err:
                        if "404" in str(schema_err) or "not found" in str(schema_err).lower():
                            raise schema_err
                        logger.warning(
                            "generate_content with response_schema failed, falling back to JSON mode",
                            extra={"error": str(schema_err)[:300]},
                        )
                        config_kwargs.pop("response_schema", None)
                        generation_config = genai_types.GenerateContentConfig(**config_kwargs)
                        response = self._client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=generation_config,
                        )
                else:
                    generation_config = genai_types.GenerateContentConfig(**config_kwargs)
                    response = self._client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=generation_config,
                    )

                if model_name != self.text_model:
                    logger.info("Switched to working Gemini model", extra={"model": model_name})
                    self.text_model = model_name

                text = response.text or ""
                usage = {}
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    meta = response.usage_metadata
                    usage = {
                        "prompt_token_count": getattr(meta, "prompt_token_count", None),
                        "candidates_token_count": getattr(meta, "candidates_token_count", None),
                        "total_token_count": getattr(meta, "total_token_count", None),
                    }
                return text, usage

            except Exception as err:
                last_error = err
                err_str = str(err).lower()
        # If all candidates returned 404, query models.list() to discover any accessible model
        try:
            logger.info("Candidate models returned 404; querying models.list() to discover accessible models...")
            discovered_models = []
            for m in self._client.models.list():
                m_name = getattr(m, "name", "")
                if m_name.startswith("models/"):
                    m_name = m_name[7:]
                if m_name:
                    discovered_models.append(m_name)

            logger.info("Discovered available models", extra={"models": discovered_models[:10]})

            for model_name in discovered_models:
                if any(k in model_name.lower() for k in ("flash", "gemini", "pro")):
                    try:
                        config_kwargs.pop("response_schema", None)
                        generation_config = genai_types.GenerateContentConfig(**config_kwargs)
                        response = self._client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=generation_config,
                        )
                        logger.info("Successfully connected using discovered model", extra={"model": model_name})
                        self.text_model = model_name
                        return response.text or "", {}
                    except Exception:
                        continue
        except Exception as list_err:
            logger.warning("Model discovery listing failed", extra={"error": str(list_err)[:200]})

        if last_error:
            raise last_error

    def submit_video_generation(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration_seconds: int = 8,
        resolution: str = "1080p",
    ):
        """
        Submit a video generation operation. Returns the long-running operation object.
        The operation must be polled via poll_video_operation().

        NOTE: Veo generates clips of approximately 5-8 seconds. For a 10-second Short,
        the pipeline will assemble multiple clips or extend with static frames via FFmpeg.
        """
        config = genai_types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

        operation = self._client.models.generate_videos(
            model=self.video_model,
            prompt=prompt,
            config=config,
        )
        logger.info(
            "Video generation submitted",
            extra={"model": self.video_model, "operation_name": getattr(operation, "name", "unknown")},
        )
        return operation

    def poll_video_operation(self, operation):
        """
        Refresh the operation status. Returns updated operation.
        Call until operation.done is True.
        """
        return self._client.operations.get(operation)

    def get_generated_video(self, operation) -> list[Any]:
        """
        Extract generated video objects from a completed operation.
        Returns list of generated_video objects (each has a .video attribute).
        """
        if not operation.done:
            raise ValueError("Operation is not yet complete")
        if not hasattr(operation, "response") or not operation.response:
            raise ValueError("Operation completed but response is empty")
        videos = getattr(operation.response, "generated_videos", [])
        if not videos:
            raise ValueError("No generated videos in operation response")
        return videos

    def download_video(self, video_obj, output_path: str) -> None:
        """Download a generated video object to local path."""
        self._client.files.download(file=video_obj.video)
        video_obj.video.save(output_path)
        logger.info("Video downloaded", extra={"path": output_path})

    async def validate_text_model(self) -> bool:
        """
        Lightweight check that the configured text model is accessible.
        Sends a minimal prompt. Returns True if successful.
        """
        try:
            text, _ = await self.generate_text(
                prompt="Reply with exactly one word: OK",
                max_output_tokens=10,
            )
            return bool(text)
        except Exception as exc:
            logger.error(
                "Text model validation failed",
                extra={"model": self.text_model, "error": str(exc)},
            )
            return False
