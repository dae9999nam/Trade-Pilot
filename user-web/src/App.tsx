import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  ListChecks,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  WalletCards
} from "lucide-react";

import { ApiClient } from "./api";
import type {
  DecisionListItem,
  DecisionResponse,
  MoneyValue,
  OrderView,
  PositionView,
  PublicConfig,
  RiskStatus
} from "./api";

type Tab = "dashboard" | "agents" | "orders";
type Tone = "blue" | "green" | "amber" | "red" | "slate";

export default function App() {
  const api = useMemo(() => new ApiClient(), []);
  const [tab, setTab] = useState<Tab>("dashboard");
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [positions, setPositions] = useState<PositionView[]>([]);
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [decisions, setDecisions] = useState<DecisionListItem[]>([]);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [symbol, setSymbol] = useState("A005930");
  const [quantity, setQuantity] = useState("1");
  const [lastPrice, setLastPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextConfig, nextPositions, nextOrders, nextDecisions] = await Promise.all([
      api.config(),
      api.positions(),
      api.orders(),
      api.decisions()
    ]);
    setConfig(nextConfig);
    setPositions(nextPositions);
    setOrders(nextOrders);
    setDecisions(nextDecisions);
  }

  useEffect(() => {
    refresh().catch((nextError) => setError(String(nextError)));
  }, []);

  async function runDecision(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const payload = {
        symbol: symbol.trim().toUpperCase(),
        quantity: Number(quantity || 0),
        last_price: lastPrice ? Number(lastPrice) : undefined
      };
      const response = await api.runDecision(payload);
      setDecision(response);
      setTab("agents");
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
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  const portfolioValue = positions.reduce(
    (total, position) => total + Number(position.market_price) * position.quantity,
    0
  );
  const openOrders = orders.filter((order) => order.status === "PENDING_APPROVAL" || order.status === "SUBMITTED");
  const lastDecision = decision ?? null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Trade-pilot</p>
          <h1>Portfolio</h1>
        </div>
        <nav>
          <TabButton icon={<BarChart3 size={17} />} label="Dashboard" active={tab === "dashboard"} onClick={() => setTab("dashboard")} />
          <TabButton icon={<Bot size={17} />} label="AI Agents" active={tab === "agents"} onClick={() => setTab("agents")} />
          <TabButton icon={<ListChecks size={17} />} label="Orders" active={tab === "orders"} onClick={() => setTab("orders")} />
        </nav>
        <div className="sidebar-foot">
          <Badge tone={config?.live_trading_enabled ? "green" : "amber"}>
            {config?.live_trading_enabled ? "Live enabled" : "Guarded"}
          </Badge>
          <span>{config?.broker_mode ?? "paper"}</span>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">{config?.openai_model ?? "loading"}</p>
            <h2>{tabTitle(tab)}</h2>
          </div>
          <button className="icon-button" type="button" onClick={() => refresh()} aria-label="Refresh">
            <RefreshCw size={18} />
          </button>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        {tab === "dashboard" ? (
          <section className="stack">
            <div className="metric-grid">
              <Metric icon={<WalletCards />} label="Market value" value={formatKrw(portfolioValue)} />
              <Metric icon={<Activity />} label="Positions" value={String(positions.filter((item) => item.quantity !== 0).length)} />
              <Metric icon={<Clock3 />} label="Open orders" value={String(openOrders.length)} />
              <Metric icon={<ShieldCheck />} label="Confidence gate" value={formatPercent(config?.min_decision_confidence ?? 0)} />
            </div>

            <div className="dashboard-grid">
              <DecisionForm
                symbol={symbol}
                quantity={quantity}
                lastPrice={lastPrice}
                loading={loading}
                onSymbol={setSymbol}
                onQuantity={setQuantity}
                onLastPrice={setLastPrice}
                onSubmit={runDecision}
              />
              <RiskPanel config={config} />
            </div>

            <PositionsPanel positions={positions} />
          </section>
        ) : null}

        {tab === "agents" ? (
          <section className="stack">
            <DecisionForm
              symbol={symbol}
              quantity={quantity}
              lastPrice={lastPrice}
              loading={loading}
              onSymbol={setSymbol}
              onQuantity={setQuantity}
              onLastPrice={setLastPrice}
              onSubmit={runDecision}
            />
            <DecisionPanel decision={lastDecision} history={decisions} />
          </section>
        ) : null}

        {tab === "orders" ? (
          <section className="stack">
            <OrdersPanel orders={orders} loading={loading} onApprove={approve} />
          </section>
        ) : null}
      </main>
    </div>
  );
}

function DecisionForm(props: {
  symbol: string;
  quantity: string;
  lastPrice: string;
  loading: boolean;
  onSymbol: (value: string) => void;
  onQuantity: (value: string) => void;
  onLastPrice: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="panel decision-form" onSubmit={props.onSubmit}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Decision request</p>
          <h3>Run Agent Review</h3>
        </div>
        <Badge tone="blue">Paper first</Badge>
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
      </div>
      <button className="primary" type="submit" disabled={props.loading}>
        <Play size={17} />
        {props.loading ? "Running" : "Run AI Decision"}
      </button>
    </form>
  );
}

