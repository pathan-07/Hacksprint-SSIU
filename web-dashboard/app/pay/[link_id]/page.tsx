"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Phone, ShoppingBag } from "lucide-react";
import { supabase } from "@/utils/supabase";

type Customer = {
  id: number;
  name: string;
  shop_phone: string;
  link_id: string;
};

type Entry = {
  id: number;
  amount: number | string | null;
  created_at: string;
  raw_text: string | null;
  transcript: string | null;
  reversed: boolean | null;
};

const toAmount = (v: Entry["amount"]) => {
  if (typeof v === "number") return v;
  return Number.parseFloat(String(v ?? "0")) || 0;
};

const fmt = (v: number) => `₹${Math.abs(v).toFixed(2)}`;

export default function CustomerBillPage() {
  const params = useParams<{ link_id?: string | string[] }>();
  const linkId = Array.isArray(params?.link_id) ? params?.link_id[0] : params?.link_id;

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const fetchBill = async () => {
      if (!linkId) {
        if (active) setLoading(false);
        return;
      }

      const { data: custData } = await supabase
        .from("customers")
        .select("id,name,shop_phone,link_id")
        .eq("link_id", linkId)
        .single();

      if (!active) return;
      if (!custData) {
        setLoading(false);
        return;
      }

      setCustomer(custData as Customer);

      const { data: txnData } = await supabase
        .from("udhaar_entries")
        .select("id,amount,created_at,raw_text,transcript,reversed")
        .eq("customer_id", custData.id)
        .order("created_at", { ascending: false });

      if (!active) return;
      setEntries((txnData || []) as Entry[]);
      setLoading(false);
    };

    fetchBill();
    return () => {
      active = false;
    };
  }, [linkId]);

  const visibleEntries = useMemo(
    () => entries.filter((e) => !e.reversed),
    [entries],
  );

  const pendingAmount = useMemo(
    () => visibleEntries.reduce((sum, e) => sum + toAmount(e.amount), 0),
    [visibleEntries],
  );

  const upiLink = useMemo(() => {
    if (!customer) return "";
    const payee = `${(customer.shop_phone || "").replace(/\D/g, "")}@upi`;
    const amount = Math.max(pendingAmount, 0).toFixed(2);
    return `upi://pay?pa=${encodeURIComponent(payee)}&pn=${encodeURIComponent(customer.name)}&am=${amount}&cu=INR`;
  }, [customer, pendingAmount]);

  if (loading) {
    return <div className="p-10 text-center">Bill load ho raha hai...</div>;
  }

  if (!customer) {
    return <div className="p-10 text-center text-red-500">Invalid Link</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="mx-auto max-w-md overflow-hidden rounded-2xl bg-white shadow-xl">
        <div className="bg-blue-600 p-6 text-center text-white">
          <h2 className="text-xl font-bold">Digital Bill</h2>
          <p className="mt-2 flex items-center justify-center gap-2 text-sm text-blue-100">
            <Phone size={14} /> Shop: {customer.shop_phone}
          </p>
        </div>

        <div className="border-b border-gray-100 p-6 text-center">
          <p className="text-xs font-bold uppercase tracking-wider text-gray-500">Total Pending Amount</p>
          <h1 className="my-4 text-5xl font-bold text-gray-900">₹{pendingAmount.toFixed(2)}</h1>

          <a
            href={upiLink}
            className="block w-full rounded-xl bg-green-600 py-4 font-bold text-white shadow-lg transition active:scale-95 hover:bg-green-700"
          >
            Pay Now via UPI
          </a>
          <p className="mt-3 text-xs text-gray-400">Secure Payment via your UPI App</p>
        </div>

        <div className="bg-gray-50 p-4">
          <h3 className="mb-3 ml-1 text-sm font-bold text-gray-600">Recent Items</h3>
          <div className="space-y-3">
            {visibleEntries.map((t) => {
              const amt = toAmount(t.amount);
              const isCredit = amt >= 0;
              const note = t.raw_text || t.transcript || "Manual Entry";

              return (
                <div key={t.id} className="flex items-center justify-between rounded-lg bg-white p-4 shadow-sm">
                  <div className="flex items-start gap-3">
                    <div
                      className={`rounded-full p-2 ${
                        isCredit ? "bg-red-50 text-red-500" : "bg-green-50 text-green-500"
                      }`}
                    >
                      <ShoppingBag size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-800">{note}</p>
                      <p className="text-xs text-gray-400">{new Date(t.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <span className={`font-bold ${isCredit ? "text-red-600" : "text-green-600"}`}>
                    {isCredit ? "+" : "-"}
                    {fmt(amt)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
