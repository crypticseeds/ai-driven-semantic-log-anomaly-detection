"""LLM reasoning service for analyzing anomalous log entries."""

import logging
from typing import Any

from openai import OpenAI, RateLimitError

from app.config import get_settings

logger = logging.getLogger(__name__)


class LLMReasoningService:
    """Service for using LLM to detect and explain anomalous log entries.

    This service uses OpenAI's chat completion API to:
    1. Detect anomalies (classify logs as anomalous or normal)
    2. Generate explanations for why log entries are considered anomalous
    """

    def __init__(self):
        """Initialize LLM reasoning service."""
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured. LLM reasoning will not work.")
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o-mini"  # Cost-effective model for reasoning

    def analyze_anomaly(
        self,
        log_message: str,
        log_level: str | None = None,
        log_service: str | None = None,
        context_logs: list[dict[str, Any]] | None = None,
    ) -> str | None:
        """Analyze why a log entry is anomalous using LLM reasoning.

        Args:
            log_message: The log message to analyze
            log_level: Optional log level (INFO, ERROR, etc.)
            log_service: Optional service name
            context_logs: Optional list of similar/normal logs for context

        Returns:
            Explanation string or None if analysis failed
        """
        if not self.client:
            logger.warning("OpenAI client not initialized. Skipping LLM reasoning.")
            return None

        try:
            # Build context from similar logs if provided
            context_text = ""
            if context_logs:
                context_text = "\n\nSimilar normal logs for context:\n"
                for i, log in enumerate(context_logs[:5], 1):  # Limit to 5 context logs
                    context_text += f"{i}. [{log.get('level', 'N/A')}] {log.get('message', '')}\n"

            # Build prompt
            prompt = f"""You are a log analysis expert. Analyze the following log entry and explain why it might be considered anomalous or unusual.

Log Entry:
- Level: {log_level or "N/A"}
- Service: {log_service or "N/A"}
- Message: {log_message}
{context_text}

Provide a concise explanation (2-3 sentences) of why this log entry is anomalous. Focus on:
1. What makes it unusual compared to normal patterns
2. Potential root causes or issues it might indicate
3. Why it doesn't fit into common log patterns

Be specific and technical. If the log seems normal, explain why it might still be flagged as an outlier."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert log analyst specializing in identifying anomalies and unusual patterns in system logs.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.3,  # Lower temperature for more consistent reasoning
            )

            reasoning = response.choices[0].message.content
            logger.debug(f"Generated LLM reasoning for log: {reasoning[:100]}...")
            return reasoning

        except RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded for LLM reasoning: {e}")
            return None
        except Exception as e:
            logger.error(f"Error generating LLM reasoning: {e}", exc_info=True)
            return None

    def analyze_anomalies_batch(
        self,
        anomalies: list[dict[str, Any]],
        max_analyses: int = 10,
    ) -> dict[str, str]:
        """Analyze multiple anomalies in batch.

        Args:
            anomalies: List of anomaly dictionaries with log_message, log_level, log_service
            max_analyses: Maximum number of analyses to perform (to limit API costs)

        Returns:
            Dictionary mapping anomaly identifier to reasoning string
        """
        if not self.client:
            return {}

        results = {}
        for i, anomaly in enumerate(anomalies[:max_analyses]):
            reasoning = self.analyze_anomaly(
                log_message=anomaly.get("log_message", ""),
                log_level=anomaly.get("log_level"),
                log_service=anomaly.get("log_service"),
                context_logs=anomaly.get("context_logs"),
            )
            if reasoning:
                # Use log_id or index as key
                key = anomaly.get("log_id") or str(i)
                results[key] = reasoning

        return results

    def detect_anomaly(
        self,
        log_message: str,
        log_level: str | None = None,
        log_service: str | None = None,
        context_logs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Detect if a log entry is anomalous using LLM classification.

        This method validates whether a log entry is truly anomalous by analyzing
        its semantic content and context. Used in the hybrid detection pipeline
        to validate high-scoring anomalies from statistical methods.

        Args:
            log_message: The log message to analyze
            log_level: Optional log level (INFO, ERROR, etc.)
            log_service: Optional service name
            context_logs: Optional list of similar/normal logs for context

        Returns:
            Dictionary with:
            - is_anomaly: Boolean indicating if log is anomalous
            - confidence: Float confidence score (0.0 to 1.0)
            - reasoning: Explanation string
            Or None if detection failed
        """
        if not self.client:
            logger.warning("OpenAI client not initialized. Skipping LLM detection.")
            return None

        try:
            # Build context from similar logs if provided
            context_text = ""
            if context_logs:
                context_text = "\n\nSimilar normal logs for context:\n"
                for i, log in enumerate(context_logs[:5], 1):  # Limit to 5 context logs
                    context_text += f"{i}. [{log.get('level', 'N/A')}] {log.get('message', '')}\n"

            # Build detection prompt
            prompt = f"""You are a log analysis expert. Analyze the following log entry and determine if it is anomalous.

Log Entry:
- Level: {log_level or "N/A"}
- Service: {log_service or "N/A"}
- Message: {log_message}
{context_text}

Respond in JSON format with the following structure:
{{
    "is_anomaly": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation (2-3 sentences) of why this log is or isn't anomalous"
}}

Consider:
1. Unusual patterns compared to normal logs
2. Error severity and frequency
3. Context and service behavior
4. Potential security or operational issues"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert log analyst. Always respond with valid JSON only, no additional text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.2,  # Lower temperature for more consistent classification
                response_format={"type": "json_object"},
            )

            import json

            result_json = json.loads(response.choices[0].message.content)
            is_anomaly = result_json.get("is_anomaly", False)
            confidence = float(result_json.get("confidence", 0.5))
            reasoning = result_json.get("reasoning", "No reasoning provided")

            logger.debug(f"LLM detection: is_anomaly={is_anomaly}, confidence={confidence:.2f}")

            return {
                "is_anomaly": is_anomaly,
                "confidence": confidence,
                "reasoning": reasoning,
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            return None
        except RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded for LLM detection: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in LLM anomaly detection: {e}", exc_info=True)
            return None


# Global instance
llm_reasoning_service = LLMReasoningService()