function RiskPanel({ config }: { config: PublicConfig | null }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Guardrails</p>
          <h3>Execution Limits</h3>
        </div>
      </div>
      <dl className="settings-list">
        <Row label="Broker" value={config?.broker_mode ?? "-"} />
        <Row label="Auto execute" value={config?.auto_execute ? "on" : "off"} />
        <Row label="Live trading" value={config?.live_trading_enabled ? "enabled" : "disabled"} />
        <Row label="Max order" value={formatKrw(config?.max_order_krw ?? 0)} />
        <Row label="Position cap" value={formatKrw(config?.max_position_krw ?? 0)} />
      </dl>
    </section>
  );
}

function DecisionPanel({
  decision,
  history
}: {
  decision: DecisionResponse | null;
  history: DecisionListItem[];
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
        <div className="table decisions">
          <div className="table-row header">
            <span>Symbol</span>
            <span>Action</span>
            <span>Confidence</span>
            <span>Status</span>
          </div>
          {history.length === 0 ? <EmptyRow label="No decisions yet" /> : null}
          {history.slice(0, 8).map((item) => (
            <div className="table-row" key={item.id}>
              <span>{item.symbol}</span>
              <span>{item.action}</span>
              <span>{formatPercent(item.confidence)}</span>
              <span><Badge tone={riskTone(item.risk_status)}>{item.risk_status}</Badge></span>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="decision-summary">
        <div>
          <p className="eyebrow">{decision.decision.symbol}</p>
          <h3>{decision.decision.action}</h3>
        </div>
        <Badge tone={riskTone(decision.risk_status)}>{decision.risk_status}</Badge>
      </div>
      <p className="thesis">{decision.decision.thesis}</p>
      {decision.risk_reasons.length > 0 ? (
        <div className="reason-list">
          {decision.risk_reasons.map((reason) => (
            <span key={reason}>{reason}</span>
          ))}
        </div>
      ) : null}
      <div className="vote-grid">
        {decision.decision.agent_votes.map((vote) => (
          <article className="vote-card" key={vote.role}>
            <div className="vote-head">
              {vote.verdict === "block" ? <ShieldAlert size={18} /> : <CheckCircle2 size={18} />}
              <strong>{vote.role}</strong>
            </div>
            <p>{vote.verdict} / {formatPercent(vote.confidence)}</p>
            <small>{vote.reasons.join(" ") || "No reason returned"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function PositionsPanel({ positions }: { positions: PositionView[] }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Holdings</p>
          <h3>Current Positions</h3>
        </div>
      </div>
      <div className="table positions">
        <div className="table-row header">
          <span>Symbol</span>
          <span>Qty</span>
          <span>Avg price</span>
          <span>Market price</span>
          <span>Value</span>
        </div>
        {positions.length === 0 ? <EmptyRow label="No positions" /> : null}
        {positions.map((position) => (
          <div className="table-row" key={position.symbol}>
            <span>{position.symbol}</span>
            <span>{position.quantity}</span>
            <span>{formatKrw(position.avg_price)}</span>
            <span>{formatKrw(position.market_price)}</span>
            <span>{formatKrw(Number(position.market_price) * position.quantity)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function OrdersPanel({
  orders,
  loading,
  onApprove
}: {
  orders: OrderView[];
  loading: boolean;
  onApprove: (orderId: number) => void;
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
          <span>Type</span>
          <span>Status</span>
          <span>Action</span>
        </div>
        {orders.length === 0 ? <EmptyRow label="No orders" /> : null}
        {orders.map((order) => (
          <div className="table-row" key={order.id}>
            <span>{order.symbol}</span>
            <span>{order.side}</span>
            <span>{order.quantity}</span>
            <span>{order.order_type}</span>
            <span><Badge tone={orderTone(order.status)}>{order.status}</Badge></span>
            <span>
              {order.status === "PENDING_APPROVAL" ? (
                <button className="mini-button" type="button" onClick={() => onApprove(order.id)} disabled={loading}>
                  <CheckCircle2 size={15} />
                  Approve
                </button>
              ) : (
                order.broker_order_id ?? "-"
              )}
            </span>
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

function TabButton({
  icon,
  label,
  active,
  onClick
}: {
  icon: ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button className={active ? "nav-button active" : "nav-button"} type="button" onClick={onClick}>
      {icon}
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

function EmptyRow({ label }: { label: string }) {
  return (
    <div className="empty-row">
      <span>{label}</span>
    </div>
  );
}

function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function tabTitle(tab: Tab) {
  if (tab === "agents") return "AI Agents";
  if (tab === "orders") return "Orders";
  return "Dashboard";
}

function riskTone(status: RiskStatus): Tone {
  if (status === "APPROVED") return "green";
  if (status === "NEEDS_APPROVAL") return "amber";
  return "red";
}

function orderTone(status: string): Tone {
  if (status === "FILLED") return "green";
  if (status === "REJECTED") return "red";
  if (status === "SUBMITTED") return "blue";
  return "amber";
}

function formatKrw(value: MoneyValue | null) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0
  }).format(Number(value ?? 0));
}

function formatPercent(value: number) {
  return `${Math.round(Number(value) * 100)}%`;
}
