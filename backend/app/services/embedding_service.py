"""Service for generating text embeddings using OpenAI with rate limiting, retries, and caching."""

import contextlib
import hashlib
import logging
import time
from datetime import date, datetime
from typing import Any

from openai import OpenAI, RateLimitError

from app.config import get_settings
from app.observability.metrics import (
    openai_budget_exceeded_total,
    openai_daily_spending_usd,
    openai_embedding_cache_hits_total,
    openai_embedding_cost_usd,
    openai_embedding_duration_seconds,
    openai_embedding_tokens_total,
    openai_embeddings_total,
    openai_rate_limit_errors_total,
)

logger = logging.getLogger(__name__)

# OpenAI text-embedding-3-small pricing (per 1K tokens)
# Input: $0.02 per 1M tokens
EMBEDDING_COST_PER_1M_TOKENS = 0.02


class BudgetExceededError(Exception):
    """Exception raised when OpenAI budget limit is exceeded."""

    def __init__(self, daily_spending: float, budget: float):
        """Initialize budget exceeded error.

        Args:
            daily_spending: Current daily spending in USD
            budget: Daily budget limit in USD
        """
        self.daily_spending = daily_spending
        self.budget = budget
        message = f"OpenAI daily budget exceeded: ${daily_spending:.6f} / ${budget:.2f} USD"
        super().__init__(message)


