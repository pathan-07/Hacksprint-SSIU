"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/utils/supabase";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

/* ── types ─────────────────────────────────────────────────────── */

type CustomerRef = { name: string };

type UdhaarEntry = {
  id: number;
  amount: number | string | null;
  created_at: string;
  transcript: string | null;
  raw_text?: string | null;
  customer_id?: string | number | null;
  shop_phone?: string | null;
  customers: CustomerRef[] | CustomerRef | null;
};

type Stats = {
  totalUdhar: number;
  todaysSales: number;
  estProfit: number;
  activeCustomers: number;
};

/* ── helpers ───────────────────────────────────────────────────── */

const fmt = (v: number) => `Rs ${Math.round(v).toLocaleString()}`;

const safeAmt = (v: UdhaarEntry["amount"]) =>
  typeof v === "number" ? v : Number.parseFloat(String(v ?? "0")) || 0;

const customerName = (entry: UdhaarEntry) => {
  const c = entry.customers;
  if (!c) return "Unknown";
  if (Array.isArray(c)) return c[0]?.name || "Unknown";
  return c.name || "Unknown";
};

/**
 * Backend normalizes to +<digits>. We try multiple variants so the
 * query matches regardless of what format was used during insert.
 */
const phoneVariants = (raw: string): string[] => {
  let digits = raw.replace(/\D/g, "");
  if (!digits) return [];
  if (digits.startsWith("00")) digits = digits.slice(2);
  const withPlus = `+${digits}`;
  const withCountry =
    digits.length === 10 ? [`+91${digits}`, `91${digits}`] : [];
  // Return unique variants: +919…, 919…, +9…, 9… etc.
  return [...new Set([withPlus, digits, ...withCountry])];
};

/* ── component ─────────────────────────────────────────────────── */

