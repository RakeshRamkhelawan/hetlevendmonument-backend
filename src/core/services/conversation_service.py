"""
Conversation Persistence Service
Handles persistent storage and retrieval of CVA conversations for learning
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from sqlalchemy import desc, select

from src.core.conversations.models import CVAConversation
from src.core.database.database import db_manager
from src.core.middleware.tenant_context import get_tenant_id

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing persistent CVA conversations"""

    @staticmethod
    async def save_conversation(
        session_id: str,
        user_id: str,
        user_message: str,
        cva_response: str,
        conversation_turn: int,
        response_metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        performance_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        conversation_history: list[dict[str, Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """
        Save a conversation turn to database
        Returns the conversation ID
        """
        try:
            # Ensure database is initialized before using it
            if not db_manager.is_initialized():
                logger.warning("Database manager not initialized, initializing now...")
                if not await db_manager.initialize():
                    raise Exception("Failed to initialize database manager")

            async with db_manager.get_session() as db_session:
                # Create context summary from conversation history
                context_summary = None
                if conversation_history:
                    context_summary = ConversationService._create_context_summary(
                        conversation_history
                    )

                conversation = CVAConversation(
                    session_id=session_id,
                    user_id=user_id,
                    user_message=user_message,
                    cva_response=cva_response,
                    conversation_turn=conversation_turn,
                    context_summary=context_summary,
                    response_metadata=response_metadata or {},
                    performance_data=performance_data or {},
                )

                db_session.add(conversation)
                await db_session.commit()
                await db_session.refresh(conversation)

                logger.info(f"Saved conversation turn {conversation_turn} for session {session_id}")
                return cast(str, conversation.id)

        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")
            raise Exception(f"Failed to save conversation: {e}") from e

    @staticmethod
    async def get_conversation_history(session_id: str, limit: int = 50) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get conversation history for a session
        Returns list of conversation turns in chronological order
        """
        try:
            # Ensure database is initialized before using it
            if not db_manager.is_initialized():
                logger.warning("Database manager not initialized for get_conversation_history")
                if not await db_manager.initialize():
                    logger.error("Failed to initialize database manager")
                    return []

            async with db_manager.get_session() as db_session:
                tenant_id = get_tenant_id()
                stmt = (
                    select(CVAConversation)
                    .where(
                        CVAConversation.tenant_id == tenant_id,
                        CVAConversation.session_id == session_id,
                    )
                    .order_by(CVAConversation.conversation_turn)
                    .limit(limit)
                )
                result = await db_session.execute(stmt)
                conversations = result.scalars().all()

                history: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for conv in conversations:
                    history.extend(
                        [
                            {"role": "user", "content": conv.user_message},
                            {"role": "assistant", "content": conv.cva_response},
                        ]
                    )

                logger.debug(f"Retrieved {len(history)} messages for session {session_id}")
                return history

        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []

    @staticmethod
    async def get_learning_data(limit: int = 100) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get conversation data for learning and analytics
        Returns conversations with performance and feedback data
        """
        try:
            # Ensure database is initialized before using it
            if not db_manager.is_initialized():
                logger.warning("Database manager not initialized for get_learning_data")
                if not await db_manager.initialize():
                    logger.error("Failed to initialize database manager")
                    return []

            async with db_manager.get_session() as db_session:
                tenant_id = get_tenant_id()
                stmt = (
                    select(CVAConversation)
                    .where(
                        CVAConversation.tenant_id == tenant_id,
                        CVAConversation.user_feedback.isnot(None),
                    )
                    .order_by(desc(CVAConversation.created_at))
                    .limit(limit)
                )
                result = await db_session.execute(stmt)
                conversations = result.scalars().all()

                learning_data: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for conv in conversations:
                    learning_data.append(
                        {
                            "conversation_id": conv.id,
                            "user_message": conv.user_message,
                            "cva_response": conv.cva_response,
                            "user_feedback": conv.user_feedback,
                            "feedback_details": conv.feedback_details,
                            "performance_data": conv.performance_data,
                            "conversation_topic": conv.conversation_topic,
                            "keywords": conv.keywords,
                            "created_at": conv.created_at.isoformat() if conv.created_at else None,
                        }
                    )

                logger.info(f"Retrieved {len(learning_data)} learning samples")
                return learning_data

        except Exception as e:
            logger.error(f"Failed to get learning data: {e}")
            return []

    @staticmethod
    async def add_feedback(
        conversation_id: str, feedback: str, details: str | None = None
    ) -> bool:
        """
        Add user feedback to a conversation for learning
        """
        try:
            # Ensure database is initialized before using it
            if not db_manager.is_initialized():
                logger.warning("Database manager not initialized for add_feedback")
                if not await db_manager.initialize():
                    logger.error("Failed to initialize database manager")
                    return False

            async with db_manager.get_session() as db_session:
                tenant_id = get_tenant_id()
                stmt = select(CVAConversation).where(
                    CVAConversation.tenant_id == tenant_id,
                    CVAConversation.id == conversation_id,
                )
                result = await db_session.execute(stmt)
                conversation = result.scalars().first()

                if conversation:
                    conversation.user_feedback = feedback
                    conversation.feedback_details = details
                    await db_session.commit()

                    logger.info(f"Added feedback '{feedback}' to conversation {conversation_id}")
                    return True
                else:
                    logger.warning(f"Conversation {conversation_id} not found")
                    return False

        except Exception as e:
            logger.error(f"Failed to add feedback: {e}")
            return False

    @staticmethod
    async def get_conversation_analytics(days: int = 30) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get analytics data for conversations over specified days
        """
        try:
            from sqlalchemy import and_, func

            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            # Ensure database is initialized before using it
            if not db_manager.is_initialized():
                logger.warning("Database manager not initialized for get_conversation_analytics")
                if not await db_manager.initialize():
                    logger.error("Failed to initialize database manager")
                    return {}

            async with db_manager.get_session() as db_session:
                tenant_id = get_tenant_id()
                # Total conversations
                count_stmt = select(func.count(CVAConversation.id)).where(
                    CVAConversation.tenant_id == tenant_id,
                    CVAConversation.created_at >= cutoff_date,
                )
                count_result = await db_session.execute(count_stmt)
                total_conversations = count_result.scalar() or 0

                # Feedback distribution
                feedback_stmt = (
                    select(
                        CVAConversation.user_feedback,
                        func.count(CVAConversation.id).label("count"),
                    )
                    .where(
                        and_(
                            CVAConversation.tenant_id == tenant_id,
                            CVAConversation.created_at >= cutoff_date,
                            CVAConversation.user_feedback.isnot(None),
                        )
                    )
                    .group_by(CVAConversation.user_feedback)
                )
                feedback_result = await db_session.execute(feedback_stmt)
                feedback_stats = feedback_result.all()

                # Most common topics
                topic_stmt = (
                    select(
                        CVAConversation.conversation_topic,
                        func.count(CVAConversation.id).label("count"),
                    )
                    .where(
                        and_(
                            CVAConversation.tenant_id == tenant_id,
                            CVAConversation.created_at >= cutoff_date,
                            CVAConversation.conversation_topic.isnot(None),
                        )
                    )
                    .group_by(CVAConversation.conversation_topic)
                    .order_by(func.count(CVAConversation.id).desc())
                    .limit(10)
                )
                topic_result = await db_session.execute(topic_stmt)
                topic_stats = topic_result.all()

                analytics = {
                    "period_days": days,
                    "total_conversations": total_conversations,
                    "feedback_distribution": {
                        stat.user_feedback: stat.count for stat in feedback_stats
                    },
                    "top_topics": [
                        {"topic": stat.conversation_topic, "count": stat.count}
                        for stat in topic_stats
                    ],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }

                logger.info(
                    f"Generated analytics for {days} days: {total_conversations} conversations"
                )
                return analytics

        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return {}

    @staticmethod
    def _create_context_summary(conversation_history: list[dict[str, Any]]) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Create a brief summary of conversation context for storage
        """
        if not conversation_history:
            return ""

        # Simple context summary - could be enhanced with AI summarization
        user_messages = [msg["content"] for msg in conversation_history if msg["role"] == "user"]
        topics: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Extract key topics/keywords (simple approach)
        for message in user_messages[-3:]:  # Last 3 user messages
            words = message.lower().split()
            key_words = [
                word
                for word in words
                if len(word) > 4 and word not in ["have", "would", "could", "should"]
            ]
            topics.extend(key_words[:2])  # Top 2 words per message

        context = (
            f"Topics discussed: {', '.join(set(topics[:5]))}" if topics else "General conversation"
        )
        return context
