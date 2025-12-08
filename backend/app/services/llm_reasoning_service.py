"""LLM reasoning service for analyzing anomalous log entries."""

import json
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

    TODO: Migrate prompts to Langfuse for centralized management
    - Prompts to migrate:
      * analyze_anomaly (line ~63)
      * detect_anomaly (line ~174)
      * analyze_anomaly_with_root_cause (line ~289)
    - Benefits: Non-technical team members can edit prompts, version control, A/B testing
    - Estimated effort: 4-6 hours
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

            # Build prompt with enhanced root cause analysis
            prompt = f"""You are a log analysis expert. Analyze the following log entry and provide a comprehensive root cause analysis.

Log Entry:
- Level: {log_level or "N/A"}
- Service: {log_service or "N/A"}
- Message: {log_message}
{context_text}

Provide a detailed analysis that includes:
1. **Anomaly Explanation**: What makes this log entry unusual compared to normal patterns (2-3 sentences)
2. **Root Cause Hypotheses**: List 2-3 most likely root causes with brief explanations
3. **Impact Assessment**: Potential impact on system/service operations
4. **Remediation Steps**: Specific actionable steps to investigate and resolve the issue

Be specific, technical, and actionable. Focus on identifying the underlying cause rather than just describing symptoms."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert log analyst specializing in identifying anomalies and unusual patterns in system logs.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,  # Increased for root cause analysis
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

    def analyze_anomaly_with_root_cause(
        self,
        log_message: str,
        log_level: str | None = None,
        log_service: str | None = None,
        context_logs: list[dict[str, Any]] | None = None,
        cluster_info: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Analyze anomaly with structured root cause analysis.

        Enhanced version that returns structured output with root causes and remediation steps.

        Args:
            log_message: The log message to analyze
            log_level: Optional log level (INFO, ERROR, etc.)
            log_service: Optional service name
            context_logs: Optional list of similar/normal logs for context
            cluster_info: Optional cluster information from clustering_service.get_cluster_info()

        Returns:
            Dictionary with:
            - explanation: Explanation string
            - root_causes: List of root cause hypotheses
            - remediation_steps: List of remediation actions
            - severity: Severity level (LOW/MEDIUM/HIGH/CRITICAL)
            Or None if analysis failed
        """
        if not self.client:
            logger.warning("OpenAI client not initialized. Skipping root cause analysis.")
            return None

        try:
            # Build context from similar logs if provided
            context_text = ""
            if context_logs:
                context_text = "\n\nSimilar normal logs for context:\n"
                for i, log in enumerate(context_logs[:5], 1):  # Limit to 5 context logs
                    context_text += f"{i}. [{log.get('level', 'N/A')}] {log.get('message', '')}\n"

            # Build cluster context if provided
            cluster_context_text = ""
            if cluster_info:
                cluster_context_text = f"""

Cluster Context:
- Cluster ID: {cluster_info.get("cluster_id", "N/A")}
- Cluster Size: {cluster_info.get("cluster_size", "N/A")}
- This log is an outlier compared to {cluster_info.get("cluster_size", 0)} similar normal logs.
- Sample normal logs from cluster:
"""
                sample_logs = cluster_info.get("sample_logs", [])[:3]
                for i, log in enumerate(sample_logs, 1):
                    cluster_context_text += (
                        f"  {i}. [{log.get('level', 'N/A')}] {log.get('message', '')[:100]}...\n"
                    )

            # Build enhanced prompt
            prompt = f"""You are a senior log analysis expert specializing in root cause analysis. Analyze the following log entry and provide structured analysis.

Log Entry:
- Level: {log_level or "N/A"}
- Service: {log_service or "N/A"}
- Message: {log_message}
{context_text}{cluster_context_text}

Respond in JSON format with the following structure:
{{
    "explanation": "Detailed explanation (3-4 sentences) of why this log is anomalous",
    "root_causes": [
        {{"hypothesis": "Root cause 1", "confidence": 0.0-1.0, "description": "Brief explanation"}},
        {{"hypothesis": "Root cause 2", "confidence": 0.0-1.0, "description": "Brief explanation"}}
    ],
    "remediation_steps": [
        {{"step": "Action 1", "priority": "HIGH/MEDIUM/LOW", "description": "What to do"}},
        {{"step": "Action 2", "priority": "HIGH/MEDIUM/LOW", "description": "What to do"}}
    ],
    "severity": "LOW/MEDIUM/HIGH/CRITICAL",
    "severity_reason": "Why this severity level"
}}

Focus on:
1. Specific technical root causes (not generic issues)
2. Actionable remediation steps
3. Accurate severity assessment based on operational impact"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert log analyst. Always respond with valid JSON only, no additional text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=800,
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            result_json = json.loads(response.choices[0].message.content)

            # Validate and structure the response
            result = {
                "explanation": result_json.get("explanation", "No explanation provided"),
                "root_causes": result_json.get("root_causes", []),
                "remediation_steps": result_json.get("remediation_steps", []),
                "severity": result_json.get("severity", "MEDIUM"),
                "severity_reason": result_json.get("severity_reason", "No reason provided"),
            }

            logger.debug(
                f"Generated root cause analysis: severity={result['severity']}, "
                f"root_causes={len(result['root_causes'])}"
            )

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response for root cause analysis: {e}")
            # Fallback to regular analysis
            explanation = self.analyze_anomaly(
                log_message=log_message,
                log_level=log_level,
                log_service=log_service,
                context_logs=context_logs,
            )
            if explanation:
                return {
                    "explanation": explanation,
                    "root_causes": [],
                    "remediation_steps": [],
                    "severity": "MEDIUM",
                    "severity_reason": "Analysis completed but structured parsing failed",
                }
            return None
        except RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded for root cause analysis: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in root cause analysis: {e}", exc_info=True)
            return None


# Global instance
llm_reasoning_service = LLMReasoningService()
