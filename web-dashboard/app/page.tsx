export default function Home() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="text-lg font-bold tracking-tight">VoiceKhata</div>
          <nav className="hidden gap-6 text-sm text-slate-300 md:flex">
            <a href="#problem" className="hover:text-white">Problem</a>
            <a href="#solution" className="hover:text-white">Solution</a>
            <a href="#use-cases" className="hover:text-white">Use Cases</a>
            <a href="#demo" className="hover:text-white">Demo</a>
            <a href="#stack" className="hover:text-white">Stack</a>
          </nav>
          <a href="#demo" className="rounded-xl border border-cyan-300/40 bg-cyan-300/10 px-4 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-300/20">See demo</a>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -top-36 -left-20 h-80 w-80 rounded-full bg-cyan-400/20 blur-3xl" />
            <div className="absolute -top-28 right-0 h-80 w-80 rounded-full bg-violet-400/20 blur-3xl" />
          </div>
          <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 md:grid-cols-2 md:py-24">
            <div className="relative z-10">
              <p className="inline-flex rounded-full border border-white/20 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-300">Hackathon-ready demo</p>
              <h1 className="mt-4 text-4xl font-bold leading-tight tracking-tight md:text-5xl">Track udhaar with voice notes on WhatsApp.</h1>
              <p className="mt-4 max-w-xl text-slate-300">VoiceKhata converts everyday messages into a clean ledger with confirmation-first safety, live summaries, inventory restock, and secure customer bill links.</p>
              <ul className="mt-5 space-y-2 text-sm text-slate-200">
                <li>• Works with normal WhatsApp messages</li>
                <li>• YES/NO confirmation before save</li>
                <li>• Snap-to-Inventory from bill images</li>
              </ul>
              <div className="mt-6 flex flex-wrap gap-3">
                <a href="#demo" className="rounded-xl bg-cyan-400 px-5 py-3 text-sm font-bold text-slate-900 hover:bg-cyan-300">Try demo flow</a>
                <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="rounded-xl border border-white/20 px-5 py-3 text-sm font-semibold hover:bg-white/10">Open API docs</a>
              </div>
            </div>

            <div className="relative z-10 rounded-2xl border border-white/15 bg-white/5 p-5 shadow-2xl">
              <div className="space-y-3 text-sm">
                <div className="rounded-xl bg-white/10 p-3">Bhai, Ramesh ko 200 udhaar</div>
                <div className="rounded-xl bg-cyan-300/20 p-3">Confirm: Add ₹200 udhaar for Ramesh? Reply YES or NO.</div>
                <div className="rounded-xl bg-white/10 p-3">YES ✅</div>
                <div className="rounded-xl bg-cyan-300/20 p-3">Done. Added ₹200 udhaar for Ramesh.</div>
                <div className="rounded-xl bg-white/10 p-3">Ramesh ka total?</div>
                <div className="rounded-xl bg-cyan-300/20 p-3">Ramesh total: Net ₹200</div>
              </div>
            </div>
          </div>
        </section>

        <section className="border-y border-white/10 bg-white/5">
          <div className="mx-auto grid max-w-6xl gap-3 px-6 py-6 md:grid-cols-4">
            <div className="rounded-xl border border-white/10 bg-white/5 p-3"><strong>Voice + Text</strong><div className="text-xs text-slate-300">Input supported end-to-end</div></div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-3"><strong>Confirmation-first</strong><div className="text-xs text-slate-300">Prevents wrong entries</div></div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-3"><strong>Live dashboard</strong><div className="text-xs text-slate-300">Realtime ledger visibility</div></div>
            <div className="rounded-xl border border-white/10 bg-white/5 p-3"><strong>Secure bill links</strong><div className="text-xs text-slate-300">Shareable customer pay page</div></div>
          </div>
        </section>

        <section id="problem" className="mx-auto max-w-6xl px-6 py-14">
          <h2 className="text-3xl font-bold tracking-tight">Problem</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Udhaar is informal</h3><p className="mt-2 text-sm text-slate-300">Notebooks and memory cause confusion and disputes.</p></article>
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Typing is slow</h3><p className="mt-2 text-sm text-slate-300">Rush hours need voice-speed entry, not forms.</p></article>
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Errors are costly</h3><p className="mt-2 text-sm text-slate-300">Wrong name/amount directly hurts trust and cashflow.</p></article>
          </div>
        </section>

        <section id="solution" className="border-y border-white/10 bg-white/5">
          <div className="mx-auto max-w-6xl px-6 py-14">
            <h2 className="text-3xl font-bold tracking-tight">Solution</h2>
            <p className="mt-2 text-slate-300">A WhatsApp-first voice khata with AI extraction and explicit confirmation before save.</p>
            <div className="mt-6 grid gap-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><strong>1. Send voice/text</strong><p className="mt-1 text-sm text-slate-300">Example: “Sita ko 150 udhaar add karo”.</p></div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><strong>2. AI extracts intent</strong><p className="mt-1 text-sm text-slate-300">Customer + amount + action + items when needed.</p></div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4"><strong>3. Confirm to save</strong><p className="mt-1 text-sm text-slate-300">Reply YES/NO to keep ledger safe by default.</p></div>
            </div>
          </div>
        </section>

        <section id="use-cases" className="mx-auto max-w-6xl px-6 py-14">
          <h2 className="text-3xl font-bold tracking-tight">Use Cases</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Fast udhaar entry</h3><p className="mt-2 text-sm text-slate-300">Log dues in seconds from a message.</p></article>
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Snap-to-Inventory</h3><p className="mt-2 text-sm text-slate-300">Scan purchase bill and restock with audit logs.</p></article>
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Secure customer payment</h3><p className="mt-2 text-sm text-slate-300">Share link-based bill page with UPI pay CTA.</p></article>
          </div>
        </section>

        <section id="demo" className="border-y border-white/10 bg-white/5">
          <div className="mx-auto max-w-6xl px-6 py-14">
            <h2 className="text-3xl font-bold tracking-tight">Live Demo (for judges)</h2>
            <p className="mt-2 text-slate-300">Use backend demo endpoints and dashboard routes for quick walkthrough.</p>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <a href="http://localhost:8000/demo/record" target="_blank" rel="noreferrer" className="rounded-2xl border border-white/10 bg-white/5 p-5 hover:bg-white/10">
                <h3 className="font-semibold">Open Voice Demo Recorder</h3>
                <p className="mt-1 text-sm text-slate-300">Test voice pipeline without WhatsApp setup.</p>
              </a>
              <a href="/dashboard/%2B919999999999" className="rounded-2xl border border-white/10 bg-white/5 p-5 hover:bg-white/10">
                <h3 className="font-semibold">Open Live Dashboard</h3>
                <p className="mt-1 text-sm text-slate-300">See realtime udhaar entries and stats.</p>
              </a>
            </div>
          </div>
        </section>

        <section id="stack" className="mx-auto max-w-6xl px-6 py-14">
          <h2 className="text-3xl font-bold tracking-tight">Tech Stack</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">FastAPI</h3><p className="mt-2 text-sm text-slate-300">Webhook and demo API layer.</p></article>
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Supabase</h3><p className="mt-2 text-sm text-slate-300">Ledger + inventory + audit logs.</p></article>
            <article className="rounded-2xl border border-white/10 bg-white/5 p-5"><h3 className="font-semibold">Gemini</h3><p className="mt-2 text-sm text-slate-300">Transcription and intent extraction.</p></article>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 bg-black/20">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-6 text-sm text-slate-300">
          <span>© {new Date().getFullYear()} VoiceKhata</span>
          <div className="flex gap-4">
            <a href="http://localhost:8000/health" target="_blank" rel="noreferrer" className="hover:text-white">API health</a>
            <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:text-white">API docs</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
