import json
from decimal import Decimal
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.schemas import AgentVerdict, DecisionRequest, MarketSnapshot, TradeDecisionPayload
from app.services.skill_catalog import load_skill_catalog


class LLMTradeDecisionPayload(BaseModel):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    quantity: int = Field(ge=0)
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: float | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    thesis: str
    stop_loss_pct: float | None = Field(default=None, ge=0, le=100)
    take_profit_pct: float | None = Field(default=None, ge=0, le=100)
    require_human_approval: bool
    agent_votes: list[AgentVerdict]


class AgentOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def llm_available(self) -> bool:
        return bool(self.settings.openai_api_key)

    def _llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.settings.openai_model,
            temperature=0,
            api_key=self.settings.openai_api_key,
        )

    def _context(self, request: DecisionRequest, snapshot: MarketSnapshot) -> str:
        return json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "snapshot": snapshot.model_dump(mode="json"),
                "limits": {
                    "max_order_krw": self.settings.max_order_krw,
                    "max_position_krw": request.max_position_krw or self.settings.max_position_krw,
                    "min_decision_confidence": self.settings.min_decision_confidence,
                    "auto_execute": self.settings.auto_execute,
                    "broker_mode": self.settings.broker_mode,
                },
            },
            ensure_ascii=True,
        )

    def _skills(self) -> str:
        return load_skill_catalog()

    def _skill_system_prompt(self) -> str:
        return (
            "You have access to a SKILLS catalog that describes this trading system's "
            "available APIs, services, variables, parameters, and safety rules. "
            "Do not reduce the request to one intent label. Your objective is to fully "
            "answer or solve the user's trading-related request within the current task. "
            "Break the request into the skills needed to solve it, select every relevant "
            "existing skill card, and use those skill cards as ground truth for endpoint "
            "names, field names, enum values, required parameters, broker behavior, artifact "
            "expectations, and safety constraints. If a required capability is not described "
            "by SKILLS, explicitly state the missing skill or integration instead of inventing "
            "an API or parameter. If required information is missing, prefer a conservative "
            "HOLD decision or set require_human_approval=true rather than guessing. Never "
            "bypass RiskManager, human approval requirements, or live-trading environment gates."
        )

    def _fallback_decision(
        self, request: DecisionRequest, snapshot: MarketSnapshot
    ) -> TradeDecisionPayload:
        vote = AgentVerdict(
            role="supervisor",
            verdict="neutral",
            confidence=0.0,
            reasons=["OPENAI_API_KEY is not configured."],
            risk_notes=["Paper mode fallback returned HOLD."],
        )
        return TradeDecisionPayload(
            symbol=request.symbol.upper(),
            action="HOLD",
            quantity=0,
            order_type="LIMIT",
            limit_price=Decimal(snapshot.price),
            confidence=0.0,
            thesis="No model call was made because OPENAI_API_KEY is missing.",
            stop_loss_pct=None,
            take_profit_pct=None,
            require_human_approval=True,
            agent_votes=[vote],
        )

    def run(self, request: DecisionRequest, snapshot: MarketSnapshot) -> TradeDecisionPayload:
        if not self.llm_available:
            return self._fallback_decision(request, snapshot)

        context = self._context(request, snapshot)
        skills = self._skills()
        votes = [
            self._run_specialist(
                role="market_analyst",
                instruction="Assess only market direction, quote quality, and immediate signal strength.",
                context=context,
                skills=skills,
            ),
            self._run_specialist(
                role="risk_analyst",
                instruction="Assess sizing, downside, stop logic, and reasons to block the trade.",
                context=context,
                skills=skills,
            ),
            self._run_specialist(
                role="portfolio_analyst",
                instruction="Assess exposure and whether the requested quantity is coherent.",
                context=context,
                skills=skills,
            ),
            self._run_specialist(
                role="execution_analyst",
                instruction="Assess order type, limit price, and whether execution should wait.",
                context=context,
                skills=skills,
            ),
        ]

        supervisor = self._llm().with_structured_output(LLMTradeDecisionPayload)
        result = supervisor.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a cautious trading supervisor. You do not give financial advice. "
                        "Return one structured decision for an automated trading system. "
                        "Prefer HOLD when evidence is thin, confidence is weak, or risk is unclear. "
                        "Use BUY or SELL only when specialist votes and limits justify it. "
                        "Never bypass human approval for unusual risk. "
                        f"{self._skill_system_prompt()}"
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "context": json.loads(context),
                            "skills": skills,
                            "specialist_votes": [vote.model_dump(mode="json") for vote in votes],
                        },
                        ensure_ascii=True,
                    )
                ),
            ]
        )
        return TradeDecisionPayload(
            symbol=request.symbol.upper(),
            action=result.action,
            quantity=result.quantity,
            order_type=result.order_type,
            limit_price=Decimal(str(result.limit_price)) if result.limit_price is not None else None,
            confidence=result.confidence,
            thesis=result.thesis,
            stop_loss_pct=result.stop_loss_pct,
            take_profit_pct=result.take_profit_pct,
            require_human_approval=result.require_human_approval,
            agent_votes=votes,
        )

    def _run_specialist(
        self,
        role: str,
        instruction: str,
        context: str,
        skills: str,
    ) -> AgentVerdict:
        agent = self._llm().with_structured_output(AgentVerdict)
        result = agent.invoke(
            [
                SystemMessage(
                    content=(
                        f"You are {role}. {instruction} "
                        "Return compact reasons. Use verdict block when the trade should not proceed. "
                        f"{self._skill_system_prompt()}"
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "context": json.loads(context),
                            "skills": skills,
                        },
                        ensure_ascii=True,
                    )
                ),
            ]
        )
        result.role = role
        return result
