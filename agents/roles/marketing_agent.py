"""AICOS Marketing Agent: brand storyteller, content creator, and growth strategist."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agents.base import BaseAgent, TaskResult
from core.models import (
    AgentConfig,
    AgentRole,
    Message,
    Task,
    TaskStatus,
)

logger = logging.getLogger("aicos.agents.marketing")

MARKETING_SYSTEM_PROMPT = """\
You are the Head of Marketing at this AI-powered company. Your name is {name}.

You are a creative strategist who turns company capabilities into compelling stories \
that attract, engage, and convert the right audience. You combine data-driven growth \
tactics with genuine brand storytelling.

Core responsibilities:
- Create high-quality content: blog posts, social media updates, email campaigns, and landing pages.
- Develop and execute marketing campaigns aligned with sales targets and company strategy.
- Manage SEO strategy to drive organic traffic and domain authority.
- Analyze engagement metrics and optimize campaigns based on performance data.
- Build and maintain the company's brand voice and visual identity.
- Generate marketing-qualified leads (MQLs) and hand them off to Sales.

Marketing philosophy:
- Content is king, but distribution is the kingdom. Great content that nobody sees is worthless.
- Every piece of content should educate, entertain, or inspire — ideally all three.
- Data informs creativity. You A/B test, measure, and iterate constantly.
- Brand consistency across channels builds trust. Voice, tone, and visuals should be coherent.
- You market to people, not personas. Empathy and authenticity beat corporate polish.

Content strategy:
- Top of funnel: thought leadership, educational blog posts, social media engagement.
- Middle of funnel: case studies, comparison guides, webinars, email nurture sequences.
- Bottom of funnel: product demos, testimonials, ROI calculators, free trials.
- You match content format to channel: long-form for blog/SEO, snappy for social, visual for ads.

Communication style:
- You write in a clear, engaging voice that reflects the brand personality.
- Headlines are hook-driven and honest — no clickbait.
- You present campaign results with context: what worked, what didn't, and what you'd change.
- You collaborate openly with Sales on messaging alignment and lead quality feedback.

You work closely with Sales on lead generation, with the CEO on brand strategy, and \
with Support on gathering customer stories and testimonials.
"""

DEFAULT_MARKETING_TOOLS = [
    "create_content",
    "schedule_post",
    "analyze_engagement",
    "run_campaign",
    "optimize_seo",
    "generate_lead_magnet",
    "create_email_campaign",
]

DEFAULT_MARKETING_KPIS = {
    "content_pieces": 0.0,
    "engagement_rate": 0.0,
    "website_traffic": 0.0,
    "leads_generated": 0.0,
}


class MarketingAgent(BaseAgent):
    """Marketing agent — content creation, campaigns, SEO, and brand growth."""

    def __init__(self, config: AgentConfig, comm_bus, memory_manager, anthropic_client=None) -> None:
        if not config.system_prompt:
            config.system_prompt = MARKETING_SYSTEM_PROMPT.format(name=config.name)
        if not config.tools:
            config.tools = list(DEFAULT_MARKETING_TOOLS)

        super().__init__(config, comm_bus, memory_manager, anthropic_client)

        for kpi_name, kpi_val in DEFAULT_MARKETING_KPIS.items():
            self.kpis.setdefault(kpi_name, kpi_val)

    async def act(self, task: Task) -> TaskResult:
        self.status = "working"
        self.current_task = task
        task.status = TaskStatus.IN_PROGRESS

        try:
            task_type = self._classify_task(task)

            if task_type == "content":
                return await self._handle_content_creation(task)
            elif task_type == "campaign":
                return await self._handle_campaign(task)
            elif task_type == "seo":
                return await self._handle_seo(task)
            elif task_type == "social":
                return await self._handle_social_media(task)
            else:
                return await self._handle_general_marketing(task)

        except Exception as exc:
            logger.exception("Marketing %s failed task %s", self.name, task.id)
            task.status = TaskStatus.FAILED
            task.result = str(exc)
            return TaskResult(task_id=task.id, success=False, error=str(exc))
        finally:
            self.current_task = None
            self.status = "idle"

    def _classify_task(self, task: Task) -> str:
        combined = f"{task.title} {task.description}".lower()
        if any(kw in combined for kw in ("blog", "article", "content", "write", "copy", "whitepaper")):
            return "content"
        if any(kw in combined for kw in ("campaign", "launch", "promotion", "ad ", "ads ", "advertising")):
            return "campaign"
        if any(kw in combined for kw in ("seo", "keyword", "search engine", "organic", "ranking")):
            return "seo"
        if any(kw in combined for kw in ("social", "twitter", "linkedin", "facebook", "instagram", "post")):
            return "social"
        return "general"

    async def _handle_content_creation(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Marketing, create content:\n\n"
            f"Request: {task.title}\n"
            f"Brief: {task.description}\n\n"
            f"Deliver:\n"
            f"1. A compelling headline with 2-3 alternatives.\n"
            f"2. The full content piece (well-structured, engaging, on-brand).\n"
            f"3. Meta description for SEO (under 160 characters).\n"
            f"4. Suggested distribution channels and timing.\n"
            f"5. Call-to-action aligned with our current funnel goals.\n"
            f"6. Internal linking opportunities if this is a blog post."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("content_pieces", self.kpis.get("content_pieces", 0) + 1)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_campaign(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Marketing, plan and execute a campaign:\n\n"
            f"Campaign brief: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Campaign objectives and success metrics.\n"
            f"2. Target audience segments.\n"
            f"3. Channel strategy (which channels, why, what content for each).\n"
            f"4. Creative direction and key messaging.\n"
            f"5. Budget allocation across channels.\n"
            f"6. Timeline with launch date and milestones.\n"
            f"7. A/B testing plan.\n"
            f"8. Post-campaign analysis framework."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_seo(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Marketing, optimize for search:\n\n"
            f"SEO task: {task.title}\n"
            f"Details: {task.description}\n\n"
            f"Provide:\n"
            f"1. Target keywords (primary, secondary, long-tail) with search intent.\n"
            f"2. Content optimization recommendations (title tags, headers, body copy).\n"
            f"3. Technical SEO checklist (page speed, mobile, schema markup).\n"
            f"4. Internal and external linking strategy.\n"
            f"5. Competitor analysis for target keywords.\n"
            f"6. Expected timeline to rank and traffic projections."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("website_traffic", self.kpis.get("website_traffic", 0) + 10)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_social_media(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Marketing, create social media content:\n\n"
            f"Request: {task.title}\n"
            f"Context: {task.description}\n\n"
            f"Provide:\n"
            f"1. Platform-specific posts (adapt tone and format for each channel).\n"
            f"2. Hashtag strategy.\n"
            f"3. Visual direction or image descriptions.\n"
            f"4. Optimal posting schedule based on audience activity.\n"
            f"5. Engagement strategy (comments, DMs, community interaction).\n"
            f"6. Performance metrics to track."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        self.track_kpi("engagement_rate", self.kpis.get("engagement_rate", 0) + 0.5)
        return TaskResult(task_id=task.id, success=True, output=output)

    async def _handle_general_marketing(self, task: Task) -> TaskResult:
        prompt = (
            f"As Head of Marketing, address this task:\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description}\n"
            f"Priority: {task.priority}\n\n"
            f"Apply your marketing expertise to deliver actionable results."
        )
        output = await self.think(prompt)
        task.status = TaskStatus.COMPLETED
        task.result = output
        task.completed_at = datetime.utcnow()
        return TaskResult(task_id=task.id, success=True, output=output)
