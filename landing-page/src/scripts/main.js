function $(selector, root = document) {
	return root.querySelector(selector);
}

function $all(selector, root = document) {
	return Array.from(root.querySelectorAll(selector));
}

function clamp(n, min, max) {
	return Math.max(min, Math.min(max, n));
}

function setBadge(badge, text, kind) {
	badge.classList.remove("ok", "bad");
	if (kind) badge.classList.add(kind);
	badge.textContent = text;
}

function normalizeBackendUrl(url) {
	const trimmed = (url || "").trim();
	if (!trimmed) return "";
	return trimmed.replace(/\/+$/, "");
}

function buildDemoScript(input) {
	const t = (input || "").trim();
	const lower = t.toLowerCase();

	const lines = [];
	lines.push(`> user: ${t || "(empty)"}`);
	lines.push("-");

	if (!t) {
		lines.push("bot: Please type something like: 'Ramesh ko 200 udhaar'.");
		return lines.join("\n");
	}

	// Lightweight heuristics to mimic the backend intents.
	const looksLikeUndo = /\bundo\b/.test(lower);
	const looksLikeSummary = /\bsummary\b|hisaab|khata/.test(lower);
	const looksLikeTotal = /\btotal\b|kitna|kitni/.test(lower);
	const amountMatch = t.match(/(\d+(?:\.\d+)?)/);
	const amount = amountMatch ? Number(amountMatch[1]) : null;

	// Extract a "customer" by taking words before amount or before 'ka/ki/ko'.
	let customer = "";
	const koIdx = lower.indexOf(" ko ");
	const kaIdx = lower.indexOf(" ka ");
	const kiIdx = lower.indexOf(" ki ");
	const amountIdx = amountMatch ? lower.indexOf(amountMatch[1].toLowerCase()) : -1;

	if (koIdx > 0) customer = t.slice(0, koIdx).trim();
	else if (kaIdx > 0) customer = t.slice(0, kaIdx).trim();
	else if (kiIdx > 0) customer = t.slice(0, kiIdx).trim();
	else if (amountIdx > 0) customer = t.slice(0, amountIdx).trim();

	// If user wrote “Ramesh ...” keep first word as name.
	if (!customer) {
		customer = t.split(/\s+/).slice(0, 1).join(" ").trim();
	}
	customer = customer.replace(/[?!.]+$/g, "").trim();

	if (looksLikeUndo) {
		lines.push("bot: Confirm undo last entry? Reply YES or NO.");
		lines.push("bot: (on YES) Done. Last entry has been undone (marked reversed).\n");
		return lines.join("\n");
	}

	if (looksLikeSummary) {
		lines.push("bot: Udhaar summary:");
		lines.push("bot: - Ramesh: ₹200");
		lines.push("bot: - Sita: ₹150");
		lines.push("bot: - ... (top 10)\n");
		return lines.join("\n");
	}

	if (looksLikeTotal) {
		lines.push(`bot: ${customer || "Customer"} total: Net ₹200`);
		lines.push("bot: (demo response)\n");
		return lines.join("\n");
	}

	// Default: treat as add udhaar if has amount.
	if (amount !== null && Number.isFinite(amount)) {
		const rounded = Number.isInteger(amount) ? String(amount) : amount.toFixed(2);
		lines.push(`bot: Confirm: Add ₹${rounded} udhaar for ${customer || "(name)"}? Reply YES or NO.`);
		lines.push("bot: (on YES) Done. Added entry to ledger.");
		return lines.join("\n");
	}

	lines.push("bot: I couldn't understand confidently. Please repeat with customer name and amount.");
	lines.push("bot: Example: 'Ramesh ko 200 udhaar'\n");
	return lines.join("\n");
}

function prettyJson(obj) {
	try {
		return JSON.stringify(obj, null, 2);
	} catch {
		return String(obj);
	}
}

async function apiJson(url, options) {
	const res = await fetch(url, {
		headers: { "Content-Type": "application/json" },
		...options,
	});
	const text = await res.text();
	let data = null;
	try {
		data = text ? JSON.parse(text) : null;
	} catch {
		data = { raw: text };
	}
	if (!res.ok) {
		const detail = data && (data.detail || data.message);
		const msg = detail ? String(detail) : `HTTP ${res.status}`;
		const err = new Error(msg);
		err.status = res.status;
		err.data = data;
		throw err;
	}
	return data;
}

async function apiForm(url, formData) {
	const res = await fetch(url, { method: "POST", body: formData });
	const text = await res.text();
	let data = null;
	try {
		data = text ? JSON.parse(text) : null;
	} catch {
		data = { raw: text };
	}
	if (!res.ok) {
		const detail = data && (data.detail || data.message);
		const msg = detail ? String(detail) : `HTTP ${res.status}`;
		const err = new Error(msg);
		err.status = res.status;
		err.data = data;
		throw err;
	}
	return data;
}

