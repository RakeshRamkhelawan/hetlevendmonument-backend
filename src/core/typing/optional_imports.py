"""Lazy import wrappers for optional third-party dependencies.

All libraries below are listed in pyproject.toml [[tool.mypy.overrides]] with
ignore_missing_imports = true. This means mypy ignores ImportError for these
packages -- no try/except needed inside TYPE_CHECKING blocks.

PATTERN: Use `from src.core.typing.optional_imports import X` in type
annotations. Runtime code must guard usage with its own availability check.

DEPRECATED: New code should use TYPE_CHECKING directly in the consuming module
rather than importing from here. This file will be removed once all consumers
are migrated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Sentence transformers
    from sentence_transformers import CrossEncoder, SentenceTransformer

    # Playwright
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    # Slack SDK
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    # Instructor
    import instructor as InstructorModule

    # Google Generative AI
    import google.genai as google_genai

    # Streamlit
    import streamlit as st

    # FAISS
    import faiss

    # MLflow
    import mlflow

    # Stable Baselines3
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import DummyVecEnv

    # TensorFlow Hub
    import tensorflow_hub as hub

    # LangChain
    from langchain_openai import ChatOpenAI

    # PyInstrument
    from pyinstrument import Profiler

    # APScheduler
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    # Async SMTP
    import aiosmtplib

    # SQLModel
    from sqlmodel import SQLModel

    # Docker
    import docker

    # OpenTelemetry
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

__all__ = [
    "CrossEncoder",
    "SentenceTransformer",
    "PlaywrightTimeoutError",
    "WebClient",
    "SlackApiError",
    "InstructorModule",
    "google_genai",
    "st",
    "faiss",
    "mlflow",
    "PPO",
    "BaseCallback",
    "DummyVecEnv",
    "hub",
    "ChatOpenAI",
    "Profiler",
    "AsyncIOScheduler",
    "CronTrigger",
    "aiosmtplib",
    "SQLModel",
    "docker",
    "FastAPIInstrumentor",
    "SQLAlchemyInstrumentor",
]
