import json
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.schemas import AgentVerdict, DecisionRequest, MarketSnapshot, TradeDecisionPayload


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
        votes = [
            self._run_specialist(
                role="market_analyst",
                instruction="Assess only market direction, quote quality, and immediate signal strength.",
                context=context,
            ),
            self._run_specialist(
                role="risk_analyst",
                instruction="Assess sizing, downside, stop logic, and reasons to block the trade.",
                context=context,
            ),
            self._run_specialist(
                role="portfolio_analyst",
                instruction="Assess exposure and whether the requested quantity is coherent.",
                context=context,
            ),
            self._run_specialist(
                role="execution_analyst",
                instruction="Assess order type, limit price, and whether execution should wait.",
                context=context,
            ),
        ]

        supervisor = self._llm().with_structured_output(TradeDecisionPayload)
        result = supervisor.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a cautious trading supervisor. You do not give financial advice. "
                        "Return one structured decision for an automated trading system. "
                        "Prefer HOLD when evidence is thin, confidence is weak, or risk is unclear. "
                        "Use BUY or SELL only when specialist votes and limits justify it. "
                        "Never bypass human approval for unusual risk."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "context": json.loads(context),
                            "specialist_votes": [vote.model_dump(mode="json") for vote in votes],
                        },
                        ensure_ascii=True,
                    )
                ),
            ]
        )
        result.symbol = request.symbol.upper()
        result.agent_votes = votes
        return result

    def _run_specialist(self, role: str, instruction: str, context: str) -> AgentVerdict:
        agent = self._llm().with_structured_output(AgentVerdict)
        result = agent.invoke(
            [
                SystemMessage(
                    content=(
                        f"You are {role}. {instruction} "
                        "Return compact reasons. Use verdict block when the trade should not proceed."
                    )
                ),
                HumanMessage(content=context),
            ]
        )
        result.role = role
        return result

