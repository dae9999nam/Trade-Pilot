const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type MoneyValue = number | string;

export type PublicConfig = {
  app_env: string;
  broker_mode: string;
  auto_execute: boolean;
  live_trading_enabled: boolean;
  openai_model: string;
  max_order_krw: number;
  max_position_krw: number;
  min_decision_confidence: number;
};

export type AgentVerdict = {
  role: string;
  verdict: "bullish" | "bearish" | "neutral" | "block";
  confidence: number;
  reasons: string[];
  risk_notes: string[];
};

export type DecisionRequest = {
  symbol: string;
  quantity: number;
  last_price?: number;
};

export type RiskStatus = "APPROVED" | "REJECTED" | "NEEDS_APPROVAL";

export type DecisionResponse = {
  id: number;
  risk_status: RiskStatus;
  risk_reasons: string[];
  order_id: number | null;
  decision: {
    symbol: string;
    action: "BUY" | "SELL" | "HOLD";
    quantity: number;
    order_type: "MARKET" | "LIMIT";
    limit_price: MoneyValue | null;
    confidence: number;
    thesis: string;
    stop_loss_pct: number | null;
    take_profit_pct: number | null;
    require_human_approval: boolean;
    agent_votes: AgentVerdict[];
  };
};

export type DecisionListItem = {
  id: number;
  symbol: string;
  action: string;
  quantity: number;
  confidence: number;
  risk_status: RiskStatus;
  risk_reasons: string[];
  created_at: string;
};

export type OrderView = {
  id: number;
  mode: string;
  symbol: string;
  side: string;
  quantity: number;
  order_type: string;
  limit_price: MoneyValue | null;
  status: string;
  broker_order_id: string | null;
  message: string | null;
};

export type PositionView = {
  symbol: string;
  quantity: number;
  avg_price: MoneyValue;
  market_price: MoneyValue;
};

export class ApiClient {
  async config(): Promise<PublicConfig> {
    return this.get("/api/config");
  }

  async runDecision(payload: DecisionRequest): Promise<DecisionResponse> {
    return this.post("/api/decisions/run", payload);
  }

  async decisions(): Promise<DecisionListItem[]> {
    return this.get("/api/decisions");
  }

  async orders(): Promise<OrderView[]> {
    return this.get("/api/orders");
  }

  async approveOrder(orderId: number): Promise<OrderView> {
    return this.post(`/api/orders/${orderId}/approve`, {});
  }

  async positions(): Promise<PositionView[]> {
    return this.get("/api/positions");
  }

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`);
    return this.parse<T>(response);
  }

  private async post<T>(path: string, payload: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
    return this.parse<T>(response);
  }

  private async parse<T>(response: Response): Promise<T> {
    if (response.ok) {
      return response.json() as Promise<T>;
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      throw new Error(payload.detail ?? `HTTP ${response.status}`);
    }

    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
}
