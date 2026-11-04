"""Orchestrator for autonomous workflow system."""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from prometheus_client import Gauge, start_http_server

from .config import WorkflowConfig
from .feedback import FeedbackService
from .training import TrainingPipeline

# Metrics
TRAINING_CYCLE_TIME = Gauge("training_cycle_time", "Time since last training cycle")
ACTIVE_EXPERIENCES = Gauge("active_experiences", "Number of active experiences")


class WorkflowOrchestrator:
    """Main orchestrator for autonomous workflow system."""

    def __init__(
        self,
        config: WorkflowConfig,
        feedback_service: FeedbackService,
        training_pipeline: TrainingPipeline,
    ) -> None:
        self.config = config
        self.feedback_service = feedback_service
        self.training_pipeline = training_pipeline
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.last_training_time = datetime.now(timezone.utc)

    async def start(self) -> None:
        """Start the orchestrator."""
        self.running = True

        # Setup metrics server if enabled
        if self.config.enable_metrics:
            start_http_server(self.config.metrics_port)

        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._signal_handler)

        try:
            while self.running:
                await self._run_training_cycle()
                await asyncio.sleep(300)  # 5 minutes between cycles

        except Exception as e:
            self.logger.error(f"Orchestrator error: {str(e)}")
            self.running = False
            raise

    def _signal_handler(self, signum: int, frame: object) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}")
        self.running = False
        sys.exit(0)

    async def _run_training_cycle(self) -> None:
        """Execute one training cycle."""
        try:
            # Update metrics
            TRAINING_CYCLE_TIME.set(
                (datetime.now(timezone.utc) - self.last_training_time).total_seconds()
            )

            # Get unprocessed experiences
            experiences = await self.feedback_service.get_unprocessed_experiences(
                limit=self.config.batch_size
            )

            if not experiences:
                self.logger.info("No new experiences to process")
                return

            ACTIVE_EXPERIENCES.set(len(experiences))

            # Train on experiences
            training_result = await self.training_pipeline.train_on_experiences(
                experiences, epochs=self.config.training_epochs
            )

            if "error" in training_result:
                raise RuntimeError(f"Training failed: {training_result['error']}")

            # Mark experiences as processed
            experience_ids = [exp.id for exp in experiences]
            await self.feedback_service.mark_experiences_processed(experience_ids)

            # Save model if training was successful
            self.training_pipeline.save_model("models/latest.pt")

            # Update last training time
            self.last_training_time = datetime.now(timezone.utc)

            self.logger.info(
                f"Training cycle completed: processed {len(experiences)} experiences, "
                f"loss: {training_result['average_loss']:.4f}"
            )

        except Exception as e:
            self.logger.error(f"Error in training cycle: {str(e)}")
            raise

    async def shutdown(self) -> None:
        """Graceful shutdown of the orchestrator."""
        self.logger.info("Shutting down orchestrator...")
        self.running = False
        # Additional cleanup if needed
