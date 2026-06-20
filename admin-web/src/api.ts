const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type UserProfile = {
  id: number;
  username: string;
  email: string;
  role: "user" | "admin";
};

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

export type DecisionResponse = {
  id: number;
  risk_status: "APPROVED" | "REJECTED" | "NEEDS_APPROVAL";
  risk_reasons: string[];
  order_id: number | null;
  decision: {
    symbol: string;
    action: "BUY" | "SELL" | "HOLD";
    quantity: number;
    order_type: "MARKET" | "LIMIT";
    limit_price: number | null;
    confidence: number;
    thesis: string;
    stop_loss_pct: number | null;
    take_profit_pct: number | null;
    require_human_approval: boolean;
    agent_votes: AgentVerdict[];
  };
};

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

export type OrderCreate = {
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  limit_price?: number;
};

export type OrderView = {
  id: number;
  mode: string;
  symbol: string;
  side: string;
  quantity: number;
  order_type: string;
  limit_price: number | null;
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
  is_terminal: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type TransactionView = OrderView & {
  created_at: string;
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
  avg_price: number;
  market_price: number;
};

export type DecisionListItem = {
  id: number;
  symbol: string;
  action: string;
  quantity: number;
  confidence: number;
  risk_status: string;
  risk_reasons: string[];
  created_at: string;
};

export type DashboardSummary = {
  user: UserProfile;
  broker_mode: string;
  live_trading_enabled: boolean;
  auto_execute: boolean;
  total_market_value: number;
  total_cost_basis: number;
  unrealized_pnl: number;
  positions_count: number;
  open_orders_count: number;
  filled_orders_count: number;
  rejected_orders_count: number;
  recent_transactions: TransactionView[];
  positions: PositionView[];
  recent_decisions: DecisionListItem[];
};

export class ApiClient {
  async login(username: string, password: string): Promise<{ csrf_token: string; user: UserProfile }> {
    return this.post("/api/auth/login", { username, password });
  }

  async logout(): Promise<{ ok: boolean }> {
    return this.post("/api/auth/logout", {});
  }

  async me(): Promise<UserProfile> {
    return this.get("/api/auth/me");
  }

  async config(): Promise<PublicConfig> {
    return this.get("/api/config");
  }

  async summary(): Promise<DashboardSummary> {
    return this.get("/api/dashboard/summary");
  }

  async transactions(): Promise<TransactionView[]> {
    return this.get("/api/dashboard/transactions");
  }

  async runDecision(payload: DecisionRequest): Promise<DecisionResponse> {
    return this.post("/api/decisions/run", payload);
  }

  async orders(): Promise<OrderView[]> {
    return this.get("/api/orders");
  }

  async createOrder(payload: OrderCreate): Promise<OrderView> {
    return this.post("/api/orders", payload);
  }

  async approveOrder(orderId: number): Promise<OrderView> {
    return this.post(`/api/orders/${orderId}/approve`, {});
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

  private async parse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        const payload = await response.json();
        throw new Error(payload.detail ?? `HTTP ${response.status}`);
      }

      const detail = await response.text();
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
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