function renderLedgerRows(tbody, entries) {
	tbody.innerHTML = "";
	if (!entries || entries.length === 0) {
		const tr = document.createElement("tr");
		tr.innerHTML = `<td colspan="4" class="muted">No entries yet.</td>`;
		tbody.appendChild(tr);
		return;
	}

	for (const e of entries) {
		const reversed = !!e.reversed;
		const status = reversed
			? '<span class="pill-badge rev">reversed</span>'
			: '<span class="pill-badge">active</span>';
		const amount = Number(e.amount);
		const amountStr = Number.isFinite(amount) ? `₹${Math.round(amount)}` : "—";
		const tr = document.createElement("tr");
		tr.innerHTML = `
			<td>${e.id ?? "—"}</td>
			<td>${(e.customer_name || "").toString()}</td>
			<td>${amountStr}</td>
			<td>${status}</td>
		`;
		tbody.appendChild(tr);
	}
}

function animateCounters() {
	const items = $all("[data-counter]");
	if (!items.length) return;

	const start = performance.now();
	const durationMs = 900;

	function tick(now) {
		const t = clamp((now - start) / durationMs, 0, 1);
		const eased = 1 - Math.pow(1 - t, 3);

		for (const el of items) {
			const target = Number(el.getAttribute("data-counter") || "0");
			const val = Math.round(target * eased);
			el.textContent = String(val);
		}

		if (t < 1) requestAnimationFrame(tick);
	}

	requestAnimationFrame(tick);
}

function setupMenu() {
	const menuBtn = $("[data-menu-button]");
	const nav = $("[data-nav]");
	if (!menuBtn || !nav) return;

	function setOpen(open) {
		nav.setAttribute("data-open", open ? "true" : "false");
		menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
	}

	menuBtn.addEventListener("click", () => {
		const open = nav.getAttribute("data-open") === "true";
		setOpen(!open);
	});

	// Close on nav click (mobile)
	nav.addEventListener("click", (e) => {
		const a = e.target && e.target.closest ? e.target.closest("a") : null;
		if (a) setOpen(false);
	});

	// Close on escape
	document.addEventListener("keydown", (e) => {
		if (e.key === "Escape") setOpen(false);
	});
}

function setupSmoothScroll() {
	document.addEventListener("click", (e) => {
		const a = e.target && e.target.closest ? e.target.closest('a[href^="#"]') : null;
		if (!a) return;
		const href = a.getAttribute("href");
		if (!href || href === "#") return;
		const id = href.slice(1);
		const target = document.getElementById(id);
		if (!target) return;

		e.preventDefault();
		target.scrollIntoView({ behavior: "smooth", block: "start" });
		history.replaceState(null, "", href);
	});

	$all("[data-scroll-to]").forEach((btn) => {
		btn.addEventListener("click", () => {
			const id = btn.getAttribute("data-scroll-to");
			const target = id ? document.getElementById(id) : null;
			if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
		});
	});
}

function setupHealthCheck() {
	const urlInput = $("[data-backend-url]");
	const btn = $("[data-health-check]");
	const badge = $("[data-health-badge]");
	const docsLink = $("[data-docs-link]");
	const healthLink = $("[data-health-link]");
	if (!urlInput || !btn || !badge) return;

	function syncLinks() {
		const base = normalizeBackendUrl(urlInput.value) || "http://localhost:8000";
		if (docsLink) docsLink.setAttribute("href", `${base}/docs`);
		if (healthLink) healthLink.setAttribute("href", `${base}/health`);
	}

	async function check() {
		const base = normalizeBackendUrl(urlInput.value);
		if (!base) {
			setBadge(badge, "Missing URL", "bad");
			return;
		}

		setBadge(badge, "Checking…", null);
		try {
			const res = await fetch(`${base}/health`, { method: "GET" });
			if (!res.ok) {
				setBadge(badge, `HTTP ${res.status}`, "bad");
				return;
			}
			const data = await res.json().catch(() => ({}));
			if (data && data.status === "ok") {
				setBadge(badge, "API: OK", "ok");
			} else {
				setBadge(badge, "API: Unknown", null);
			}
		} catch (err) {
			setBadge(badge, "Offline / CORS", "bad");
		}
	}

	btn.addEventListener("click", check);
	urlInput.addEventListener("change", syncLinks);
	urlInput.addEventListener("input", () => {
		// Keep it lightweight; no network calls on every keystroke.
		syncLinks();
	});

	syncLinks();
}

