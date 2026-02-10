"use client";

import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/utils/supabase";

type LedgerRow = {
  id: number;
  amount: number;
  created_at: string;
  reversed: boolean | null;
  raw_text: string | null;
  transcript: string | null;
  customers: { name: string }[] | null;
};

const formatAmount = (value: number) => {
  const sign = value < 0 ? "-" : "";
  return `${sign}Rs ${Math.abs(value).toFixed(0)}`;
};

export default function Home() {
  const [rows, setRows] = useState<LedgerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetchLedger = async () => {
      setLoading(true);
      const { data, error } = await supabase
        .from("udhaar_entries")
        .select("id, amount, created_at, reversed, raw_text, transcript, customers(name)")
        .order("created_at", { ascending: false });

      if (!active) {
        return;
      }

      if (error) {
        setError(error.message);
      } else {
        setRows((data || []) as LedgerRow[]);
      }
      setLoading(false);
    };

    fetchLedger();
    const interval = setInterval(fetchLedger, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const stats = useMemo(() => {
    const totalUdhar = rows.reduce((sum, row) => sum + (row.amount || 0), 0);
    const todayKey = new Date().toISOString().slice(0, 10);
    const todaysSales = rows
      .filter((row) => row.amount > 0 && row.created_at.startsWith(todayKey))
      .reduce((sum, row) => sum + row.amount, 0);
    const activeCustomers = new Set(
      rows
        .map((row) => (row.customers?.[0]?.name || "").trim())
        .filter(Boolean),
    ).size;
    return { totalUdhar, todaysSales, activeCustomers };
  }, [rows]);

  return (
    <div className="min-h-screen overflow-hidden bg-[color:var(--background)] text-[color:var(--foreground)]">
      <div className="pointer-events-none absolute inset-0">
        <div className="grain absolute inset-0 opacity-80" />
        <div className="absolute -top-40 -right-24 h-96 w-96 rounded-full bg-emerald-200/60 blur-3xl floaty" />
        <div className="absolute top-44 -left-32 h-72 w-72 rounded-full bg-amber-200/70 blur-3xl floaty" />
      </div>

      <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-14 sm:px-10">
        <section className="rise flex flex-col gap-5 rounded-3xl border border-emerald-900/10 bg-[color:var(--surface)] p-8 shadow-[0_20px_60px_-40px_rgba(16,55,45,0.6)]">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[color:var(--muted)]">
                Voice Khata Admin
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-[color:var(--foreground)] sm:text-4xl">
                Business-level dashboard
              </h1>
              <p className="mt-2 max-w-2xl text-base text-[color:var(--muted)]">
                Monitor udhaar exposure, daily credit sales, and active customers without touching the database.
              </p>
            </div>
            <div className="flex items-center gap-3 rounded-full border border-emerald-900/10 bg-emerald-900/5 px-4 py-2 text-sm font-medium text-emerald-900">
              <span className="inline-flex h-2 w-2 rounded-full bg-emerald-600" />
              Live sync enabled
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-rose-700/80">
                Total udhar
              </p>
              <p className="mt-3 text-3xl font-semibold text-rose-700">
                {formatAmount(stats.totalUdhar)}
              </p>
              <p className="mt-2 text-xs text-rose-700/70">Market mein fasa hua paisa</p>
            </div>
            <div className="rounded-2xl border border-sky-200 bg-sky-50 px-5 py-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700/80">
                Today's sales
              </p>
              <p className="mt-3 text-3xl font-semibold text-sky-700">
                {formatAmount(stats.todaysSales)}
              </p>
              <p className="mt-2 text-xs text-sky-700/70">Aaj ka credit dhandha</p>
            </div>
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700/80">
                Active customers
              </p>
              <p className="mt-3 text-3xl font-semibold text-amber-700">
                {stats.activeCustomers}
              </p>
              <p className="mt-2 text-xs text-amber-700/70">Ledger me total log</p>
            </div>
          </div>
        </section>

        <section className="rise rounded-3xl border border-emerald-900/10 bg-[color:var(--surface)] p-6 shadow-[0_18px_50px_-40px_rgba(16,55,45,0.5)]">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-emerald-900/10 pb-4">
            <div>
              <h2 className="text-xl font-semibold text-[color:var(--foreground)]">Recent activity</h2>
              <p className="text-sm text-[color:var(--muted)]">Newest updates from the WhatsApp webhook.</p>
            </div>
            {loading && <span className="text-sm text-[color:var(--muted)]">Loading ledger...</span>}
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[680px] border-collapse text-left">
              <thead>
                <tr className="text-xs uppercase tracking-[0.2em] text-[color:var(--muted)]">
                  <th className="py-3">Date</th>
                  <th className="py-3">Customer</th>
                  <th className="py-3">Note</th>
                  <th className="py-3 text-right">Amount</th>
                  <th className="py-3 text-right">Type</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const type = row.amount < 0 ? "PAYMENT" : "CREDIT";
                  const note = row.raw_text || row.transcript || "Text entry";
                  return (
                    <tr
                      key={row.id}
                      className="border-t border-emerald-900/10 text-sm text-[color:var(--foreground)]"
                    >
                      <td className="py-4 text-[color:var(--muted)]">
                        {new Date(row.created_at).toLocaleString()}
                      </td>
                      <td className="py-4 font-semibold">
                        {row.customers?.[0]?.name || "Unknown"}
                      </td>
                      <td className="py-4 text-[color:var(--muted)]">
                        {note}
                        {row.reversed ? (
                          <span className="ml-2 inline-flex rounded-full border border-amber-400/40 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-700">
                            reversed
                          </span>
                        ) : null}
                      </td>
                      <td className="py-4 text-right font-semibold">
                        {formatAmount(row.amount)}
                      </td>
                      <td className="py-4 text-right">
                        <span
                          className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] ${
                            type === "CREDIT"
                              ? "bg-rose-100 text-rose-700"
                              : "bg-emerald-100 text-emerald-700"
                          }`}
                        >
                          {type}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {!loading && rows.length === 0 && !error && (
            <div className="py-10 text-center text-sm text-[color:var(--muted)]">
              No entries yet. Send a WhatsApp message to create the first one.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
