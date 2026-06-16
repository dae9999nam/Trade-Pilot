import json
import re
from decimal import Decimal
from hashlib import sha256
from typing import Literal
from urllib.parse import quote_plus

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.base import Broker
from app.core.config import Settings
from app.market.data import MarketDataService
from app.models import Order, Position, TradeDecision
from app.schemas import (
    AssistantArtifact,
    AssistantQueryRequest,
    AssistantQueryResponse,
    DecisionRequest,
    DecisionResponse,
)
from app.services.skill_catalog import load_skill_catalog
from app.services.trading_engine import TradingEngine


WorkspaceCapability = Literal[
    "trade_decision",
    "portfolio_review",
    "order_review",
    "decision_history",
    "web_research",
    "system_status",
]


class AssistantWorkspacePlan(BaseModel):
    objective: str = Field(
        description="The complete user-facing goal to answer or solve, not a single intent label."
    )
    workspace_capabilities: list[WorkspaceCapability] = Field(
        default_factory=list,
        description="Every connected workspace capability needed to answer the request.",
    )
    selected_skills: list[str] = Field(
        default_factory=list,
        description="Existing skill card filenames selected from the SKILLS catalog.",
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Capabilities or skill cards needed but not currently available.",
    )
    missing_skill_explanation: str = ""
    answer_strategy: str = ""


