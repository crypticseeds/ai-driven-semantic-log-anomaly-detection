"""Agent executor service for root cause analysis using LangChain."""

import logging
from typing import Any

from langchain.agents.factory import create_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.services.agent_tools import get_agent_tools

logger = logging.getLogger(__name__)


class AgentExecutorService:
    """Service for executing LangChain agents with root cause analysis capabilities."""

    def __init__(self):
        """Initialize agent executor service."""
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured. Agent executor will not work.")
            self.llm = None
            self.executor = None
            return

        try:
            # Initialize LLM
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",  # Cost-effective model
                temperature=0.3,  # Lower temperature for more consistent reasoning
                api_key=settings.openai_api_key,
            )

            # Get tools
            tools = get_agent_tools()

            # Create system prompt for root cause analysis
            system_prompt = """You are an expert log analysis agent specializing in root cause analysis and anomaly detection.

Your role is to:
1. Analyze log entries to identify anomalies and issues
2. Perform root cause analysis to determine why problems occurred
3. Search and summarize logs to understand patterns and trends
4. Provide actionable insights and remediation steps

When analyzing anomalies:
- Use the analyze_anomaly_tool or analyze_anomaly_with_cluster_context for detailed analysis
- Use detect_anomaly_tool to validate if logs are truly anomalous
- Use search_logs to find related logs and patterns
- Use summarize_range to understand trends over time periods

Always provide:
- Clear explanations of what the issue is
- Root cause hypotheses with confidence levels
- Prioritized remediation steps
- Severity assessment

Be thorough, technical, and actionable in your analysis."""

            # Create agent using new LangChain 1.x API
            # create_agent returns a CompiledStateGraph directly
            self.executor = create_agent(
                model=self.llm,
                tools=tools,
                system_prompt=system_prompt,
                debug=True,  # Enable debug mode for verbose output
            )

            logger.info("Agent executor initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize agent executor: {e}", exc_info=True)
            self.llm = None
            self.executor = None

    def analyze_root_cause(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute agent to perform root cause analysis.

        Args:
            query: Natural language query describing what to analyze
            context: Optional context dictionary with additional information

        Returns:
            Dictionary with agent response and analysis results
        """
        if not self.executor:
            return {
                "error": "Agent executor not initialized. Check OpenAI API key configuration.",
                "response": None,
            }

        try:
            # Build input with context if provided
            input_text = query
            if context:
                context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
                input_text = f"{query}\n\nContext:\n{context_str}"

            # Execute agent using new LangChain 1.x API
            # The new API expects messages in the input
            result = self.executor.invoke({"messages": [HumanMessage(content=input_text)]})

            # Extract response from the new format
            # In LangChain 1.x, the response is in messages format
            output = ""
            if "messages" in result:
                # Get the last AI message
                for msg in reversed(result["messages"]):
                    if hasattr(msg, "content") and msg.content:
                        output = msg.content
                        break
                    elif isinstance(msg, dict) and "content" in msg:
                        output = msg["content"]
                        break

            return {
                "response": output or str(result),
                "intermediate_steps": result.get("intermediate_steps", []),
                "query": query,
            }

        except Exception as e:
            logger.error(f"Error executing agent: {e}", exc_info=True)
            return {
                "error": str(e),
                "response": None,
                "query": query,
            }

    def is_available(self) -> bool:
        """Check if agent executor is available.

        Returns:
            True if agent executor is initialized and ready
        """
        return self.executor is not None


# Global instance
agent_executor_service = AgentExecutorService()
