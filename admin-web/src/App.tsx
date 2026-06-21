import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  LogOut,
  Play,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  WalletCards,
  XCircle
} from "lucide-react";

import {
  ApiClient,
  DashboardSummary,
  DecisionResponse,
  OrderEventView,
  OrderView,
  PublicConfig,
  TransactionView,
  UserProfile
} from "./api";

type Tab = "dashboard" | "agents" | "orders" | "transactions";
type Tone = "blue" | "green" | "amber" | "red" | "slate";

export default function App() {
  const api = useMemo(() => new ApiClient(), []);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [tab, setTab] = useState<Tab>("dashboard");
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [orderEvents, setOrderEvents] = useState<Record<number, OrderEventView[]>>({});
  const [transactions, setTransactions] = useState<TransactionView[]>([]);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [symbol, setSymbol] = useState("A005930");
  const [quantity, setQuantity] = useState("1");
  const [lastPrice, setLastPrice] = useState("");
  const [manualSide, setManualSide] = useState<"BUY" | "SELL">("BUY");
  const [manualType, setManualType] = useState<"LIMIT" | "MARKET">("LIMIT");
  const [manualPrice, setManualPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh(currentUser = user) {
    if (!currentUser) {
      const nextConfig = await api.config();
      setConfig(nextConfig);
      return;
    }

    const [nextConfig, nextSummary, nextOrders, nextTransactions] = await Promise.all([
      api.config(),
      api.summary(),
      api.orders(),
      api.transactions()
    ]);
    setConfig(nextConfig);
    setSummary(nextSummary);
    setOrders(nextOrders);
    setTransactions(nextTransactions);
  }

  useEffect(() => {
    bootstrap().catch((nextError) => setError(String(nextError)));
  }, []);

  async function bootstrap() {
    try {
      const [nextConfig, nextUser] = await Promise.all([
        api.config(),
        api.me().catch(() => null)
      ]);
      setConfig(nextConfig);
      if (nextUser && nextUser.role !== "admin") {
        await api.logout().catch(() => undefined);
        setUser(null);
        setError("Admin access requires an admin account.");
        return;
      }
      if (nextUser) {
        await refresh(nextUser);
      }
      setUser(nextUser);
    } finally {
      setBootstrapped(true);
    }
  }

  async function runDecision() {
    setLoading(true);
    setError(null);
    try {
      const response = await api.runDecision({
        symbol,
        quantity: Number(quantity || 0),
        last_price: lastPrice ? Number(lastPrice) : undefined
      });
      setDecision(response);
      setTab("agents");
      await refresh();
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function createManualOrder() {
    setLoading(true);
    setError(null);
    try {
      await api.createOrder({
        symbol,
        side: manualSide,
        quantity: Number(quantity || 0),
        order_type: manualType,
        limit_price: manualPrice ? Number(manualPrice) : undefined
      });
      setTab("orders");
      await refresh();
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function approve(orderId: number) {
    setLoading(true);
    setError(null);
    try {
      await api.approveOrder(orderId);
      await refresh();
      await loadOrderEvents(orderId);
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function cancelOrder(orderId: number) {
    setLoading(true);
    setError(null);
    try {
      await api.cancelOrder(orderId);
      await refresh();
      await loadOrderEvents(orderId);
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function refreshOrder(orderId: number) {
    setLoading(true);
    setError(null);
    try {
      await api.refreshOrder(orderId);
      await refresh();
      await loadOrderEvents(orderId);
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function loadOrderEvents(orderId: number) {
    const events = await api.orderEvents(orderId);
    setOrderEvents((current) => ({ ...current, [orderId]: events }));
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      // Session may already be expired; clear local state either way.
    }
    setUser(null);
    setSummary(null);
    setOrders([]);
    setOrderEvents({});
    setTransactions([]);
    setDecision(null);
  }

  if (!bootstrapped) {
    return <main className="login-page">Loading Trade-pilot</main>;
  }

  if (!user) {
    return (
      <LoginScreen
        api={api}
        authError={error}
        onLogin={async (nextUser) => {
          setError(null);
          await refresh(nextUser);
          setUser(nextUser);
        }}
        config={config}
      />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Trade-pilot</p>
          <h1>Admin</h1>
        </div>
        <nav>
          <TabButton label="Dashboard" active={tab === "dashboard"} onClick={() => setTab("dashboard")} />
          <TabButton label="AI Agents" active={tab === "agents"} onClick={() => setTab("agents")} />
          <TabButton label="Orders" active={tab === "orders"} onClick={() => setTab("orders")} />
          <TabButton label="Transactions" active={tab === "transactions"} onClick={() => setTab("transactions")} />
        </nav>
        <button className="icon-text ghost" onClick={logout}>
          <LogOut size={17} />
          Log out
        </button>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Signed in as {user.email}</p>
            <h2>{tabTitle(tab)}</h2>
          </div>
          <div className="topbar-actions">
            <Badge tone={config?.live_trading_enabled ? "green" : "amber"}>
              {config?.live_trading_enabled ? "Live enabled" : "Guarded"}
            </Badge>
            <button className="icon-button" onClick={() => refresh()} aria-label="Refresh">
              <RefreshCw size={18} />
            </button>
          </div>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        {tab === "dashboard" && summary ? (
          <section className="stack">
            <div className="metric-grid">
              <Metric icon={<WalletCards />} label="Market value" value={formatKrw(summary.total_market_value)} />
              <Metric icon={<CircleDollarSign />} label="Unrealized P/L" value={formatKrw(summary.unrealized_pnl)} />
              <Metric icon={<Activity />} label="Positions" value={String(summary.positions_count)} />
              <Metric icon={<ShieldCheck />} label="Open orders" value={String(summary.open_orders_count)} />
            </div>

            <div className="two-column">
              <DecisionPanel
                symbol={symbol}
                quantity={quantity}
                lastPrice={lastPrice}
                manualPrice={manualPrice}
                manualSide={manualSide}
                manualType={manualType}
                loading={loading}
                onSymbol={setSymbol}
                onQuantity={setQuantity}
                onLastPrice={setLastPrice}
                onManualPrice={setManualPrice}
                onManualSide={setManualSide}
                onManualType={setManualType}
                onRun={runDecision}
                onCreateOrder={createManualOrder}
              />
              <ConfigPanel config={config} summary={summary} />
            </div>

            <PositionsTable positions={summary.positions} />
          </section>
        ) : null}

        {tab === "agents" ? (
          <section className="stack">
            <DecisionPanel
              symbol={symbol}
              quantity={quantity}
              lastPrice={lastPrice}
              manualPrice={manualPrice}
              manualSide={manualSide}
              manualType={manualType}
              loading={loading}
              onSymbol={setSymbol}
              onQuantity={setQuantity}
              onLastPrice={setLastPrice}
              onManualPrice={setManualPrice}
              onManualSide={setManualSide}
              onManualType={setManualType}
              onRun={runDecision}
              onCreateOrder={createManualOrder}
            />
            <AgentDecision decision={decision} fallback={summary?.recent_decisions ?? []} />
          </section>
        ) : null}

        {tab === "orders" ? (
          <section className="stack">
            <OrdersTable
              eventsByOrder={orderEvents}
              loading={loading}
              onApprove={approve}
              onCancel={cancelOrder}
              onLoadEvents={loadOrderEvents}
              onRefresh={refreshOrder}
              orders={orders}
            />
          </section>
        ) : null}

        {tab === "transactions" ? (
          <section className="stack">
            <TransactionsTable transactions={transactions} />
          </section>
        ) : null}
      </main>
    </div>
  );
}

function LoginScreen({
  api,
  authError,
  onLogin,
  config
}: {
  api: ApiClient;
  authError: string | null;
  onLogin: (user: UserProfile) => Promise<void>;
  config: PublicConfig | null;
}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await api.login(username, password);
      if (response.user.role !== "admin") {
        await api.logout().catch(() => undefined);
        setError("Admin access requires an admin account.");
        return;
      }
      await onLogin(response.user);
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <p className="eyebrow">Trade-pilot</p>
        <h1>Admin Dashboard</h1>
        <label>
          Username
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          Password
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
        </label>
        {error || authError ? <div className="error-banner">{error ?? authError}</div> : null}
        <button className="primary full" type="submit" disabled={loading}>
          <ShieldCheck size={17} />
          {loading ? "Signing in" : "Sign in"}
        </button>
        <div className="login-meta">
          <Badge tone="blue">{config?.broker_mode ?? "paper"}</Badge>
          <Badge tone="amber">{config?.openai_model ?? "model loading"}</Badge>
        </div>
      </form>
    </main>
  );
}

function DecisionPanel(props: {
  symbol: string;
  quantity: string;
  lastPrice: string;
  manualPrice: string;
  manualSide: "BUY" | "SELL";
  manualType: "LIMIT" | "MARKET";
  loading: boolean;
  onSymbol: (value: string) => void;
  onQuantity: (value: string) => void;
  onLastPrice: (value: string) => void;
  onManualPrice: (value: string) => void;
  onManualSide: (value: "BUY" | "SELL") => void;
  onManualType: (value: "LIMIT" | "MARKET") => void;
  onRun: () => void;
  onCreateOrder: () => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Trading controls</p>
          <h3>AI Decision Request</h3>
        </div>
        <Badge tone="blue">Mobile parity</Badge>
      </div>
      <div className="form-grid">
        <label>
          Symbol
          <input value={props.symbol} onChange={(event) => props.onSymbol(event.target.value.toUpperCase())} />
        </label>
        <label>
          Quantity
          <input value={props.quantity} onChange={(event) => props.onQuantity(event.target.value)} inputMode="numeric" />
        </label>
        <label>
          Last price
          <input
            value={props.lastPrice}
            onChange={(event) => props.onLastPrice(event.target.value)}
            inputMode="decimal"
            placeholder="optional"
          />
        </label>
        <label>
          Manual limit
          <input
            value={props.manualPrice}
            onChange={(event) => props.onManualPrice(event.target.value)}
            inputMode="decimal"
            placeholder="optional"
          />
        </label>
      </div>
      <div className="segmented">
        <button className={props.manualSide === "BUY" ? "active" : ""} onClick={() => props.onManualSide("BUY")}>
          BUY
        </button>
        <button className={props.manualSide === "SELL" ? "active" : ""} onClick={() => props.onManualSide("SELL")}>
          SELL
        </button>
        <button className={props.manualType === "LIMIT" ? "active" : ""} onClick={() => props.onManualType("LIMIT")}>
          LIMIT
        </button>
        <button className={props.manualType === "MARKET" ? "active" : ""} onClick={() => props.onManualType("MARKET")}>
          MARKET
        </button>
      </div>
      <div className="button-row">
        <button className="primary" onClick={props.onRun} disabled={props.loading}>
          <Play size={17} />
          Run AI Decision
        </button>
        <button className="secondary" onClick={props.onCreateOrder} disabled={props.loading}>
          <CheckCircle2 size={17} />
          Stage Manual Order
        </button>
      </div>
    </section>
  );
}

function ConfigPanel({ config, summary }: { config: PublicConfig | null; summary: DashboardSummary }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">System</p>
          <h3>Execution Settings</h3>
        </div>
      </div>
      <dl className="settings-list">
        <Row label="Broker" value={summary.broker_mode} />
        <Row label="Auto execute" value={String(summary.auto_execute)} />
        <Row label="Live trading" value={String(summary.live_trading_enabled)} />
        <Row label="Model" value={config?.openai_model ?? "-"} />
        <Row label="Max order" value={formatKrw(config?.max_order_krw ?? 0)} />
        <Row label="Position cap" value={formatKrw(config?.max_position_krw ?? 0)} />
        <Row label="Confidence gate" value={String(config?.min_decision_confidence ?? "-")} />
      </dl>
    </section>
  );
}

function AgentDecision({
  decision,
  fallback
}: {
  decision: DecisionResponse | null;
  fallback: DashboardSummary["recent_decisions"];
}) {
  if (!decision) {
    return (
      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Recent decisions</p>
            <h3>AI Decision History</h3>
          </div>
        </div>
        <div className="table">
          <div className="table-row header">
            <span>Symbol</span>
            <span>Action</span>
            <span>Confidence</span>
            <span>Status</span>
          </div>
          {fallback.map((item) => (
            <div className="table-row" key={item.id}>
              <span>{item.symbol}</span>
              <span>{item.action}</span>
              <span>{formatPercent(item.confidence)}</span>
              <span><Badge tone={item.risk_status === "APPROVED" ? "green" : "red"}>{item.risk_status}</Badge></span>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="decision-hero">
        <div>
          <p className="eyebrow">{decision.decision.symbol}</p>
          <h3>{decision.decision.action}</h3>
        </div>
        <Badge tone={decision.risk_status === "APPROVED" ? "green" : "red"}>{decision.risk_status}</Badge>
      </div>
      <p className="thesis">{decision.decision.thesis}</p>
      <div className="vote-grid">
        {decision.decision.agent_votes.map((vote) => (
          <article className="vote-card" key={vote.role}>
            <div className="vote-head">
              {vote.verdict === "block" ? <ShieldAlert size={18} /> : <CheckCircle2 size={18} />}
              <strong>{vote.role}</strong>
            </div>
            <p>{vote.verdict} / {formatPercent(vote.confidence)}</p>
            <small>{vote.reasons.join(" ")}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function PositionsTable({ positions }: { positions: DashboardSummary["positions"] }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Portfolio</p>
          <h3>Current Holdings</h3>
        </div>
      </div>
      <div className="table four">
        <div className="table-row header">
          <span>Symbol</span>
          <span>Qty</span>
          <span>Avg price</span>
          <span>Market price</span>
        </div>
        {positions.map((position) => (
          <div className="table-row" key={position.symbol}>
            <span>{position.symbol}</span>
            <span>{position.quantity}</span>
            <span>{formatKrw(position.avg_price)}</span>
            <span>{formatKrw(position.market_price)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function OrdersTable({
  eventsByOrder,
  orders,
  loading,
  onApprove,
  onCancel,
  onLoadEvents,
  onRefresh
}: {
  eventsByOrder: Record<number, OrderEventView[]>;
  orders: OrderView[];
  loading: boolean;
  onApprove: (orderId: number) => void;
  onCancel: (orderId: number) => void;
  onLoadEvents: (orderId: number) => void;
  onRefresh: (orderId: number) => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Execution</p>
          <h3>Orders</h3>
        </div>
      </div>
      <div className="table orders">
        <div className="table-row header">
          <span>Symbol</span>
          <span>Side</span>
          <span>Qty</span>
          <span>Status</span>
          <span>Attempts</span>
          <span>Action</span>
        </div>
        {orders.map((order) => (
          <div className="table-row" key={order.id}>
            <span>{order.symbol}</span>
            <span>{order.side}</span>
            <span>{order.quantity}</span>
            <span><Badge tone={orderTone(order.status)}>{order.status}</Badge></span>
            <span>{order.submission_attempts}</span>
            <span className="row-actions">
              {order.can_approve ? (
                <button className="mini-button" onClick={() => onApprove(order.id)} disabled={loading}>
                  <CheckCircle2 size={15} />
                  {order.status === "SUBMISSION_FAILED" ? "Retry" : "Approve"}
                </button>
              ) : null}
              {!order.is_terminal ? (
                <button className="mini-button" onClick={() => onRefresh(order.id)} disabled={loading}>
                  <RefreshCw size={15} />
                  Refresh
                </button>
              ) : null}
              {order.can_cancel ? (
                <button className="mini-button" onClick={() => onCancel(order.id)} disabled={loading}>
                  <XCircle size={15} />
                  Cancel
                </button>
              ) : null}
              <button className="mini-button" onClick={() => onLoadEvents(order.id)} disabled={loading}>
                <Clock3 size={15} />
                Events
              </button>
            </span>
          </div>
        ))}
      </div>
      {Object.entries(eventsByOrder).length > 0 ? (
        <div className="order-events-panel">
          {Object.entries(eventsByOrder).map(([orderId, events]) => (
            <div className="order-events-group" key={orderId}>
              <h4>Order #{orderId} timeline</h4>
              {events.length === 0 ? <p>No events</p> : null}
              {events.map((event) => (
                <div className="order-event-row" key={event.id}>
                  <span>{formatDate(event.created_at)}</span>
                  <strong>{event.to_status}</strong>
                  <small>{event.event_type}{event.message ? ` / ${event.message}` : ""}</small>
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TransactionsTable({ transactions }: { transactions: TransactionView[] }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Account</p>
          <h3>Recent Transactions</h3>
        </div>
      </div>
      <div className="table transactions">
        <div className="table-row header">
          <span>Time</span>
          <span>Symbol</span>
          <span>Side</span>
          <span>Qty</span>
          <span>Status</span>
          <span>Message</span>
        </div>
        {transactions.map((item) => (
          <div className="table-row" key={item.id}>
            <span>{formatDate(item.created_at)}</span>
            <span>{item.symbol}</span>
            <span>{item.side}</span>
            <span>{item.quantity}</span>
            <span><Badge tone={orderTone(item.status)}>{item.status}</Badge></span>
            <span>{item.message ?? "-"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <article className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button className={active ? "nav-button active" : "nav-button"} onClick={onClick}>
      {label}
    </button>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function tabTitle(tab: Tab) {
  if (tab === "agents") return "AI Agents";
  if (tab === "orders") return "Orders";
  if (tab === "transactions") return "Transactions";
  return "Dashboard";
}

function formatKrw(value: number) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0
  }).format(Number(value));
}

function formatPercent(value: number) {
  return `${Math.round(Number(value) * 100)}%`;
}

function orderTone(status: string): Tone {
  if (status === "FILLED") return "green";
  if (status === "REJECTED" || status === "SUBMISSION_FAILED") return "red";
  if (status === "SUBMITTED" || status === "SUBMITTING") return "blue";
  if (status === "APPROVED" || status === "PARTIALLY_FILLED") return "amber";
  if (status === "CANCELED") return "slate";
  return "amber";
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