class AssistantWorkspace:
    def __init__(self, db: Session, broker: Broker, settings: Settings, user_id: int) -> None:
        self.db = db
        self.broker = broker
        self.settings = settings
        self.user_id = user_id

    def run(self, request: AssistantQueryRequest) -> AssistantQueryResponse:
        query = request.query.strip()
        plan = self._plan_request(request)
        capabilities = self._normalize_capabilities(plan.workspace_capabilities)

        responses: list[AssistantQueryResponse] = []
        decision: DecisionResponse | None = None
        artifacts = [self._skill_coverage_artifact(plan, capabilities)]
        suggested_actions: list[str] = []

        for capability in capabilities:
            response = self._run_capability(capability, request)
            responses.append(response)
            artifacts.extend(response.artifacts)
            suggested_actions.extend(response.suggested_actions)
            if response.decision is not None and decision is None:
                decision = response.decision

        if not responses:
            suggested_actions.append("Add the missing skill or clarify the request with available system data.")

        return AssistantQueryResponse(
            answer=self._compose_workspace_answer(query, plan, responses),
            intent="assistant_workspace",
            artifacts=artifacts,
            suggested_actions=self._dedupe(suggested_actions),
            decision=decision,
        )

    def _llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.settings.openai_model,
            temperature=0,
            api_key=self.settings.openai_api_key,
        )

    def _plan_request(self, request: AssistantQueryRequest) -> AssistantWorkspacePlan:
        if self.settings.openai_api_key:
            try:
                return self._llm_plan_request(request)
            except Exception as exc:
                fallback = self._fallback_plan_request(request)
                fallback.missing_skills.append("assistant_workspace_planner_recovery")
                fallback.missing_skill_explanation = (
                    f"LLM planner failed, so the workspace used deterministic skill matching: {exc}"
                )
                return fallback
        return self._fallback_plan_request(request)

    def _llm_plan_request(self, request: AssistantQueryRequest) -> AssistantWorkspacePlan:
        planner = self._llm().with_structured_output(AssistantWorkspacePlan)
        return planner.invoke(
            [
                SystemMessage(
                    content=(
                        "You are the Trade-pilot assistant workspace planner. Do not classify "
                        "the user's query into one intent. Your objective is to fully answer or "
                        "solve the user's question/request. Decompose the request into every "
                        "required task, inspect the SKILLS catalog, and select every existing "
                        "skill card needed to solve it. Then choose every connected workspace "
                        "capability needed from: trade_decision, portfolio_review, order_review, "
                        "decision_history, web_research, system_status. Use multiple capabilities "
                        "when the request requires them. If a required capability is not present "
                        "in SKILLS or the connected workspace capabilities, list it in "
                        "missing_skills and explain what would be needed. Never invent endpoints, "
                        "fields, enum values, broker modes, order statuses, or market data. "
                        "The web_research capability currently creates a browser-style research "
                        "tab only; if the user needs real web search ingestion or summarization, "
                        "mark a missing web-search provider skill."
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "user_query": request.query,
                            "request_context": request.model_dump(mode="json"),
                            "connected_workspace_capabilities": [
                                "trade_decision",
                                "portfolio_review",
                                "order_review",
                                "decision_history",
                                "web_research",
                                "system_status",
                            ],
                            "skills": load_skill_catalog(),
                        },
                        ensure_ascii=True,
                    )
                ),
            ]
        )

    def _fallback_plan_request(self, request: AssistantQueryRequest) -> AssistantWorkspacePlan:
        query = request.query.strip()
        normalized = query.lower()
        capabilities: list[WorkspaceCapability] = []
        selected_skills: list[str] = []
        missing_skills: list[str] = []

        if self._contains_any(normalized, ["web", "search", "google", "news", "뉴스", "검색", "리서치"]):
            capabilities.append("web_research")
            missing_skills.append("real_web_search_provider.md")
        if self._contains_any(normalized, ["portfolio", "position", "holding", "보유", "포트폴리오", "비중"]):
            capabilities.append("portfolio_review")
        if self._contains_any(normalized, ["order", "orders", "주문", "체결", "승인"]):
            capabilities.append("order_review")
        if self._contains_any(normalized, ["history", "decision history", "최근 판단", "히스토리", "이력"]):
            capabilities.append("decision_history")
        if self._contains_any(normalized, ["config", "health", "status", "broker", "설정", "상태", "모드"]):
            capabilities.append("system_status")
        if self._looks_like_trade_decision_request(query):
            capabilities.append("trade_decision")

        if not capabilities:
            missing_skills.append("general_request_resolution_skill.md")

        for capability in capabilities:
            selected_skills.extend(self._skill_names_for_capability(capability))

        return AssistantWorkspacePlan(
            objective=f"Answer or solve the full user request: {query}",
            workspace_capabilities=self._dedupe(capabilities),
            selected_skills=self._dedupe(selected_skills),
            missing_skills=self._dedupe(missing_skills),
            missing_skill_explanation=(
                "실제 웹 검색 수집/요약 skill은 아직 연결되어 있지 않습니다."
                if "real_web_search_provider.md" in missing_skills
                else (
                    "현재 SKILLS catalog만으로는 이 요청을 실행할 수 있는 구체 skill이 없습니다."
                    if missing_skills
                    else ""
                )
            ),
            answer_strategy="Use all matching connected capabilities; explain missing skills explicitly.",
        )

    def _run_capability(
        self,
        capability: WorkspaceCapability,
        request: AssistantQueryRequest,
    ) -> AssistantQueryResponse:
        query = request.query.strip()
        if capability == "trade_decision":
            return self._trade_decision_response(request)
        if capability == "portfolio_review":
            return self._portfolio_response(query)
        if capability == "order_review":
            return self._orders_response(query)
        if capability == "decision_history":
            return self._decision_history_response(query)
        if capability == "web_research":
            return self._web_research_response(query)
        return self._system_status_response(query)

    def _normalize_capabilities(
        self,
        capabilities: list[WorkspaceCapability],
    ) -> list[WorkspaceCapability]:
        order: list[WorkspaceCapability] = [
            "system_status",
            "portfolio_review",
            "order_review",
            "decision_history",
            "web_research",
            "trade_decision",
        ]
        selected = set(capabilities)
        return [capability for capability in order if capability in selected]

    def _trade_decision_response(self, request: AssistantQueryRequest) -> AssistantQueryResponse:
        symbol = (request.symbol or self._extract_symbol(request.query) or "A005930").upper()
        decision_request = DecisionRequest(
            symbol=symbol,
            quantity=request.quantity,
            max_position_krw=request.max_position_krw,
            last_price=request.last_price,
            notes=request.query,
        )
        snapshot = MarketDataService(self.broker).snapshot_for(decision_request)
        decision = TradingEngine(self.db, self.broker, self.settings, self.user_id).run_decision(
            decision_request,
            snapshot,
        )

        answer = (
            f"{symbol}에 대한 현재 결정은 {decision.decision.action}입니다. "
            f"신뢰도는 {decision.decision.confidence:.0%}, risk status는 "
            f"{decision.risk_status}입니다. {decision.decision.thesis}"
        )

        artifacts = [
            self._decision_card(decision),
            self._price_line_chart(symbol, snapshot.price),
            self._agent_vote_chart(decision),
            self._risk_table(decision),
        ]
        return AssistantQueryResponse(
            answer=answer,
            intent="trade_decision",
            artifacts=artifacts,
            suggested_actions=[
                "Ask for a portfolio-level exposure review",
                "Open recent decision history",
                "Review pending orders before approving execution",
            ],
            decision=decision,
        )

    def _portfolio_response(self, query: str) -> AssistantQueryResponse:
        positions = list(
            self.db.scalars(
                select(Position)
                .where(Position.user_id == self.user_id)
                .order_by(Position.symbol.asc())
            ).all()
        )
        rows = [
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": float(position.avg_price),
                "market_price": float(position.market_price),
                "market_value": float(Decimal(position.quantity) * position.market_price),
            }
            for position in positions
        ]
        total_value = sum(row["market_value"] for row in rows)
        answer = (
            f"현재 저장된 포지션은 {len(rows)}개이고 총 평가액은 "
            f"{total_value:,.0f} KRW입니다. 이 값은 앱 DB에 저장된 paper/live 상태 기준입니다."
        )
        return AssistantQueryResponse(
            answer=answer,
            intent="portfolio_review",
            artifacts=[
                AssistantArtifact(
                    id="portfolio-metrics",
                    type="metric_grid",
                    title="Portfolio summary",
                    data={
                        "items": [
                            {"label": "Positions", "value": len(rows)},
                            {"label": "Market value", "value": round(total_value)},
                            {"label": "Broker", "value": self.settings.broker_mode},
                            {"label": "Live trading", "value": self.settings.live_trading_enabled},
                        ]
                    },
                ),
                AssistantArtifact(
                    id="portfolio-table",
                    type="table",
                    title="Positions from database",
                    data={
                        "columns": ["symbol", "quantity", "avg_price", "market_price", "market_value"],
                        "rows": rows,
                    },
                ),
                AssistantArtifact(
                    id="portfolio-allocation",
                    type="pie_chart",
                    title="Allocation by market value",
                    data={"labelKey": "symbol", "valueKey": "market_value", "slices": rows},
                ),
            ],
            suggested_actions=["Run a decision for a specific symbol", "Review pending orders"],
        )

    def _orders_response(self, query: str) -> AssistantQueryResponse:
        orders = list(
            self.db.scalars(
                select(Order)
                .where(Order.user_id == self.user_id)
                .order_by(Order.created_at.desc())
                .limit(50)
            ).all()
        )
        rows = [
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "status": order.status,
                "broker_order_id": order.broker_order_id,
            }
            for order in orders
        ]
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

        return AssistantQueryResponse(
            answer=f"최근 주문 {len(rows)}건을 조회했습니다. 상태별 분포와 주문 테이블을 함께 표시합니다.",
            intent="order_review",
            artifacts=[
                AssistantArtifact(
                    id="order-status-bars",
                    type="bar_chart",
                    title="Order status distribution",
                    data={
                        "xKey": "status",
                        "yKey": "count",
                        "bars": [
                            {"status": status, "count": count}
                            for status, count in sorted(status_counts.items())
                        ],
                    },
                ),
                AssistantArtifact(
                    id="orders-table",
                    type="table",
                    title="Recent orders",
                    data={
                        "columns": [
                            "id",
                            "symbol",
                            "side",
                            "quantity",
                            "order_type",
                            "status",
                            "broker_order_id",
                        ],
                        "rows": rows,
                    },
                ),
            ],
            suggested_actions=["Approve a pending order from the Orders panel", "Run risk review"],
        )

    def _decision_history_response(self, query: str) -> AssistantQueryResponse:
        decisions = list(
            self.db.scalars(
                select(TradeDecision)
                .where(TradeDecision.user_id == self.user_id)
                .order_by(TradeDecision.created_at.desc())
                .limit(50)
            ).all()
        )
        rows = [
            {
                "id": decision.id,
                "symbol": decision.symbol,
                "action": decision.action,
                "quantity": decision.quantity,
                "confidence": decision.confidence,
                "risk_status": decision.risk_status,
                "created_at": decision.created_at.isoformat(),
            }
            for decision in decisions
        ]
        return AssistantQueryResponse(
            answer=f"최근 AI decision {len(rows)}건을 가져왔습니다.",
            intent="decision_history",
            artifacts=[
                AssistantArtifact(
                    id="decision-history-table",
                    type="table",
                    title="Recent AI decisions",
                    data={
                        "columns": [
                            "id",
                            "symbol",
                            "action",
                            "quantity",
                            "confidence",
                            "risk_status",
                            "created_at",
                        ],
                        "rows": rows,
                    },
                )
            ],
            suggested_actions=["Run a fresh decision with current market data"],
        )

    def _web_research_response(self, query: str) -> AssistantQueryResponse:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return AssistantQueryResponse(
            answer=(
                "현재 백엔드에는 실제 web search 수집기가 연결되어 있지 않습니다. "
                "대신 assistant workspace 안에 열 수 있는 research tab artifact를 만들었습니다."
            ),
            intent="web_research",
            artifacts=[
                AssistantArtifact(
                    id="web-search-tab",
                    type="web_tab",
                    title="Web research tab",
                    description="Open this tab to continue browser-based research.",
                    data={"url": url, "label": query},
                )
            ],
            suggested_actions=["Connect a real web-search provider skill", "Summarize pasted research notes"],
        )

    def _system_status_response(self, query: str) -> AssistantQueryResponse:
        return AssistantQueryResponse(
            answer=(
                f"Backend is configured for {self.settings.broker_mode} mode. "
                f"Auto execution is {self.settings.auto_execute}; live trading is "
                f"{self.settings.live_trading_enabled}."
            ),
            intent="system_status",
            artifacts=[
                AssistantArtifact(
                    id="system-config",
                    type="metric_grid",
                    title="System configuration",
                    data={
                        "items": [
                            {"label": "Broker", "value": self.settings.broker_mode},
                            {"label": "Auto execute", "value": self.settings.auto_execute},
                            {"label": "Live trading", "value": self.settings.live_trading_enabled},
                            {"label": "Model", "value": self.settings.openai_model},
                            {"label": "Max order KRW", "value": self.settings.max_order_krw},
                            {"label": "Position cap KRW", "value": self.settings.max_position_krw},
                        ]
                    },
                )
            ],
            suggested_actions=["Run a paper decision", "Review broker adapter mode"],
        )

    def _decision_card(self, decision: DecisionResponse) -> AssistantArtifact:
        return AssistantArtifact(
            id="decision-card",
            type="decision_card",
            title=f"{decision.decision.symbol} decision",
            data={
                "symbol": decision.decision.symbol,
                "action": decision.decision.action,
                "quantity": decision.decision.quantity,
                "confidence": decision.decision.confidence,
                "risk_status": decision.risk_status,
                "risk_reasons": decision.risk_reasons,
                "order_id": decision.order_id,
            },
        )

    def _price_line_chart(self, symbol: str, price: Decimal) -> AssistantArtifact:
        return AssistantArtifact(
            id="price-line-chart",
            type="line_chart",
            title=f"{symbol} synthetic price context",
            description="Paper-mode context generated from the current snapshot; not historical market data.",
            data={
                "xKey": "label",
                "yKeys": ["price"],
                "points": self._synthetic_price_points(symbol, price),
            },
        )

    def _agent_vote_chart(self, decision: DecisionResponse) -> AssistantArtifact:
        return AssistantArtifact(
            id="agent-vote-bars",
            type="bar_chart",
            title="Agent confidence",
            data={
                "xKey": "role",
                "yKey": "confidence",
                "bars": [
                    {
                        "role": vote.role,
                        "confidence": round(vote.confidence * 100, 2),
                        "verdict": vote.verdict,
                    }
                    for vote in decision.decision.agent_votes
                ],
            },
        )

    def _risk_table(self, decision: DecisionResponse) -> AssistantArtifact:
        return AssistantArtifact(
            id="risk-table",
            type="table",
            title="Risk result",
            data={
                "columns": ["status", "reason"],
                "rows": [
                    {"status": decision.risk_status, "reason": reason}
                    for reason in decision.risk_reasons
                ],
            },
        )

    def _synthetic_price_points(self, symbol: str, price: Decimal) -> list[dict[str, float | str]]:
        seed = int(sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)
        base = float(price)
        labels = ["T-5", "T-4", "T-3", "T-2", "T-1", "Now"]
        points: list[dict[str, float | str]] = []
        for index, label in enumerate(labels):
            offset = ((seed >> (index * 3)) % 11 - 5) / 100
            drift = (index - 4) * 0.004
            points.append({"label": label, "price": round(base * (1 + offset + drift), 2)})
        points[-1]["price"] = round(base, 2)
        return points

    def _skill_coverage_artifact(
        self,
        plan: AssistantWorkspacePlan,
        capabilities: list[WorkspaceCapability],
    ) -> AssistantArtifact:
        rows = [
            {"type": "selected_skill", "name": skill, "status": "available"}
            for skill in plan.selected_skills
        ]
        rows.extend(
            {"type": "workspace_capability", "name": capability, "status": "will_run"}
            for capability in capabilities
        )
        rows.extend(
            {"type": "missing_skill", "name": skill, "status": "needed"}
            for skill in plan.missing_skills
        )
        return AssistantArtifact(
            id="skill-coverage",
            type="table",
            title="Skill coverage plan",
            description=plan.objective,
            data={
                "columns": ["type", "name", "status"],
                "rows": rows,
            },
        )

    def _compose_workspace_answer(
        self,
        query: str,
        plan: AssistantWorkspacePlan,
        responses: list[AssistantQueryResponse],
    ) -> str:
        sections = [
            f"요청 목표: {plan.objective}",
        ]
        if plan.selected_skills:
            sections.append(f"사용한 SKILLS: {', '.join(plan.selected_skills)}")
        if plan.missing_skills:
            missing = f"부족한 SKILLS: {', '.join(plan.missing_skills)}"
            if plan.missing_skill_explanation:
                missing = f"{missing}. {plan.missing_skill_explanation}"
            sections.append(missing)
        if plan.answer_strategy:
            sections.append(f"해결 전략: {plan.answer_strategy}")

        if responses:
            sections.append(
                "실행 결과:\n"
                + "\n\n".join(f"- {response.answer}" for response in responses)
            )
        else:
            sections.append(
                "현재 연결된 workspace capability로는 요청을 직접 실행하지 못했습니다. "
                "위의 missing skill을 추가하면 이 질문을 실제 시스템 작업으로 처리할 수 있습니다."
            )
        return "\n\n".join(sections)

    def _skill_names_for_capability(self, capability: WorkspaceCapability) -> list[str]:
        if capability == "trade_decision":
            return [
                "ai_trade_decision.md",
                "market_snapshot.md",
                "risk_guardrails.md",
                "broker_adapters.md",
            ]
        if capability == "portfolio_review":
            return ["portfolio_positions.md"]
        if capability == "order_review":
            return ["order_management.md", "risk_guardrails.md"]
        if capability == "decision_history":
            return ["decision_history.md"]
        if capability == "system_status":
            return ["system_status_and_config.md", "broker_adapters.md"]
        return []

    def _looks_like_trade_decision_request(self, query: str) -> bool:
        normalized = query.lower()
        return bool(self._extract_symbol(query)) or self._contains_any(
            normalized,
            [
                "buy",
                "sell",
                "hold",
                "trade",
                "decision",
                "agent review",
                "매수",
                "매도",
                "보유",
                "판단",
                "분석",
                "종목",
            ],
        )

    def _dedupe(self, values: list) -> list:
        seen = set()
        result = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _extract_symbol(self, query: str) -> str | None:
        match = re.search(r"\bA\d{6}\b|\b[A-Z]{2,8}\b", query.upper())
        return match.group(0) if match else None

    def _contains_any(self, text: str, needles: list[str]) -> bool:
        return any(needle in text for needle in needles)
