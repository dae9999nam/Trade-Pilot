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

export type UserProfile = {
  id: number;
  username: string;
  email: string;
  role: "user" | "admin";
};

export type LoginResponse = {
  csrf_token: string;
  token_type: "cookie";
  user: UserProfile;
};

export type ProfileUpdateRequest = {
  current_password: string;
  email?: string;
  new_password?: string;
};

export type TradingSafetyUserSettings = {
  max_order_krw: number;
  max_position_krw: number;
  min_decision_confidence: number;
  require_manual_approval: boolean;
  live_trading_opt_in: boolean;
};

export type TradingSafetySystemSettings = {
  broker_mode: string;
  auto_execute: boolean;
  system_live_trading_enabled: boolean;
  effective_live_trading_enabled: boolean;
  max_order_krw_cap: number;
  max_position_krw_cap: number;
  min_decision_confidence_floor: number;
  controlled_by_system: string[];
};

export type TradingSafetySettings = {
  user: TradingSafetyUserSettings;
  system: TradingSafetySystemSettings;
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
export type OrderStatus =
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "SUBMITTING"
  | "SUBMITTED"
  | "PARTIALLY_FILLED"
  | "FILLED"
  | "REJECTED"
  | "SUBMISSION_FAILED"
  | "CANCELED";
export type AssistantIntent =
  | "assistant_workspace"
  | "trade_decision"
  | "portfolio_review"
  | "order_review"
  | "decision_history"
  | "web_research"
  | "system_status";
export type ArtifactType =
  | "metric_grid"
  | "table"
  | "line_chart"
  | "bar_chart"
  | "pie_chart"
  | "web_tab"
  | "decision_card";

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

export type AssistantQueryRequest = {
  query: string;
  symbol?: string;
  quantity?: number;
  last_price?: number;
  max_position_krw?: number;
};

export type AssistantArtifact = {
  id: string;
  type: ArtifactType;
  title: string;
  description: string | null;
  data: Record<string, unknown>;
};

export type AssistantQueryResponse = {
  answer: string;
  intent: AssistantIntent;
  artifacts: AssistantArtifact[];
  suggested_actions: string[];
  decision: DecisionResponse | null;
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
  status: OrderStatus | string;
  broker_order_id: string | null;
  message: string | null;
  approved_at: string | null;
  submitted_at: string | null;
  filled_at: string | null;
  rejected_at: string | null;
  failed_at: string | null;
  canceled_at: string | null;
  last_status_at: string | null;
  submission_attempts: number;
  can_approve: boolean;
  can_cancel: boolean;
  is_terminal: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type OrderEventView = {
  id: number;
  order_id: number;
  from_status: string | null;
  to_status: string;
  event_type: string;
  message: string | null;
  broker_order_id: string | null;
  event_payload: Record<string, unknown> | null;
  created_at: string;
};

export type PositionView = {
  symbol: string;
  quantity: number;
  avg_price: MoneyValue;
  market_price: MoneyValue;
};

export class ApiClient {
  async register(email: string, password: string): Promise<LoginResponse> {
    return this.post("/api/auth/register", { email, password });
  }

  async login(username: string, password: string): Promise<LoginResponse> {
    return this.post("/api/auth/login", { username, password });
  }

  async logout(): Promise<{ ok: boolean }> {
    return this.post("/api/auth/logout", {});
  }

  async me(): Promise<UserProfile> {
    return this.get("/api/auth/me");
  }

  async updateProfile(payload: ProfileUpdateRequest): Promise<UserProfile> {
    return this.patch("/api/auth/me", payload);
  }

  async tradingSafety(): Promise<TradingSafetySettings> {
    return this.get("/api/settings/trading-safety");
  }

  async updateTradingSafety(payload: TradingSafetyUserSettings): Promise<TradingSafetySettings> {
    return this.patch("/api/settings/trading-safety", payload);
  }

  async config(): Promise<PublicConfig> {
    return this.get("/api/config");
  }

  async runDecision(payload: DecisionRequest): Promise<DecisionResponse> {
    return this.post("/api/decisions/run", payload);
  }

  async queryAssistant(payload: AssistantQueryRequest): Promise<AssistantQueryResponse> {
    return this.post("/api/assistant/query", payload);
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

  async cancelOrder(orderId: number): Promise<OrderView> {
    return this.post(`/api/orders/${orderId}/cancel`, {});
  }

  async refreshOrder(orderId: number): Promise<OrderView> {
    return this.post(`/api/orders/${orderId}/refresh`, {});
  }

  async orderEvents(orderId: number): Promise<OrderEventView[]> {
    return this.get(`/api/orders/${orderId}/events`);
  }

  async positions(): Promise<PositionView[]> {
    return this.get("/api/positions");
  }

  private async get<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: "include"
    });
    return this.parse<T>(response);
  }

  private async post<T>(path: string, payload: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...csrfHeader()
      },
      body: JSON.stringify(payload)
    });
    return this.parse<T>(response);
  }

  private async patch<T>(path: string, payload: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...csrfHeader()
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

function csrfHeader(): HeadersInit {
  const token = readCookie("trade_pilot_csrf");
  return token ? { "X-CSRF-Token": token } : {};
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  const cookie = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}
