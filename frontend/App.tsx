import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { CheckCircle2, Play, RefreshCw, ShieldAlert } from "lucide-react-native";
import { StatusBar } from "expo-status-bar";

import { ApiClient, DecisionResponse, OrderView, PositionView, PublicConfig } from "./src/api/client";
import { colors, spacing } from "./src/theme";

type Tab = "dashboard" | "agents" | "orders";

export default function App() {
  const api = useMemo(() => new ApiClient(), []);
  const [tab, setTab] = useState<Tab>("dashboard");
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [positions, setPositions] = useState<PositionView[]>([]);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [symbol, setSymbol] = useState("A005930");
  const [quantity, setQuantity] = useState("1");
  const [lastPrice, setLastPrice] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    const [nextConfig, nextOrders, nextPositions] = await Promise.all([
      api.config(),
      api.orders(),
      api.positions()
    ]);
    setConfig(nextConfig);
    setOrders(nextOrders);
    setPositions(nextPositions);
  }

  useEffect(() => {
    refresh().catch((error) => Alert.alert("API error", String(error)));
  }, []);

  async function runDecision() {
    setLoading(true);
    try {
      const response = await api.runDecision({
        symbol,
        quantity: Number(quantity || 0),
        last_price: lastPrice ? Number(lastPrice) : undefined
      });
      setDecision(response);
      setTab("agents");
      await refresh();
    } catch (error) {
      Alert.alert("Decision failed", String(error));
    } finally {
      setLoading(false);
    }
  }

  async function approve(orderId: number) {
    setLoading(true);
    try {
      await api.approveOrder(orderId);
      await refresh();
    } catch (error) {
      Alert.alert("Approval failed", String(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.page}>
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>Trade-pilot</Text>
            <Text style={styles.subtitle}>{config?.openai_model ?? "loading"}</Text>
          </View>
          <Pressable style={styles.iconButton} onPress={() => refresh()}>
            <RefreshCw color={colors.ink} size={20} />
          </Pressable>
        </View>

        <View style={styles.statusRow}>
          <StatusPill label={config?.broker_mode ?? "paper"} tone="blue" />
          <StatusPill label={config?.auto_execute ? "auto" : "manual"} tone="amber" />
          <StatusPill label={config?.live_trading_enabled ? "live" : "guarded"} tone="green" />
        </View>

        <View style={styles.tabs}>
          <TabButton label="Dashboard" active={tab === "dashboard"} onPress={() => setTab("dashboard")} />
          <TabButton label="Agents" active={tab === "agents"} onPress={() => setTab("agents")} />
          <TabButton label="Orders" active={tab === "orders"} onPress={() => setTab("orders")} />
        </View>

        {tab === "dashboard" && (
          <View style={styles.section}>
            <View style={styles.metrics}>
              <Metric label="Max order" value={`${config?.max_order_krw ?? 0}`} />
              <Metric label="Position cap" value={`${config?.max_position_krw ?? 0}`} />
              <Metric label="Confidence" value={`${config?.min_decision_confidence ?? 0}`} />
            </View>

            <View style={styles.tradePanel}>
              <Text style={styles.sectionTitle}>Decision Request</Text>
              <TextInput value={symbol} onChangeText={setSymbol} autoCapitalize="characters" style={styles.input} />
              <View style={styles.formRow}>
                <TextInput
                  value={quantity}
                  onChangeText={setQuantity}
                  keyboardType="number-pad"
                  style={[styles.input, styles.flex]}
                />
                <TextInput
                  value={lastPrice}
                  onChangeText={setLastPrice}
                  keyboardType="decimal-pad"
                  placeholder="price"
                  style={[styles.input, styles.flex]}
                />
              </View>
              <Pressable style={styles.primaryButton} onPress={runDecision} disabled={loading}>
                {loading ? <ActivityIndicator color="#fff" /> : <Play color="#fff" size={18} />}
                <Text style={styles.primaryText}>Run AI Decision</Text>
              </Pressable>
            </View>

            <View style={styles.list}>
              <Text style={styles.sectionTitle}>Positions</Text>
              {positions.length === 0 ? <Text style={styles.muted}>No positions</Text> : null}
              {positions.map((position) => (
                <View key={position.symbol} style={styles.rowCard}>
                  <View>
                    <Text style={styles.rowTitle}>{position.symbol}</Text>
                    <Text style={styles.muted}>{position.quantity} shares</Text>
                  </View>
                  <Text style={styles.money}>{position.market_price}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {tab === "agents" && (
          <View style={styles.section}>
            {decision ? (
              <>
                <View style={styles.decisionHeader}>
                  <View>
                    <Text style={styles.sectionTitle}>{decision.decision.symbol}</Text>
                    <Text style={styles.bigAction}>{decision.decision.action}</Text>
                  </View>
                  <StatusPill label={decision.risk_status} tone={decision.risk_status === "APPROVED" ? "green" : "red"} />
                </View>
                <Text style={styles.thesis}>{decision.decision.thesis}</Text>
                {decision.decision.agent_votes.map((vote) => (
                  <View key={vote.role} style={styles.rowCard}>
                    <View style={styles.voteIcon}>
                      {vote.verdict === "block" ? (
                        <ShieldAlert color={colors.red} size={18} />
                      ) : (
                        <CheckCircle2 color={colors.green} size={18} />
                      )}
                    </View>
                    <View style={styles.flex}>
                      <Text style={styles.rowTitle}>{vote.role}</Text>
                      <Text style={styles.muted}>{vote.verdict} / {vote.confidence}</Text>
                      <Text style={styles.small}>{vote.reasons.join(" ")}</Text>
                    </View>
                  </View>
                ))}
              </>
            ) : (
              <Text style={styles.muted}>No decision yet</Text>
            )}
          </View>
        )}

        {tab === "orders" && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Orders</Text>
            {orders.length === 0 ? <Text style={styles.muted}>No orders</Text> : null}
            {orders.map((order) => (
              <View key={order.id} style={styles.rowCard}>
                <View style={styles.flex}>
                  <Text style={styles.rowTitle}>{order.symbol} {order.side}</Text>
                  <Text style={styles.muted}>{order.status} / {order.quantity} shares</Text>
                  <Text style={styles.small}>{order.message ?? ""}</Text>
                </View>
                {order.status === "PENDING_APPROVAL" ? (
                  <Pressable style={styles.smallButton} onPress={() => approve(order.id)} disabled={loading}>
                    <CheckCircle2 color="#fff" size={16} />
                  </Pressable>
                ) : null}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function TabButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.tab, active && styles.activeTab]}>
      <Text style={[styles.tabText, active && styles.activeTabText]}>{label}</Text>
    </Pressable>
  );
}

function StatusPill({ label, tone }: { label: string; tone: "blue" | "green" | "amber" | "red" }) {
  return (
    <View style={[styles.pill, styles[`${tone}Pill`]]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.background
  },
  page: {
    padding: spacing.lg,
    gap: spacing.lg
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center"
  },
  title: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: "800"
  },
  subtitle: {
    color: colors.muted,
    fontSize: 14,
    marginTop: 2
  },
  iconButton: {
    width: 42,
    height: 42,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface
  },
  statusRow: {
    flexDirection: "row",
    gap: spacing.sm,
    flexWrap: "wrap"
  },
  tabs: {
    flexDirection: "row",
    padding: 4,
    borderRadius: 8,
    backgroundColor: colors.soft,
    gap: 4
  },
  tab: {
    flex: 1,
    minHeight: 40,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center"
  },
  activeTab: {
    backgroundColor: colors.surface
  },
  tabText: {
    color: colors.muted,
    fontWeight: "700"
  },
  activeTabText: {
    color: colors.ink
  },
  section: {
    gap: spacing.lg
  },
  metrics: {
    flexDirection: "row",
    gap: spacing.sm
  },
  metric: {
    flex: 1,
    minHeight: 82,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    padding: spacing.md,
    justifyContent: "space-between"
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700"
  },
  metricValue: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800"
  },
  tradePanel: {
    gap: spacing.md,
    paddingVertical: spacing.sm
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800"
  },
  input: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: spacing.md,
    color: colors.ink,
    backgroundColor: colors.surface
  },
  formRow: {
    flexDirection: "row",
    gap: spacing.sm
  },
  flex: {
    flex: 1
  },
  primaryButton: {
    minHeight: 48,
    borderRadius: 8,
    backgroundColor: colors.blue,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: spacing.sm
  },
  primaryText: {
    color: "#fff",
    fontWeight: "800"
  },
  list: {
    gap: spacing.sm
  },
  rowCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    minHeight: 74,
    padding: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md
  },
  rowTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800"
  },
  muted: {
    color: colors.muted
  },
  small: {
    color: colors.ink,
    fontSize: 12,
    marginTop: 4,
    lineHeight: 18
  },
  money: {
    color: colors.ink,
    fontWeight: "800"
  },
  decisionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  bigAction: {
    color: colors.blue,
    fontSize: 34,
    fontWeight: "900",
    marginTop: 4
  },
  thesis: {
    color: colors.ink,
    lineHeight: 22,
    paddingVertical: spacing.sm
  },
  voteIcon: {
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.soft
  },
  smallButton: {
    width: 38,
    height: 38,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.green
  },
  pill: {
    minHeight: 30,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    alignItems: "center",
    justifyContent: "center"
  },
  pillText: {
    color: colors.ink,
    fontWeight: "800",
    fontSize: 12
  },
  bluePill: {
    backgroundColor: "#dbeafe"
  },
  greenPill: {
    backgroundColor: "#dcfce7"
  },
  amberPill: {
    backgroundColor: "#fef3c7"
  },
  redPill: {
    backgroundColor: "#fee2e2"
  }
});
