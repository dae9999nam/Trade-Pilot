const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type UserProfile = {
  username: string;
  role: "admin";
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
  status: string;
  broker_order_id: string | null;
  message: string | null;
};

export type TransactionView = OrderView & {
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
  constructor(private token: string | null) {}

  async login(username: string, password: string): Promise<{ access_token: string; user: UserProfile }> {
    return this.post("/api/auth/login", { username, password }, false);
  }

  async me(): Promise<UserProfile> {
    return this.get("/api/auth/me", true);
  }

  async config(): Promise<PublicConfig> {
    return this.get("/api/config", false);
  }

  async summary(): Promise<DashboardSummary> {
    return this.get("/api/dashboard/summary", true);
  }

  async transactions(): Promise<TransactionView[]> {
    return this.get("/api/dashboard/transactions", true);
  }

  async runDecision(payload: DecisionRequest): Promise<DecisionResponse> {
    return this.post("/api/decisions/run", payload, true);
  }

  async orders(): Promise<OrderView[]> {
    return this.get("/api/orders", true);
  }

  async createOrder(payload: OrderCreate): Promise<OrderView> {
    return this.post("/api/orders", payload, true);
  }

  async approveOrder(orderId: number): Promise<OrderView> {
    return this.post(`/api/orders/${orderId}/approve`, {}, true);
  }

  async positions(): Promise<PositionView[]> {
    return this.get("/api/positions", true);
  }

  private async get<T>(path: string, auth: boolean): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: this.headers(auth)
    });
    return this.parse<T>(response);
  }

  private async post<T>(path: string, payload: unknown, auth: boolean): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...this.headers(auth)
      },
      body: JSON.stringify(payload)
    });
    return this.parse<T>(response);
  }

  private headers(auth: boolean): HeadersInit {
    if (!auth || !this.token) {
      return {};
    }
    return { Authorization: `Bearer ${this.token}` };
  }

  private async parse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  }
}