function setupDemoSimulator() {
	const input = $("[data-demo-text]");
	const runBtn = $("[data-demo-run]");
	const output = $("[data-demo-output]");
	const copyBtn = $("[data-copy-demo]");
	const chips = $all("[data-demo-chip]");
	const shopPhoneInput = $("[data-shop-phone]");
	const pendingIdEl = $("[data-pending-id]");
	const yesBtn = $("[data-confirm-yes]");
	const noBtn = $("[data-confirm-no]");
	const refreshLedgerBtn = $("[data-refresh-ledger]");
	const ledgerBody = $("[data-ledger-body]");
	const backendUrlInput = $("[data-backend-url]");
	const voiceStartBtn = $("[data-voice-start]");
	const voiceStopBtn = $("[data-voice-stop]");
	const voiceAudio = $("[data-voice-audio]");
	if (!input || !runBtn || !output) return;

	let lastPendingId = null;
	let ledgerTimer = null;

	function setPending(id) {
		lastPendingId = typeof id === "number" ? id : null;
		if (pendingIdEl) pendingIdEl.textContent = lastPendingId ? String(lastPendingId) : "—";
		if (yesBtn) yesBtn.disabled = !lastPendingId;
		if (noBtn) noBtn.disabled = !lastPendingId;
	}

	function baseUrl() {
		const raw = backendUrlInput ? backendUrlInput.value : "http://localhost:8000";
		return normalizeBackendUrl(raw) || "http://localhost:8000";
	}

	function shopPhone() {
		return (shopPhoneInput ? shopPhoneInput.value : "+919999999999").trim() || "+919999999999";
	}

	// --- Voice recording (MediaRecorder) ---
	let mediaRecorder = null;
	let mediaStream = null;
	let recordedChunks = [];

	function canRecordVoice() {
		return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
	}

	function setVoiceButtons(recording) {
		if (voiceStartBtn) voiceStartBtn.disabled = !!recording;
		if (voiceStopBtn) voiceStopBtn.disabled = !recording;
	}

	function pickMimeType() {
		const candidates = [
			"audio/webm;codecs=opus",
			"audio/webm",
			"audio/ogg;codecs=opus",
			"audio/ogg",
		];
		for (const t of candidates) {
			try {
				if (MediaRecorder.isTypeSupported(t)) return t;
			} catch {
				// ignore
			}
		}
		return "";
	}

	async function startVoice() {
		if (!canRecordVoice()) {
			output.textContent =
				"Voice recording not supported in this browser. Open in Chrome/Edge (not VS Code Simple Browser).";
			return;
		}

		try {
			setPending(null);
			recordedChunks = [];
			if (voiceAudio) {
				voiceAudio.hidden = true;
				voiceAudio.removeAttribute("src");
			}

			mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
			const mimeType = pickMimeType();
			mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);

			mediaRecorder.ondataavailable = (e) => {
				if (e.data && e.data.size > 0) recordedChunks.push(e.data);
			};

			mediaRecorder.onstop = async () => {
				try {
					const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "audio/webm" });
					const url = URL.createObjectURL(blob);
					if (voiceAudio) {
						voiceAudio.hidden = false;
						voiceAudio.src = url;
					}

					output.textContent = "Uploading voice…";
					const fd = new FormData();
					// Backend expects UploadFile named 'file'
					const ext = (mediaRecorder.mimeType || "").includes("ogg") ? "ogg" : "webm";
					fd.append("file", blob, `voice.${ext}`);
					const endpoint = `${baseUrl()}/demo/voice?shop_phone=${encodeURIComponent(shopPhone())}`;
					const data = await apiForm(endpoint, fd);
					renderLiveResponse(data);
					ensureLedgerAutoRefresh();
					refreshLedger();
				} catch (err) {
					const msg = err && err.message ? String(err.message) : "voice upload failed";
					output.textContent = `Voice upload failed: ${msg}`;
				} finally {
					// cleanup stream
					try {
						if (mediaStream) {
							mediaStream.getTracks().forEach((t) => t.stop());
						}
					} catch {
						// ignore
					}
					mediaStream = null;
					mediaRecorder = null;
					recordedChunks = [];
					setVoiceButtons(false);
				}
			};

			mediaRecorder.start();
			output.textContent = "Recording… speak now.";
			setVoiceButtons(true);
		} catch (err) {
			const name = err && err.name ? String(err.name) : "Error";
			const message = err && err.message ? String(err.message) : String(err);
			output.textContent =
				name === "NotAllowedError"
					? "Mic permission denied. Open in Chrome/Edge and allow microphone."
					: `Mic error: ${message}`;
			setVoiceButtons(false);
			try {
				if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
			} catch {}
			mediaStream = null;
			mediaRecorder = null;
		}
	}

	function stopVoice() {
		try {
			if (mediaRecorder && mediaRecorder.state !== "inactive") {
				output.textContent = "Stopping…";
				mediaRecorder.stop();
				setVoiceButtons(false);
			}
		} catch (err) {
			const msg = err && err.message ? String(err.message) : String(err);
			output.textContent = `Stop failed: ${msg}`;
		}
	}

	async function refreshLedger() {
		if (!ledgerBody) return;
		try {
			const data = await apiJson(`${baseUrl()}/demo/entries?shop_phone=${encodeURIComponent(shopPhone())}&limit=10`, {
				method: "GET",
			});
			renderLedgerRows(ledgerBody, data.entries || []);
		} catch {
			// Non-blocking; leave existing table as-is.
		}
	}

	function ensureLedgerAutoRefresh() {
		if (ledgerTimer) return;
		ledgerTimer = setInterval(refreshLedger, 2000);
	}

	function renderFallback(text, reason) {
		const hint = reason ? `\n\n[fallback] ${reason}` : "\n\n[fallback] offline simulator";
		output.textContent = buildDemoScript(text) + hint;
	}

	function renderLiveResponse(data) {
		// Prefer a friendly message when present.
		const lines = [];
		if (data && data.message) lines.push(`bot: ${data.message}`);
		if (data && data.status) lines.push(`status: ${data.status}`);

		if (data && data.pending_id) {
			lines.push(`pending_id: ${data.pending_id}`);
			setPending(Number(data.pending_id));
		} else {
			setPending(null);
		}

		// Helpful extras for judges
		if (data && data.total != null) lines.push(`total: ${data.total}`);
		if (data && Array.isArray(data.summary)) lines.push(`summary_count: ${data.summary.length}`);
		if (data && data.entry) lines.push(`entry_id: ${data.entry.id ?? "—"}`);

		lines.push("-");
		lines.push(prettyJson(data));
		output.textContent = lines.join("\n");
	}

	function run() {
		// Try live backend demo first; fall back to offline simulator if backend/CORS is not available.
		const text = input.value;
		const payload = { shop_phone: shopPhone(), text };

		output.textContent = "Running…";
		apiJson(`${baseUrl()}/demo/text`, {
			method: "POST",
			body: JSON.stringify(payload),
		})
			.then((data) => {
				renderLiveResponse(data);
				ensureLedgerAutoRefresh();
				refreshLedger();
			})
			.catch((err) => {
				const msg = err && err.message ? String(err.message) : "backend unavailable";
				renderFallback(text, msg);
				setPending(null);
			});
	}

	runBtn.addEventListener("click", run);
	input.addEventListener("keydown", (e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			run();
		}
	});

	for (const chip of chips) {
		chip.addEventListener("click", () => {
			input.value = chip.getAttribute("data-demo-chip") || "";
			run();
		});
	}

	async function confirm(decision) {
		if (!lastPendingId) return;
		output.textContent = `Confirming ${decision}…`;
		try {
			const data = await apiJson(`${baseUrl()}/demo/confirm`, {
				method: "POST",
				body: JSON.stringify({ pending_id: lastPendingId, decision }),
			});
			renderLiveResponse(data);
			setPending(null);
			ensureLedgerAutoRefresh();
			refreshLedger();
		} catch (err) {
			const msg = err && err.message ? String(err.message) : "confirm failed";
			output.textContent = `Confirm failed: ${msg}`;
		}
	}

	if (yesBtn) yesBtn.addEventListener("click", () => confirm("YES"));
	if (noBtn) noBtn.addEventListener("click", () => confirm("NO"));
	if (refreshLedgerBtn) refreshLedgerBtn.addEventListener("click", refreshLedger);

	if (voiceStartBtn) voiceStartBtn.addEventListener("click", startVoice);
	if (voiceStopBtn) voiceStopBtn.addEventListener("click", stopVoice);

	// Initial state
	setVoiceButtons(false);

	if (copyBtn && navigator.clipboard) {
		copyBtn.addEventListener("click", async () => {
			try {
				const text = output.textContent || buildDemoScript(input.value);
				await navigator.clipboard.writeText(text);
				copyBtn.textContent = "Copied";
				setTimeout(() => (copyBtn.textContent = "Copy demo script"), 900);
			} catch {
				copyBtn.textContent = "Copy failed";
				setTimeout(() => (copyBtn.textContent = "Copy demo script"), 900);
			}
		});
	}
}

function setFooterYear() {
	const el = $("[data-year]");
	if (el) el.textContent = String(new Date().getFullYear());
}

document.addEventListener("DOMContentLoaded", () => {
	setFooterYear();
	animateCounters();
	setupMenu();
	setupSmoothScroll();
	setupHealthCheck();
	setupDemoSimulator();
});