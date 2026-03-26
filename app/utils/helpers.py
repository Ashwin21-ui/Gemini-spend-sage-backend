"""Shared utility functions - vector operations, validators, helpers"""

import numpy as np
from typing import List, Dict, Any
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


def cosine_similarity(vec1, vec2) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Args:
        vec1: First vector (list or numpy array)
        vec2: Second vector (list or numpy array)
    
    Returns:
        Similarity score between 0 and 1
    """
    v1 = np.array(vec1, dtype=np.float32) if not isinstance(vec1, np.ndarray) else vec1
    v2 = np.array(vec2, dtype=np.float32) if not isinstance(vec2, np.ndarray) else vec2
    
    if v1.size == 0 or v2.size == 0:
        return 0.0
    
    dot_product = np.dot(v1, v2)
    magnitude1 = np.linalg.norm(v1)
    magnitude2 = np.linalg.norm(v2)
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return float(dot_product / (magnitude1 * magnitude2))


def validate_uuid(value: str) -> UUID:
    """
    Validate and convert string to UUID.
    
    Args:
        value: String UUID value
    
    Returns:
        UUID object
    
    Raises:
        ValueError: If invalid UUID format
    """
    try:
        return UUID(value)
    except (ValueError, AttributeError) as e:
        logger.warning(f"Invalid UUID format: {value}")
        raise ValueError(f"Invalid UUID: {str(e)}")


def format_error_context(error: Exception, context: Dict[str, Any]) -> str:
    """
    Format error with context for logging.
    
    Args:
        error: Exception instance
        context: Dictionary of contextual information
    
    Returns:
        Formatted error message
    """
    context_str = " | ".join(f"{k}={v}" for k, v in context.items())
    return f"{error.__class__.__name__}: {str(error)} | {context_str}"