export default function RealtimeDashboard() {
  const params = useParams<{ phone?: string | string[] }>();
  const rawPhone = Array.isArray(params?.phone)
    ? params.phone[0]
    : params?.phone;
  const decoded = rawPhone ? decodeURIComponent(rawPhone) : "";
  const variants = useMemo(() => phoneVariants(decoded), [decoded]);

  const [entries, setEntries] = useState<UdhaarEntry[]>([]);
  const [initialLoad, setInitialLoad] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [rtStatus, setRtStatus] = useState("connecting");
  const [matchedPhone, setMatchedPhone] = useState("");
  const [debugLog, setDebugLog] = useState<string[]>([]);
  const activeRef = useRef(true);

  const log = useCallback(
    (msg: string) => {
      const ts = new Date().toLocaleTimeString();
      const line = `[${ts}] ${msg}`;
      console.log(line);
      setDebugLog((prev) => [line, ...prev].slice(0, 30));
    },
    [],
  );

  /* ── derived stats ──────────────────────────────────────────── */

  const stats = useMemo<Stats>(() => {
    const totalUdhar = entries.reduce((s, e) => s + safeAmt(e.amount), 0);
    const todayKey = new Date().toISOString().slice(0, 10);
    const todaysSales = entries
      .filter((e) => e.created_at?.startsWith(todayKey))
      .reduce((s, e) => s + safeAmt(e.amount), 0);
    const activeCustomers = new Set(
      entries
        .map((e) => e.customer_id)
        .filter((v) => v != null),
    ).size;
    return {
      totalUdhar,
      todaysSales,
      estProfit: Math.floor(todaysSales * 0.2),
      activeCustomers,
    };
  }, [entries]);

  const chartData = useMemo(() => {
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - i);
      return d.toISOString().slice(0, 10);
    }).reverse();
    return days.map((date) => ({
      date: new Date(date).toLocaleDateString("en-IN", { weekday: "short" }),
      sales: entries
        .filter((e) => e.created_at?.startsWith(date))
        .reduce((s, e) => s + safeAmt(e.amount), 0),
    }));
  }, [entries]);

  /* ── data fetching ──────────────────────────────────────────── */

  useEffect(() => {
    if (!variants.length) return;
    activeRef.current = true;

    const tryFetch = async (selectQuery: string, phone?: string) => {
      let query = supabase
        .from("udhaar_entries")
        .select(selectQuery)
        .order("created_at", { ascending: false })
        .limit(50);
      if (phone) query = query.eq("shop_phone", phone);
      return query;
    };

    const fetchData = async (isFirstLoad = false) => {
      log(`Fetching for variants: ${variants.join(", ")}`);

      // Strategy 1: Try each phone variant with join
      for (const phone of variants) {
        const { data, error } = await tryFetch("*, customers(name)", phone);
        if (!activeRef.current) return;
        if (error) {
          log(`Join query error for ${phone}: ${error.message} (${error.code})`);
          // Try without join
          const { data: d2, error: e2 } = await tryFetch("*", phone);
          if (!activeRef.current) return;
          if (e2) {
            log(`Plain query error for ${phone}: ${e2.message} (${e2.code})`);
            setFetchError(e2.message);
            continue;
          }
          if (d2 && d2.length > 0) {
            log(`Found ${d2.length} entries (no join) for shop_phone=${phone}`);
            setMatchedPhone(phone);
            setEntries(d2 as unknown as UdhaarEntry[]);
            setFetchError(null);
            if (isFirstLoad) setInitialLoad(false);
            return;
          }
          continue;
        }
        if (data && data.length > 0) {
          log(`Found ${data.length} entries for shop_phone=${phone}`);
          setMatchedPhone(phone);
          setEntries(data as unknown as UdhaarEntry[]);
          setFetchError(null);
          if (isFirstLoad) setInitialLoad(false);
          return;
        }
      }

      // Strategy 2: Fetch ALL entries (no filter) to diagnose
      log("No match. Fetching ALL entries (no phone filter)...");
      const { data: allData, error: allError } = await tryFetch("*");
      if (!activeRef.current) return;

      if (allError) {
        log(`Error fetching all: ${allError.message} (${allError.code})`);
        setFetchError(`DB error: ${allError.message}. Check Supabase RLS policies or API key.`);
        if (isFirstLoad) setInitialLoad(false);
        return;
      }

      if (allData && allData.length > 0) {
        const phones = [...new Set((allData as unknown as Record<string, unknown>[]).map((r) => r.shop_phone))];
        log(`Found ${allData.length} total entries. shop_phone values in DB: ${phones.join(", ")}`);
        setMatchedPhone(`ALL (DB phones: ${phones.join(", ")})`);
        setEntries(allData as unknown as UdhaarEntry[]);
        setFetchError(`Phone mismatch! URL=${decoded} but DB has: ${phones.join(", ")}`);
      } else {
        log("udhaar_entries table is EMPTY or blocked by RLS.");
        setFetchError("Table empty or RLS blocking reads. Check Supabase Dashboard > Authentication > Policies.");
        setEntries([]);
      }

      if (isFirstLoad) setInitialLoad(false);
    };

    fetchData(true);

    // Realtime subscription (no filter so we catch any insert)
    const channel = supabase
      .channel("dashboard-realtime")
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "udhaar_entries",
        },
        (payload) => {
          log(`Realtime event: ${payload.eventType} id=${(payload.new as Record<string, unknown>)?.id ?? "?"}`);
          // Refetch on any change
          fetchData(false);
        },
      )
      .subscribe((status) => {
        log(`Realtime status: ${status}`);
        setRtStatus(status);
      });

    // Polling fallback every 5s
    const poll = setInterval(() => fetchData(false), 5000);

    return () => {
      activeRef.current = false;
      clearInterval(poll);
      supabase.removeChannel(channel);
    };
  }, [variants, log]);

  /* ── render ─────────────────────────────────────────────────── */

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">
              Live Shop Monitor
            </h1>
            <p className="text-sm text-gray-500">
              Phone: {decoded} | Querying: {matchedPhone || variants.join(", ")}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold ${
                rtStatus === "SUBSCRIBED"
                  ? "bg-green-100 text-green-700"
                  : "bg-yellow-100 text-yellow-700"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  rtStatus === "SUBSCRIBED" ? "bg-green-600" : "bg-yellow-500"
                }`}
              />
              {rtStatus === "SUBSCRIBED"
                ? "Realtime ON"
                : `${rtStatus} (polling)`}
            </span>
            <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-bold text-blue-700">
              {entries.length} rows
            </span>
          </div>
        </div>

        {/* Error banner */}
        {fetchError && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <strong>Error:</strong> {fetchError}
          </div>
        )}

        {/* Stats cards */}
        <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-4">
          <div className="rounded-xl border-l-4 border-blue-500 bg-white p-6 shadow-sm">
            <p className="text-xs font-bold uppercase text-gray-500">
              Today&#39;s Sales
            </p>
            <h2 className="mt-1 text-3xl font-bold text-gray-800">
              {fmt(stats.todaysSales)}
            </h2>
          </div>
          <div className="rounded-xl border-l-4 border-red-500 bg-white p-6 shadow-sm">
            <p className="text-xs font-bold uppercase text-gray-500">
              Total Market Udhar
            </p>
            <h2 className="mt-1 text-3xl font-bold text-gray-800">
              {fmt(stats.totalUdhar)}
            </h2>
          </div>
          <div className="rounded-xl border-l-4 border-green-500 bg-white p-6 shadow-sm">
            <p className="text-xs font-bold uppercase text-gray-500">
              Est. Profit (20%)
            </p>
            <h2 className="mt-1 text-3xl font-bold text-green-600">
              ~{fmt(stats.estProfit)}
            </h2>
          </div>
          <div className="rounded-xl border-l-4 border-purple-500 bg-white p-6 shadow-sm">
            <p className="text-xs font-bold uppercase text-gray-500">
              Active Customers
            </p>
            <h2 className="mt-1 text-3xl font-bold text-gray-800">
              {stats.activeCustomers}
            </h2>
          </div>
        </div>

        {/* Chart + Transactions */}
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div className="min-w-0 rounded-xl bg-white p-6 shadow-sm lg:col-span-2">
            <h3 className="mb-4 font-bold text-gray-700">
              Weekly Sales Trend
            </h3>
            <div style={{ width: "100%", height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={chartData}>
                  <XAxis dataKey="date" stroke="#888" fontSize={12} />
                  <YAxis stroke="#888" fontSize={12} />
                  <Tooltip />
                  <Bar
                    dataKey="sales"
                    fill="#3b82f6"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl bg-white shadow-sm">
            <div className="border-b border-gray-200 bg-gray-100 px-6 py-4">
              <h3 className="font-bold text-gray-700">
                Recent Transactions
              </h3>
            </div>
            <div className="h-96 overflow-y-auto">
              {initialLoad ? (
                <p className="p-6 text-center text-gray-500">Loading...</p>
              ) : entries.length === 0 ? (
                <p className="p-6 text-center text-gray-400">
                  No entries yet. Send a WhatsApp message to create data.
                </p>
              ) : (
                entries.map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-center justify-between border-b border-gray-100 p-4 transition hover:bg-blue-50"
                  >
                    <div>
                      <p className="font-bold text-gray-800">
                        {customerName(entry)}
                      </p>
                      <p className="text-xs text-gray-500">
                        {new Date(entry.created_at).toLocaleTimeString()}
                      </p>
                      <p className="text-xs italic text-gray-400">
                        {entry.transcript || entry.raw_text || "Audio note"}
                      </p>
                    </div>
                    <span className="font-bold text-red-600">
                      {fmt(safeAmt(entry.amount))}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Debug panel (open by default for troubleshooting) */}
        <details className="mt-8 rounded-xl bg-white p-4 shadow-sm" open>
          <summary className="cursor-pointer text-sm font-bold text-gray-500">
            Debug Log (click to expand)
          </summary>
          <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-gray-900 p-3 text-xs text-green-400">
            {debugLog.length ? debugLog.join("\n") : "No logs yet..."}
          </pre>
        </details>
      </div>
    </div>
  );
}