class EmbeddingService:
    """Service for generating embeddings using OpenAI's text-embedding-3-small model.

    Features:
    - Rate limiting and automatic retries
    - Caching for duplicate log messages
    - Batch processing for cost optimization
    - Cost tracking and monitoring
    - Metadata tracking (model, timestamp, cost)
    """

    def __init__(self):
        """Initialize embedding service."""
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured. Embeddings will not work.")
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = "text-embedding-3-small"
        self.vector_size = 1536

        # Budget configuration
        self.daily_budget = settings.openai_budget
        if self.daily_budget is not None:
            logger.info(f"OpenAI daily budget enabled: ${self.daily_budget:.2f} USD")
        else:
            logger.info("OpenAI daily budget not set (unlimited)")

        # Daily spending tracking
        # Format: {date: spending_amount}
        # In production, consider using Redis or database for persistence
        self._daily_spending: dict[date, float] = {}
        self._current_date = date.today()

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # Initial delay in seconds
        self.max_retry_delay = 60.0  # Maximum delay in seconds
        self.rate_limit_retry_delay = 60.0  # Delay for rate limit errors

        # In-memory cache for embeddings (text_hash -> embedding)
        # In production, consider using Redis or similar
        self._embedding_cache: dict[str, dict[str, Any]] = {}

        # Batch processing configuration
        # OpenAI allows up to 2048 inputs per request
        self.max_batch_size = 2048

    def _get_text_hash(self, text: str) -> str:
        """Generate hash for text to use as cache key.

        Args:
            text: Text to hash

        Returns:
            SHA256 hash of the text
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _calculate_cost(self, tokens: int) -> float:
        """Calculate cost for embedding generation.

        Args:
            tokens: Number of tokens processed

        Returns:
            Cost in USD
        """
        return (tokens / 1_000_000) * EMBEDDING_COST_PER_1M_TOKENS

    def _get_current_daily_spending(self) -> float:
        """Get current daily spending for today.

        Automatically resets if date has changed.

        Returns:
            Current daily spending in USD
        """
        today = date.today()
        if today != self._current_date:
            # Date changed, reset spending for new day
            logger.info(
                f"Date changed from {self._current_date} to {today}. Resetting daily spending."
            )
            self._current_date = today
            self._daily_spending[today] = 0.0

        return self._daily_spending.get(today, 0.0)

    def _record_spending(self, cost: float) -> None:
        """Record spending for the current day.

        Args:
            cost: Cost in USD to add to daily spending
        """
        today = date.today()
        if today != self._current_date:
            # Date changed, reset spending for new day
            self._current_date = today
            self._daily_spending[today] = 0.0

        current_spending = self._daily_spending.get(today, 0.0)
        self._daily_spending[today] = current_spending + cost

        # Update Prometheus metric
        openai_daily_spending_usd.labels(model=self.model).set(self._daily_spending[today])

        logger.debug(
            f"Recorded spending: ${cost:.6f}. Daily total: ${self._daily_spending[today]:.6f} USD"
        )

    def _check_budget(self, estimated_cost: float = 0.0) -> None:
        """Check if we're within budget before generating embeddings.

        Args:
            estimated_cost: Estimated cost for the operation (optional)

        Raises:
            BudgetExceededError: If daily budget would be exceeded
        """
        if self.daily_budget is None:
            # No budget set, allow all requests
            return

        current_spending = self._get_current_daily_spending()
        projected_spending = current_spending + estimated_cost

        if projected_spending > self.daily_budget:
            openai_budget_exceeded_total.labels(model=self.model).inc()
            logger.warning(
                f"Budget check failed: ${current_spending:.6f} spent, "
                f"${estimated_cost:.6f} estimated, "
                f"${self.daily_budget:.2f} budget limit"
            )
            raise BudgetExceededError(current_spending, self.daily_budget)

        # Log if approaching budget (80% threshold)
        if current_spending > 0 and (current_spending / self.daily_budget) >= 0.8:
            logger.warning(
                f"Approaching budget limit: ${current_spending:.6f} / "
                f"${self.daily_budget:.2f} USD ({current_spending / self.daily_budget * 100:.1f}%)"
            )

    def _handle_rate_limit(self, attempt: int, error: RateLimitError) -> bool:
        """Handle rate limit errors with exponential backoff.

        Args:
            attempt: Current retry attempt number
            error: Rate limit error from OpenAI

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_retries:
            logger.error(f"Max retries reached for rate limit error: {error}")
            openai_rate_limit_errors_total.labels(model=self.model).inc()
            return False

        # Check if error message contains retry-after information
        retry_after = self.rate_limit_retry_delay
        if hasattr(error, "response") and error.response:
            headers = error.response.headers
            if headers and "retry-after" in headers:
                with contextlib.suppress(ValueError, TypeError):
                    retry_after = float(headers["retry-after"])

        wait_time = min(retry_after * (2 ** (attempt - 1)), self.max_retry_delay)
        logger.warning(
            f"Rate limit hit. Waiting {wait_time:.2f}s before retry "
            f"(attempt {attempt + 1}/{self.max_retries})"
        )
        time.sleep(wait_time)
        openai_rate_limit_errors_total.labels(model=self.model).inc()
        return True

    def _retry_with_backoff(self, func: callable, *args, **kwargs) -> Any:
        """Execute function with exponential backoff retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result or None if all retries failed
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                last_error = e
                if not self._handle_rate_limit(attempt + 1, e):
                    break
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = min(self.retry_delay * (2**attempt), self.max_retry_delay)
                    logger.warning(
                        f"Error in embedding generation (attempt {attempt + 1}/"
                        f"{self.max_retries}): {e}. Retrying in {wait_time:.2f}s"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Max retries reached. Error: {e}", exc_info=True)
                    break

        if last_error:
            logger.error(f"Failed after {self.max_retries} retries: {last_error}")
        return None

    def generate_embedding(self, text: str, use_cache: bool = True) -> dict[str, Any] | None:
        """Generate embedding for text with caching and metadata.

        Args:
            text: Text to generate embedding for
            use_cache: Whether to use cache for duplicate texts

        Returns:
            Dictionary with embedding, metadata, and cost, or None if error
            {
                'embedding': list[float],
                'model': str,
                'timestamp': datetime,
                'cost_usd': float,
                'tokens': int,
                'cached': bool
            }
        """
        if not self.client:
            logger.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
            return None

        # Check cache first
        if use_cache:
            text_hash = self._get_text_hash(text)
            if text_hash in self._embedding_cache:
                cached_result = self._embedding_cache[text_hash]
                logger.debug(f"Cache hit for text hash: {text_hash[:8]}...")
                openai_embedding_cache_hits_total.inc()
                # Return cached result with updated timestamp
                return {
                    **cached_result,
                    "timestamp": datetime.utcnow(),
                    "cached": True,
                }

        # Check budget before generating embedding
        # Estimate cost based on text length (rough estimate: ~4 chars per token)
        estimated_tokens = len(text) // 4
        estimated_cost = self._calculate_cost(estimated_tokens)
        self._check_budget(estimated_cost)

        # Generate embedding
        start_time = time.time()
        try:
            response = self._retry_with_backoff(
                self.client.embeddings.create,
                model=self.model,
                input=text,
            )

            if not response:
                openai_embeddings_total.labels(model=self.model, status="error").inc()
                return None

            duration = time.time() - start_time
            embedding = response.data[0].embedding

            # Extract usage information
            usage = response.usage
            tokens = usage.total_tokens if usage else 0
            cost = self._calculate_cost(tokens)

            # Update metrics
            openai_embeddings_total.labels(model=self.model, status="success").inc()
            openai_embedding_duration_seconds.labels(model=self.model).observe(duration)
            openai_embedding_cost_usd.labels(model=self.model).inc(cost)
            openai_embedding_tokens_total.labels(model=self.model).inc(tokens)

            # Record spending for budget tracking
            self._record_spending(cost)

            result = {
                "embedding": embedding,
                "model": self.model,
                "timestamp": datetime.utcnow(),
                "cost_usd": cost,
                "tokens": tokens,
                "cached": False,
            }

            # Cache the result
            if use_cache:
                text_hash = self._get_text_hash(text)
                self._embedding_cache[text_hash] = result.copy()

            logger.debug(f"Generated embedding: {tokens} tokens, ${cost:.6f}, {duration:.3f}s")
            return result

        except BudgetExceededError:
            # Re-raise budget exceeded errors (don't log as generic error)
            raise
        except Exception as e:
            duration = time.time() - start_time
            openai_embeddings_total.labels(model=self.model, status="error").inc()
            openai_embedding_duration_seconds.labels(model=self.model).observe(duration)
            logger.error(f"Error generating embedding: {e}", exc_info=True)
            return None

    def generate_embeddings_batch(
        self, texts: list[str], use_cache: bool = True
    ) -> list[dict[str, Any] | None]:
        """Generate embeddings for multiple texts in batch with caching.

        Args:
            texts: List of texts to generate embeddings for
            use_cache: Whether to use cache for duplicate texts

        Returns:
            List of embedding results (same format as generate_embedding)
            or None for failed embeddings
        """
        if not self.client:
            logger.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
            return [None] * len(texts)

        if not texts:
            return []

        # Separate texts into cached and uncached
        results: list[dict[str, Any] | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        if use_cache:
            for i, text in enumerate(texts):
                text_hash = self._get_text_hash(text)
                if text_hash in self._embedding_cache:
                    cached_result = self._embedding_cache[text_hash]
                    results[i] = {
                        **cached_result,
                        "timestamp": datetime.utcnow(),
                        "cached": True,
                    }
                    openai_embedding_cache_hits_total.inc()
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = texts

        # Process uncached texts in batches
        if uncached_texts:
            # Check budget before processing batch
            # Estimate cost for all uncached texts
            total_estimated_tokens = sum(len(text) // 4 for text in uncached_texts)
            estimated_cost = self._calculate_cost(total_estimated_tokens)
            self._check_budget(estimated_cost)

            # Split into batches if needed
            for batch_start in range(0, len(uncached_texts), self.max_batch_size):
                batch_end = min(batch_start + self.max_batch_size, len(uncached_texts))
                batch_texts = uncached_texts[batch_start:batch_end]
                batch_indices = uncached_indices[batch_start:batch_end]

                start_time = time.time()
                try:
                    response = self._retry_with_backoff(
                        self.client.embeddings.create,
                        model=self.model,
                        input=batch_texts,
                    )

                    if not response:
                        # Mark batch as failed
                        for idx in batch_indices:
                            results[idx] = None
                        continue

                    duration = time.time() - start_time

                    # Extract usage information
                    usage = response.usage
                    total_tokens = usage.total_tokens if usage else 0
                    cost = self._calculate_cost(total_tokens)

                    # Update metrics
                    openai_embeddings_total.labels(model=self.model, status="success").inc()
                    openai_embedding_duration_seconds.labels(model=self.model).observe(duration)
                    openai_embedding_cost_usd.labels(model=self.model).inc(cost)
                    openai_embedding_tokens_total.labels(model=self.model).inc(total_tokens)

                    # Record spending for budget tracking
                    self._record_spending(cost)

                    # Process results
                    # OpenAI returns embeddings in order, but we need to map them
                    # to the original indices
                    embeddings_dict = {item.index: item.embedding for item in response.data}

                    # Calculate cost per item (approximate)
                    cost_per_item = cost / len(batch_texts) if batch_texts else 0
                    tokens_per_item = total_tokens // len(batch_texts) if batch_texts else 0

                    for local_idx, global_idx in enumerate(batch_indices):
                        embedding = embeddings_dict.get(local_idx)
                        if embedding:
                            result = {
                                "embedding": embedding,
                                "model": self.model,
                                "timestamp": datetime.utcnow(),
                                "cost_usd": cost_per_item,
                                "tokens": tokens_per_item,
                                "cached": False,
                            }
                            results[global_idx] = result

                            # Cache the result
                            if use_cache:
                                text_hash = self._get_text_hash(batch_texts[local_idx])
                                self._embedding_cache[text_hash] = result.copy()

                    logger.debug(
                        f"Generated {len(batch_texts)} embeddings in batch: "
                        f"{total_tokens} tokens, ${cost:.6f}, {duration:.3f}s"
                    )

                except BudgetExceededError:
                    # Budget exceeded - mark remaining batches as failed
                    logger.warning(
                        f"Budget exceeded during batch processing. "
                        f"Marking {len(batch_indices)} items as failed."
                    )
                    for idx in batch_indices:
                        results[idx] = None
                    # Stop processing remaining batches
                    break
                except Exception as e:
                    duration = time.time() - start_time
                    openai_embeddings_total.labels(model=self.model, status="error").inc()
                    openai_embedding_duration_seconds.labels(model=self.model).observe(duration)
                    logger.error(f"Error generating batch embeddings: {e}", exc_info=True)
                    # Mark batch as failed
                    for idx in batch_indices:
                        results[idx] = None

        return results

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        cache_size = len(self._embedding_cache)
        self._embedding_cache.clear()
        logger.info(f"Cleared embedding cache ({cache_size} entries)")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cache_size": len(self._embedding_cache),
            "model": self.model,
            "vector_size": self.vector_size,
        }

    def get_budget_stats(self) -> dict[str, Any]:
        """Get budget statistics.

        Returns:
            Dictionary with budget statistics
        """
        current_spending = self._get_current_daily_spending()
        stats = {
            "daily_budget_usd": self.daily_budget,
            "current_daily_spending_usd": current_spending,
            "budget_enabled": self.daily_budget is not None,
        }

        if self.daily_budget is not None:
            stats["budget_remaining_usd"] = max(0.0, self.daily_budget - current_spending)
            stats["budget_utilization_percent"] = (
                (current_spending / self.daily_budget * 100) if self.daily_budget > 0 else 0.0
            )

        return stats


# Global instance
embedding_service = EmbeddingService()
