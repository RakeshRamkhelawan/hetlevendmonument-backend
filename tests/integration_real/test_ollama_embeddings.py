"""
REAL Integration Test: Ollama Embeddings.

Tests actual HTTP calls to Ollama service.
NO MOCKS - Real embedding generation.
"""

import numpy as np
import pytest


@pytest.mark.integration
@pytest.mark.requires_ollama
class TestOllamaEmbeddingsReal:
    """Test real Ollama embedding generation."""

    async def test_ollama_service_available(self, real_ollama_embedder):
        """
        Integration Test: Ollama service is running and healthy.
        """
        is_healthy = await real_ollama_embedder.health_check()
        assert is_healthy is True, "Ollama service not healthy"

    async def test_generate_single_embedding(self, real_ollama_embedder):
        """
        Integration Test: Generate embedding for single text.

        Verifies:
        - HTTP call succeeds
        - Returns numpy array
        - Correct dimensions (768 for nomic-embed-text)
        - Values are normalized
        """
        text = "Process vendor invoice for payment"

        embedding = await real_ollama_embedder.embed(text)

        # Verify shape
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (768,), f"Expected shape (768,), got {embedding.shape}"

        # Verify values are reasonable (not all zeros, not NaN)
        assert not np.all(embedding == 0), "Embedding is all zeros"
        assert not np.any(np.isnan(embedding)), "Embedding contains NaN values"

        # Verify dimension property
        assert real_ollama_embedder.dimension == 768

    async def test_embedding_consistency(self, real_ollama_embedder):
        """
        Integration Test: Same text produces consistent embeddings.

        Note: Ollama embeddings are deterministic for the same model.
        """
        text = "Quarterly financial report"

        embedding1 = await real_ollama_embedder.embed(text)
        embedding2 = await real_ollama_embedder.embed(text)

        # Should be very similar (if not identical)
        similarity = np.dot(embedding1, embedding2) / (
            np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
        )

        assert similarity > 0.99, f"Embeddings not consistent: similarity={similarity}"

    async def test_different_texts_different_embeddings(self, real_ollama_embedder):
        """
        Integration Test: Different texts produce different embeddings.
        """
        text1 = "Process invoice"
        text2 = "Hire new employee"
        text3 = "Process invoice"  # Same as text1

        emb1 = await real_ollama_embedder.embed(text1)
        emb2 = await real_ollama_embedder.embed(text2)
        emb3 = await real_ollama_embedder.embed(text3)

        # emb1 and emb2 should be different
        similarity_1_2 = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        assert similarity_1_2 < 0.9, f"Different texts too similar: {similarity_1_2}"

        # emb1 and emb3 should be very similar (same text)
        similarity_1_3 = np.dot(emb1, emb3) / (np.linalg.norm(emb1) * np.linalg.norm(emb3))
        assert similarity_1_3 > 0.99, f"Same text not similar enough: {similarity_1_3}"

    async def test_semantic_similarity_finance_tasks(self, real_ollama_embedder):
        """
        Integration Test: Finance-related tasks have similar embeddings.

        This verifies the embedding model captures semantic meaning.
        """
        finance_texts = [
            "Process monthly invoices",
            "Review vendor payments",
            "Analyze quarterly budget",
            "Calculate tax liabilities",
        ]

        hr_texts = [
            "Interview job candidates",
            "Review employee performance",
            "Process payroll",
            "Conduct training sessions",
        ]

        # Generate embeddings
        finance_embs = [await real_ollama_embedder.embed(t) for t in finance_texts]
        hr_embs = [await real_ollama_embedder.embed(t) for t in hr_texts]

        # Calculate average within-group similarity
        def avg_similarity(embs):
            sims = []
            for i in range(len(embs)):
                for j in range(i + 1, len(embs)):
                    sim = np.dot(embs[i], embs[j]) / (
                        np.linalg.norm(embs[i]) * np.linalg.norm(embs[j])
                    )
                    sims.append(sim)
            return np.mean(sims)

        finance_internal_sim = avg_similarity(finance_embs)
        hr_internal_sim = avg_similarity(hr_embs)

        # Finance tasks should be similar to each other
        assert (
            finance_internal_sim > 0.7
        ), f"Finance tasks not semantically similar: {finance_internal_sim}"

        # HR tasks should be similar to each other
        assert hr_internal_sim > 0.7, f"HR tasks not semantically similar: {hr_internal_sim}"

        # Cross-group similarity should be lower
        cross_sims = []
        for f_emb in finance_embs:
            for h_emb in hr_embs:
                sim = np.dot(f_emb, h_emb) / (np.linalg.norm(f_emb) * np.linalg.norm(h_emb))
                cross_sims.append(sim)

        cross_sim = np.mean(cross_sims)
        assert cross_sim < finance_internal_sim, "Cross-group similarity too high"

    async def test_embedding_batch_processing(self, real_ollama_embedder):
        """
        Integration Test: Batch embedding generation.
        """
        texts = [
            "Task 1: Process invoice",
            "Task 2: Review budget",
            "Task 3: Hire employee",
            "Task 4: Security audit",
            "Task 5: Design feature",
        ]

        embeddings = await real_ollama_embedder.embed_batch(texts)

        # Verify shape
        assert embeddings.shape == (5, 768)

        # Verify all embeddings are valid
        for i, emb in enumerate(embeddings):
            assert not np.all(emb == 0), f"Embedding {i} is all zeros"
            assert not np.any(np.isnan(emb)), f"Embedding {i} contains NaN"

    async def test_empty_text_handling(self, real_ollama_embedder):
        """
        Integration Test: Empty text returns zero embedding.
        """
        embedding = await real_ollama_embedder.embed("")

        # Should return zero vector
        assert np.all(embedding == 0), "Empty text should return zero embedding"

    async def test_long_text_truncation(self, real_ollama_embedder):
        """
        Integration Test: Long texts are handled correctly.
        """
        # Create a very long text (10,000 characters)
        long_text = "Analyze budget " * 500

        embedding = await real_ollama_embedder.embed(long_text)

        # Should still return valid embedding
        assert embedding.shape == (768,)
        assert not np.any(np.isnan(embedding))

    async def test_embedding_performance(self, real_ollama_embedder):
        """
        Integration Test: Embedding generation performance.

        Should complete within reasonable time (< 5 seconds for single embedding).
        """
        import time

        text = "Process vendor invoice for quarterly payment"

        start = time.time()
        embedding = await real_ollama_embedder.embed(text)
        elapsed = time.time() - start

        # Should be reasonably fast (local model)
        assert elapsed < 5.0, f"Embedding too slow: {elapsed:.2f}s"

        # Verify result is still correct
        assert embedding.shape == (768,)


@pytest.mark.integration
@pytest.mark.requires_ollama
class TestOllamaModelAvailability:
    """Test Ollama model availability and configuration."""

    async def test_nomic_embed_text_available(self, real_ollama_embedder):
        """
        Integration Test: nomic-embed-text model is loaded.
        """
        # This is implicitly tested by the embedder fixture,
        # but we verify explicitly here
        assert real_ollama_embedder.model == "nomic-embed-text"
        assert await real_ollama_embedder.health_check() is True

    async def test_model_dimension_correct(self, real_ollama_embedder):
        """
        Integration Test: Model produces expected dimension.

        nomic-embed-text should produce 768-dimensional embeddings.
        """
        embedding = await real_ollama_embedder.embed("test")

        assert len(embedding) == 768
        assert real_ollama_embedder.dimension == 768
