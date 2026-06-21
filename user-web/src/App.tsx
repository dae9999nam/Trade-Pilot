import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  Globe2,
  LineChart,
  ListChecks,
  LogOut,
  PieChart,
  RefreshCw,
  Search,
  Send,
  Settings as SettingsIcon,
  ShieldCheck,
  Table2,
  UserRound,
  WalletCards,
  XCircle
} from "lucide-react";

import { ApiClient } from "./api";
import type {
  AssistantArtifact,
  AssistantQueryResponse,
  MoneyValue,
  OrderEventView,
  OrderView,
  PositionView,
  PublicConfig,
  UserProfile
} from "./api";

type Tone = "blue" | "green" | "amber" | "red" | "slate";
type View = "positions" | "orders" | "workspace" | "settings";

export default function App() {
  const api = useMemo(() => new ApiClient(), []);
  const [view, setView] = useState<View>("positions");
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [positions, setPositions] = useState<PositionView[]>([]);
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [orderEvents, setOrderEvents] = useState<Record<number, OrderEventView[]>>({});
  const [assistantResponse, setAssistantResponse] = useState<AssistantQueryResponse | null>(null);
  const [query, setQuery] = useState("A005930을 분석하고 매수, 매도, 보유 중 어떤 선택이 적절한지 알려줘.");
  const [symbol, setSymbol] = useState("A005930");
  const [quantity, setQuantity] = useState("1");
  const [lastPrice, setLastPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(currentUser = user) {
    const nextConfig = await api.config();
    setConfig(nextConfig);

    if (!currentUser) {
      setPositions([]);
      setOrders([]);
      setOrderEvents({});
      return;
    }

    const [nextPositions, nextOrders] = await Promise.all([
      api.positions(),
      api.orders()
    ]);
    setPositions(nextPositions);
    setOrders(nextOrders);
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
      setUser(nextUser);
      await refresh(nextUser);
    } finally {
      setBootstrapped(true);
    }
  }

  async function authenticate(action: "login" | "register", username: string, password: string) {
    setLoading(true);
    setError(null);
    try {
      const response = action === "register"
        ? await api.register(username, password)
        : await api.login(username, password);
      setUser(response.user);
      await refresh(response.user);
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function updateProfile(payload: { email: string; currentPassword: string; newPassword?: string }) {
    setLoading(true);
    setError(null);
    try {
      const nextUser = await api.updateProfile({
        current_password: payload.currentPassword,
        email: payload.email,
        new_password: payload.newPassword || undefined
      });
      setUser(nextUser);
    } catch (nextError) {
      setError(String(nextError));
      throw nextError;
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    setLoading(true);
    setError(null);
    try {
      await api.logout();
    } catch {
      // The local UI state should still clear if the server session already expired.
    } finally {
      setUser(null);
      setAssistantResponse(null);
      setPositions([]);
      setOrders([]);
      setOrderEvents({});
      setLoading(false);
    }
  }

  async function runAssistant(event: FormEvent) {
    event.preventDefault();
    if (!user) {
      setError("Sign in before running assistant queries.");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const response = await api.queryAssistant({
        query,
        symbol: symbol.trim() ? symbol.trim().toUpperCase() : undefined,
        quantity: Number(quantity || 0),
        last_price: lastPrice ? Number(lastPrice) : undefined
      });
      setAssistantResponse(response);
      setView("workspace");
      await refresh();
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function approve(orderId: number) {
    if (!user) {
      setError("Sign in before approving orders.");
      return;
    }
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

  const portfolioValue = positions.reduce(
    (total, position) => total + Number(position.market_price) * position.quantity,
    0
  );
  const openOrders = orders.filter((order) => !order.is_terminal);
  const displayName = user ? user.email.split("@")[0] || user.email : "";

  if (!bootstrapped) {
    return <div className="loading-screen">Loading Trade-pilot</div>;
  }

  if (!user) {
    return (
      <AuthScreen
        config={config}
        error={error}
        loading={loading}
        onSubmit={authenticate}
      />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Trade-pilot</p>
          <h1>Analyst OS</h1>
          <div className="user-greeting">
            <UserRound size={16} />
            <span>Hello, {displayName}</span>
          </div>
        </div>
        <nav>
          <NavButton icon={<WalletCards size={17} />} label="Holdings / Positions" active={view === "positions"} onClick={() => setView("positions")} />
          <NavButton icon={<ListChecks size={17} />} label="Orders" active={view === "orders"} onClick={() => setView("orders")} />
          <NavButton icon={<Bot size={17} />} label="Workspace" active={view === "workspace"} onClick={() => setView("workspace")} />
        </nav>
        <div className="sidebar-foot">
          <Badge tone={config?.live_trading_enabled ? "green" : "amber"}>
            {config?.live_trading_enabled ? "Live enabled" : "Guarded"}
          </Badge>
          <span>{config?.broker_mode ?? "paper"}</span>
          <NavButton icon={<SettingsIcon size={17} />} label="Settings" active={view === "settings"} onClick={() => setView("settings")} />
          <button className="logout-button" type="button" onClick={logout} disabled={loading}>
            <LogOut size={15} />
            Sign out
          </button>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">{config?.openai_model ?? "loading"}</p>
            <h2>{viewTitle(view)}</h2>
            <span className="signed-in">Signed in as {user.email}</span>
          </div>
          <button className="icon-button" type="button" onClick={() => refresh()} aria-label="Refresh">
            <RefreshCw size={18} />
          </button>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        {view === "positions" ? (
          <section className="stack">
            <PortfolioOverview
              openOrders={openOrders.length}
              portfolioValue={portfolioValue}
              positions={positions}
            />
            <PositionsPanel positions={positions} />
          </section>
        ) : null}

        {view === "workspace" ? (
          <section className="workspace-grid">
            <div className="main-column">
              <QueryPanel
                query={query}
                symbol={symbol}
                quantity={quantity}
                lastPrice={lastPrice}
                loading={loading}
                onQuery={setQuery}
                onSymbol={setSymbol}
                onQuantity={setQuantity}
                onLastPrice={setLastPrice}
                onSubmit={runAssistant}
              />
              <AnswerPanel response={assistantResponse} />
              <ArtifactGrid artifacts={assistantResponse?.artifacts ?? []} />
            </div>
            <aside className="context-rail">
              <Metric icon={<WalletCards />} label="Market value" value={formatKrw(portfolioValue)} />
              <Metric icon={<Activity />} label="Positions" value={String(positions.filter((item) => item.quantity !== 0).length)} />
              <Metric icon={<Clock3 />} label="Open orders" value={String(openOrders.length)} />
              <Metric icon={<ShieldCheck />} label="Confidence gate" value={formatPercent(config?.min_decision_confidence ?? 0)} />
              <SourcePanel />
            </aside>
          </section>
        ) : null}

        {view === "orders" ? (
          <OrdersPanel
            eventsByOrder={orderEvents}
            loading={loading}
            onApprove={approve}
            onCancel={cancelOrder}
            onLoadEvents={loadOrderEvents}
            onRefresh={refreshOrder}
            orders={orders}
          />
        ) : null}

        {view === "settings" ? (
          <section className="stack">
            <SettingsPanel
              loading={loading}
              onSubmit={updateProfile}
              user={user}
            />
          </section>
        ) : null}
      </main>
    </div>
  );
}

function AuthScreen({
  config,
  error,
  loading,
  onSubmit
}: {
  config: PublicConfig | null;
  error: string | null;
  loading: boolean;
  onSubmit: (action: "login" | "register", username: string, password: string) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(mode, username, password);
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <p className="eyebrow">Trade-pilot</p>
        <h1>Analyst OS</h1>
        <div className="auth-tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Sign in
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Create account
          </button>
        </div>
        <label>
          Email or username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="you@example.com"
          />
        </label>
        <label>
          Password
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>
        {mode === "register" ? <small className="field-hint">Use at least 12 characters.</small> : null}
        {error ? <div className="error-banner">{error}</div> : null}
        <button className="primary full" type="submit" disabled={loading}>
          <ShieldCheck size={17} />
          {loading ? "Working" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        <div className="auth-meta">
          <Badge tone="blue">{config?.broker_mode ?? "paper"}</Badge>
          <Badge tone="amber">{config?.openai_model ?? "model loading"}</Badge>
        </div>
      </form>
    </main>
  );
}

function QueryPanel(props: {
  query: string;
  symbol: string;
  quantity: string;
  lastPrice: string;
  loading: boolean;
  onQuery: (value: string) => void;
  onSymbol: (value: string) => void;
  onQuantity: (value: string) => void;
  onLastPrice: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="query-panel" onSubmit={props.onSubmit}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">AI workspace</p>
          <h3>Ask the trading system</h3>
        </div>
        <Badge tone="blue">Query + artifacts</Badge>
      </div>
      <div className="query-input-shell">
        <Search size={19} />
        <textarea
          value={props.query}
          onChange={(event) => props.onQuery(event.target.value)}
          placeholder="Ask about a stock, portfolio exposure, orders, system status, or web research."
        />
      </div>
      <div className="context-grid">
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
      <div className="prompt-row">
        <button className="primary" type="submit" disabled={props.loading}>
          <Send size={17} />
          {props.loading ? "Analyzing" : "Run analysis"}
        </button>
        <span>Returns text, charts, tables, and browser-style research artifacts.</span>
      </div>
    </form>
  );
}

function AnswerPanel({ response }: { response: AssistantQueryResponse | null }) {
  if (!response) {
    return (
      <section className="answer-panel empty">
        <Bot size={24} />
        <div>
          <p className="eyebrow">Waiting for query</p>
          <h3>Results appear as an analyst workspace, not a chat transcript.</h3>
        </div>
      </section>
    );
  }

  return (
    <section className="answer-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{response.intent.replace("_", " ")}</p>
          <h3>System answer</h3>
        </div>
        <Badge tone={response.decision?.risk_status === "REJECTED" ? "red" : "green"}>
          {response.decision?.risk_status ?? "READY"}
        </Badge>
      </div>
      <p className="answer-text">{response.answer}</p>
      {response.suggested_actions.length > 0 ? (
        <div className="suggestion-row">
          {response.suggested_actions.map((action) => (
            <span key={action}>{action}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function ArtifactGrid({ artifacts }: { artifacts: AssistantArtifact[] }) {
  if (artifacts.length === 0) {
    return null;
  }

  return (
    <section className="artifact-grid">
      {artifacts.map((artifact) => (
        <ArtifactCard artifact={artifact} key={artifact.id} />
      ))}
    </section>
  );
}

function ArtifactCard({ artifact }: { artifact: AssistantArtifact }) {
  return (
    <article className={`artifact-card ${artifact.type}`}>
      <div className="artifact-head">
        <div>
          <p className="eyebrow">{artifact.type.replace("_", " ")}</p>
          <h3>{artifact.title}</h3>
        </div>
        {artifactIcon(artifact.type)}
      </div>
      {artifact.description ? <p className="artifact-description">{artifact.description}</p> : null}
      {artifact.type === "metric_grid" ? <MetricArtifact artifact={artifact} /> : null}
      {artifact.type === "decision_card" ? <DecisionArtifact artifact={artifact} /> : null}
      {artifact.type === "table" ? <TableArtifact artifact={artifact} /> : null}
      {artifact.type === "line_chart" ? <LineChartArtifact artifact={artifact} /> : null}
      {artifact.type === "bar_chart" ? <BarChartArtifact artifact={artifact} /> : null}
      {artifact.type === "pie_chart" ? <PieChartArtifact artifact={artifact} /> : null}
      {artifact.type === "web_tab" ? <WebTabArtifact artifact={artifact} /> : null}
    </article>
  );
}

function MetricArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const items = asRecordArray(artifact.data.items);
  return (
    <div className="mini-metric-grid">
      {items.map((item) => (
        <div className="mini-metric" key={String(item.label)}>
          <span>{String(item.label ?? "-")}</span>
          <strong>{formatValue(item.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function DecisionArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const data = artifact.data;
  return (
    <div className="decision-artifact">
      <strong>{String(data.action ?? "HOLD")}</strong>
      <dl>
        <Row label="Symbol" value={String(data.symbol ?? "-")} />
        <Row label="Quantity" value={String(data.quantity ?? 0)} />
        <Row label="Confidence" value={formatPercent(Number(data.confidence ?? 0))} />
        <Row label="Risk" value={String(data.risk_status ?? "-")} />
      </dl>
      <div className="reason-list">
        {asStringArray(data.risk_reasons).map((reason) => (
          <span key={reason}>{reason}</span>
        ))}
      </div>
    </div>
  );
}

function TableArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const columns = asStringArray(artifact.data.columns);
  const rows = asRecordArray(artifact.data.rows);
  return (
    <div className="data-table">
      <div className="data-row header" style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(120px, 1fr))` }}>
        {columns.map((column) => <span key={column}>{column}</span>)}
      </div>
      {rows.length === 0 ? <div className="empty-row">No rows</div> : null}
      {rows.map((row, index) => (
        <div
          className="data-row"
          key={index}
          style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(120px, 1fr))` }}
        >
          {columns.map((column) => <span key={column}>{formatValue(row[column])}</span>)}
        </div>
      ))}
    </div>
  );
}

function LineChartArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const points = asRecordArray(artifact.data.points);
  const xKey = String(artifact.data.xKey ?? "label");
  const yKeys = asStringArray(artifact.data.yKeys);
  const yKey = yKeys[0] ?? "value";
  const values = points.map((point) => Number(point[yKey] ?? 0));
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const width = 520;
  const height = 190;
  const chartPoints = points.map((point, index) => {
    const x = points.length <= 1 ? 24 : 24 + (index / (points.length - 1)) * (width - 48);
    const ratio = (Number(point[yKey] ?? 0) - min) / Math.max(max - min, 1);
    const y = height - 28 - ratio * (height - 60);
    return { x, y, label: String(point[xKey] ?? index), value: Number(point[yKey] ?? 0) };
  });
  const polyline = chartPoints.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <line x1="24" y1={height - 28} x2={width - 24} y2={height - 28} />
        <polyline points={polyline} />
        {chartPoints.map((point) => (
          <g key={point.label}>
            <circle cx={point.x} cy={point.y} r="4" />
            <text x={point.x} y={height - 8}>{point.label}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function BarChartArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const bars = asRecordArray(artifact.data.bars);
  const xKey = String(artifact.data.xKey ?? "label");
  const yKey = String(artifact.data.yKey ?? "value");
  const max = Math.max(...bars.map((bar) => Number(bar[yKey] ?? 0)), 1);

  return (
    <div className="bar-list">
      {bars.map((bar) => {
        const value = Number(bar[yKey] ?? 0);
        return (
          <div className="bar-row" key={String(bar[xKey])}>
            <span>{String(bar[xKey] ?? "-")}</span>
            <div className="bar-track">
              <div style={{ width: `${Math.max((value / max) * 100, 3)}%` }} />
            </div>
            <strong>{Math.round(value)}</strong>
          </div>
        );
      })}
    </div>
  );
}

function PieChartArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const slices = asRecordArray(artifact.data.slices);
  const labelKey = String(artifact.data.labelKey ?? "label");
  const valueKey = String(artifact.data.valueKey ?? "value");
  const values = slices.map((slice) => Math.max(Number(slice[valueKey] ?? 0), 0));
  const total = values.reduce((sum, value) => sum + value, 0);
  const colors = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#dc2626", "#0891b2"];
  let cursor = 0;
  const gradient = total === 0
    ? "#e2e8f0"
    : values.map((value, index) => {
      const start = cursor;
      const end = cursor + (value / total) * 360;
      cursor = end;
      return `${colors[index % colors.length]} ${start}deg ${end}deg`;
    }).join(", ");

  return (
    <div className="pie-layout">
      <div className="pie" style={{ background: `conic-gradient(${gradient})` }} />
      <div className="pie-legend">
        {slices.map((slice, index) => (
          <div key={String(slice[labelKey])}>
            <span style={{ background: colors[index % colors.length] }} />
            <strong>{String(slice[labelKey] ?? "-")}</strong>
            <small>{formatKrw(slice[valueKey] as MoneyValue)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function WebTabArtifact({ artifact }: { artifact: AssistantArtifact }) {
  const url = String(artifact.data.url ?? "");
  return (
    <div className="browser-artifact">
      <div className="browser-toolbar">
        <span />
        <span />
        <span />
        <input value={url} readOnly />
        <button type="button" onClick={() => window.open(url, "_blank", "noopener,noreferrer")}>
          <ExternalLink size={15} />
          Open
        </button>
      </div>
      <div className="browser-body">
        <Globe2 size={28} />
        <strong>{String(artifact.data.label ?? "Research tab")}</strong>
        <p>External websites may block iframe rendering. Use Open to continue in a browser tab.</p>
      </div>
    </div>
  );
}

function SourcePanel() {
  return (
    <section className="source-panel">
      <p className="eyebrow">Connected sources</p>
      <div><Database size={15} /> PostgreSQL tables</div>
      <div><Bot size={15} /> AgentOrchestrator</div>
      <div><LineChart size={15} /> Market snapshots</div>
      <div><Globe2 size={15} /> Web tab scaffold</div>
    </section>
  );
}

function PositionsPanel({ positions }: { positions: PositionView[] }) {
  const rows = positions.map((position) => ({
    symbol: position.symbol,
    quantity: position.quantity,
    avg_price: position.avg_price,
    market_price: position.market_price,
    value: Number(position.market_price) * position.quantity
  }));
  return (
    <ArtifactCard
      artifact={{
        id: "positions-table",
        type: "table",
        title: "Current positions",
        description: null,
        data: {
          columns: ["symbol", "quantity", "avg_price", "market_price", "value"],
          rows
        }
      }}
    />
  );
}

function PortfolioOverview({
  openOrders,
  portfolioValue,
  positions
}: {
  openOrders: number;
  portfolioValue: number;
  positions: PositionView[];
}) {
  const activePositions = positions.filter((position) => position.quantity !== 0).length;
  const costBasis = positions.reduce(
    (total, position) => total + Number(position.avg_price) * position.quantity,
    0
  );
  const pnl = portfolioValue - costBasis;

  return (
    <section className="summary-grid">
      <Metric icon={<WalletCards />} label="Market value" value={formatKrw(portfolioValue)} />
      <Metric icon={<Activity />} label="Positions" value={String(activePositions)} />
      <Metric icon={<Clock3 />} label="Open orders" value={String(openOrders)} />
      <Metric icon={<ShieldCheck />} label="Unrealized P/L" value={formatKrw(pnl)} />
    </section>
  );
}

function SettingsPanel({
  loading,
  onSubmit,
  user
}: {
  loading: boolean;
  onSubmit: (payload: { email: string; currentPassword: string; newPassword?: string }) => Promise<void>;
  user: UserProfile;
}) {
  const [email, setEmail] = useState(user.email);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    setSaved(false);

    if (!currentPassword) {
      setLocalError("Current password is required.");
      return;
    }
    if (newPassword && newPassword !== confirmPassword) {
      setLocalError("New passwords do not match.");
      return;
    }
    if (newPassword && newPassword.length < 12) {
      setLocalError("New password must be at least 12 characters.");
      return;
    }

    await onSubmit({
      email,
      currentPassword,
      newPassword: newPassword || undefined
    });
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setSaved(true);
  }

  return (
    <section className="settings-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Account</p>
          <h3>Settings</h3>
        </div>
        <Badge tone="slate">{user.role}</Badge>
      </div>
      <form className="settings-form" onSubmit={submit}>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
        </label>
        <label>
          Current password
          <input
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
          />
        </label>
        <label>
          New password
          <input
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            type="password"
            autoComplete="new-password"
            placeholder="Leave blank to keep current password"
          />
        </label>
        <label>
          Confirm new password
          <input
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            type="password"
            autoComplete="new-password"
          />
        </label>
        {localError ? <div className="error-banner">{localError}</div> : null}
        {saved ? <div className="success-banner">Settings updated.</div> : null}
        <button className="primary" type="submit" disabled={loading}>
          Save changes
        </button>
      </form>
    </section>
  );
}

function OrdersPanel({
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
    <section className="orders-workspace">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Execution</p>
          <h3>Orders</h3>
        </div>
      </div>
      <div className="order-list">
        {orders.length === 0 ? <div className="empty-row">No orders</div> : null}
        {orders.map((order) => (
          <article className="order-card" key={order.id}>
            <div className="order-main">
              <div>
                <p className="eyebrow">{order.mode}</p>
                <h3>{order.symbol} {order.side}</h3>
                <span>{order.quantity} shares / {order.order_type}</span>
              </div>
              <div className="order-meta">
                <Badge tone={orderTone(order.status)}>{order.status}</Badge>
                <small>{order.broker_order_id ?? order.message ?? `Updated ${formatDateTime(order.last_status_at)}`}</small>
              </div>
              <div className="order-actions">
                {order.can_approve ? (
                  <button className="mini-button" type="button" onClick={() => onApprove(order.id)} disabled={loading}>
                    <CheckCircle2 size={15} />
                    {order.status === "SUBMISSION_FAILED" ? "Retry" : "Approve"}
                  </button>
                ) : null}
                {!order.is_terminal ? (
                  <button className="mini-button" type="button" onClick={() => onRefresh(order.id)} disabled={loading}>
                    <RefreshCw size={15} />
                    Refresh
                  </button>
                ) : null}
                {order.can_cancel ? (
                  <button className="mini-button" type="button" onClick={() => onCancel(order.id)} disabled={loading}>
                    <XCircle size={15} />
                    Cancel
                  </button>
                ) : null}
                <button className="mini-button" type="button" onClick={() => onLoadEvents(order.id)} disabled={loading}>
                  <Clock3 size={15} />
                  Timeline
                </button>
              </div>
            </div>
            {eventsByOrder[order.id] ? <OrderTimeline events={eventsByOrder[order.id]} /> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function OrderTimeline({ events }: { events: OrderEventView[] }) {
  if (events.length === 0) {
    return <div className="order-timeline empty-row">No events</div>;
  }

  return (
    <div className="order-timeline">
      {events.map((event) => (
        <div className="order-event" key={event.id}>
          <span>{formatDateTime(event.created_at)}</span>
          <strong>{event.to_status}</strong>
          <small>{event.event_type}{event.message ? ` / ${event.message}` : ""}</small>
        </div>
      ))}
    </div>
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

function NavButton({
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

function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function artifactIcon(type: string) {
  if (type === "line_chart") return <LineChart size={20} />;
  if (type === "bar_chart") return <BarChart3 size={20} />;
  if (type === "pie_chart") return <PieChart size={20} />;
  if (type === "table") return <Table2 size={20} />;
  if (type === "web_tab") return <Globe2 size={20} />;
  return <Database size={20} />;
}

function viewTitle(view: View) {
  if (view === "positions") return "Holdings / Positions";
  if (view === "orders") return "Orders";
  if (view === "settings") return "Settings";
  return "Workspace";
}

function orderTone(status: string): Tone {
  if (status === "FILLED") return "green";
  if (status === "REJECTED" || status === "SUBMISSION_FAILED") return "red";
  if (status === "SUBMITTED" || status === "SUBMITTING") return "blue";
  if (status === "PARTIALLY_FILLED" || status === "APPROVED") return "amber";
  if (status === "CANCELED") return "slate";
  return "amber";
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item));
}

function formatKrw(value: MoneyValue | unknown) {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0
  }).format(Number(value ?? 0));
}

function formatPercent(value: number) {
  return `${Math.round(Number(value) * 100)}%`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatValue(value: unknown) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (value === null || value === undefined) {
    return "-";
  }
  return String(value);
}
