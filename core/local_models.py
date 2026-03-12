"""Local ML Models Module - Lightweight embeddings and sentiment analysis

This module provides local ML capabilities for:
- Text embeddings (similarity, duplicate detection)
- Sentiment analysis (tone detection)
- Text quality scoring

Models are loaded on-demand and cached for reuse.
All processing happens locally - no API calls.

Models:
- Embeddings: sentence-transformers/all-MiniLM-L6-v2 (~80MB)
- Sentiment: distilbert-base-uncased-finetuned-sst-2 (~67MB)
"""

import threading
from typing import Any

_embedding_model = None
_sentiment_pipeline = None
_lock = threading.Lock()


def get_embedding_model():
    """Get or load the sentence embedding model (thread-safe lazy loading)"""
    global _embedding_model

    if _embedding_model is None:
        with _lock:
            if _embedding_model is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    _embedding_model = SentenceTransformer(
                        "all-MiniLM-L6-v2",
                        local_files_only=False,
                    )
                except ImportError:
                    raise ImportError(
                        "sentence-transformers not installed. "
                        "Run: uv add sentence-transformers"
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed to load embedding model: {e}")

    return _embedding_model


def get_sentiment_pipeline():
    """Get or load the sentiment analysis pipeline (thread-safe lazy loading)"""
    global _sentiment_pipeline

    if _sentiment_pipeline is None:
        with _lock:
            if _sentiment_pipeline is None:
                try:
                    from transformers import pipeline

                    _sentiment_pipeline = pipeline(
                        "sentiment-analysis",
                        model="distilbert-base-uncased-finetuned-sst-2-english",
                        local_files_only=False,
                    )
                except ImportError:
                    raise ImportError(
                        "transformers not installed. "
                        "Run: uv add transformers torch"
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed to load sentiment model: {e}")

    return _sentiment_pipeline


def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector for text

    Args:
        text: Input text to embed

    Returns:
        List of floats (384-dimensional for all-MiniLM-L6-v2)
    """
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()  # type: ignore[no-any-return]


def compute_similarity(text1: str, text2: str) -> float:
    """Compute cosine similarity between two texts

    Args:
        text1: First text
        text2: Second text

    Returns:
        Cosine similarity score (0.0 to 1.0)
    """
    model = get_embedding_model()
    embeddings = model.encode([text1, text2], convert_to_numpy=True)
    similarity = cosine_similarity(embeddings[0], embeddings[1])
    return float(similarity)


def cosine_similarity(vec1: list[float] | Any, vec2: list[float] | Any) -> float:
    """Compute cosine similarity between two vectors"""
    import numpy as np

    vec1 = np.array(vec1) if not hasattr(vec1, "dtype") else vec1
    vec2 = np.array(vec2) if not hasattr(vec2, "dtype") else vec2

    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(dot_product / (norm1 * norm2))


def analyze_sentiment(text: str) -> dict[str, Any]:
    """Analyze sentiment of text

    Args:
        text: Input text to analyze

    Returns:
        Dict with 'label' (POSITIVE/NEGATIVE) and 'score' (confidence)
    """
    pipeline = get_sentiment_pipeline()
    result = pipeline(text[:512])[0]  
    return {
        "label": result["label"],
        "score": result["score"],
    }


def compute_text_quality_score(text: str) -> int:
    """Compute a simple text quality score based on multiple factors

    Factors:
    - Length (not too short, not too long)
    - Sentence structure (presence of punctuation)
    - Sentiment (positive tone preferred)
    - Readability (average word length)

    Args:
        text: Input text to score

    Returns:
        Quality score 0-100
    """
    if not text or not text.strip():
        return 0

    score = 100
    words = text.split()
    word_count = len(words)

    if word_count < 10:
        score -= 40
    elif word_count < 30:
        score -= 20
    elif word_count > 500:
        score -= 20

    sentences = text.replace("!", ".").replace("?", ".").split(".")
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 2:
        score -= 15

    avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
    if avg_word_length > 8:
        score -= 10  
    elif avg_word_length < 3:
        score -= 10  

    try:
        sentiment = analyze_sentiment(text)
        if sentiment["label"] == "NEGATIVE" and sentiment["score"] > 0.7:
            score -= 15
    except Exception:
        pass  

    return max(0, min(100, score))


def find_duplicates(
    texts: list[str],
    threshold: float = 0.85,
) -> list[tuple[int, int, float]]:
    """Find duplicate/similar texts in a list

    Args:
        texts: List of texts to compare
        threshold: Similarity threshold (0.0 to 1.0)

    Returns:
        List of (index1, index2, similarity) tuples for similar pairs
    """
    if len(texts) < 2:
        return []

    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True)

    duplicates = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            similarity = cosine_similarity(embeddings[i], embeddings[j])
            if similarity >= threshold:
                duplicates.append((i, j, similarity))

    return duplicates


def is_available() -> bool:
    """Check if local models are available (dependencies installed)

    Returns:
        True if both embedding and sentiment models can be loaded
    """
    try:
        import importlib.util

        has_transformers = importlib.util.find_spec("transformers") is not None
        has_sentence_transformers = importlib.util.find_spec("sentence_transformers") is not None

        if not (has_transformers and has_sentence_transformers):
            return False

        get_embedding_model()
        return True
    except Exception:
        return False


def get_model_info() -> dict[str, Any]:
    """Get information about loaded models"""
    return {
        "embedding_model": {
            "name": "all-MiniLM-L6-v2",
            "size": "~80MB",
            "dimension": 384,
            "loaded": _embedding_model is not None,
        },
        "sentiment_model": {
            "name": "distilbert-base-uncased-finetuned-sst-2",
            "size": "~67MB",
            "loaded": _sentiment_pipeline is not None,
        },
        "available": is_available(),
    }
