import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Participant = {
  key: string;
  title: string;
  category: string;
  description: string;
  handle: string;
  added: boolean;
  online: boolean;
  affordances: string[];
  health: string | null;
};

type Request = {
  id: string;
  kind: "choose" | "approval" | "input";
  prompt: string;
  detail: { options?: string[]; detail?: unknown; schema?: unknown };
};

type Snapshot = {
  participants: Participant[];
  ready: boolean;
  running: boolean;
  pending: Request | null;
  pace: number;
  reportPath: string;
};

type Log = { id: string; at: number; kind: string; message: string; participant?: string; detail?: string };
type Tab = "participants" | "case" | "log" | "human";

const empty: Snapshot = { participants: [], ready: false, running: false, pending: null, pace: 11, reportPath: "" };

function Icon({ name }: { name: "spark" | "plus" | "play" | "pulse" | "person" | "shield" | "arrow" | "terminal" }) {
  const shape: Record<string, React.ReactNode> = {
    spark: <path d="m12 2 1.8 7.2L21 11l-7.2 1.9L12 20l-1.8-7.1L3 11l7.2-1.8L12 2Z" />,
    plus: <path d="M12 5v14M5 12h14" />,
    play: <path d="m8 5 11 7-11 7V5Z" />,
    pulse: <path d="M3 12h4l2.1-5 4 10 2-5H21" />,
    person: <><circle cx="12" cy="7" r="3.2" /><path d="M5.5 21c.7-4 3-6 6.5-6s5.8 2 6.5 6" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    terminal: <><path d="m5 7 4 4-4 4M12 17h7" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{shape[name]}</svg>;
}

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot>(empty);
  const [tab, setTab] = useState<Tab>("participants");
  const [logs, setLogs] = useState<Log[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const addedCount = snapshot.participants.filter((participant) => participant.added).length;
  const human = snapshot.participants.find((participant) => participant.key === "human");
  const nonHumansReady = snapshot.participants.filter((participant) => participant.key !== "human").every((participant) => participant.added && participant.online);

  const appendLog = (log: Log) => setLogs((items) => [log, ...items].slice(0, 120));
  const refresh = async () => setSnapshot(await api<Snapshot>("/api/status"));

  useEffect(() => {
    refresh().catch((reason: Error) => setError(`Control room unavailable: ${reason.message}`));
    const stream = new EventSource("/events");
    stream.onmessage = (message) => {
      const event = JSON.parse(message.data) as Log & { snapshot?: Snapshot; request?: Request };
      if (event.snapshot) setSnapshot(event.snapshot);
      if (event.request) setSnapshot((current) => ({ ...current, pending: event.request! }));
      appendLog(event);
    };
    stream.onerror = () => setError("Live event stream disconnected. Is the demo command still running?");
    return () => stream.close();
  }, []);

  async function action(label: string, request: () => Promise<Snapshot | { accepted: boolean }>, nextTab?: Tab) {
    setBusy(label);
    setError(null);
    try {
      const response = await request();
      if ("participants" in response) setSnapshot(response);
      else await refresh();
      if (nextTab) setTab(nextTab);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message.replace(/^"|"$/g, "") : "The action failed.");
    } finally {
      setBusy(null);
    }
  }

  function addParticipant(key: string) {
    return action(`add:${key}`, () => api<Snapshot>(`/api/participants/${key}`, { method: "POST" }));
  }

  function answer(value: string | boolean) {
    const request = snapshot.pending;
    if (!request) return;
    return action("human", () => api<{ accepted: boolean }>("/api/human-response", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: request.id, value }) }));
  }

  const statusText = useMemo(() => {
    if (snapshot.running) return snapshot.pending ? "waiting on a human" : "case is running";
    if (snapshot.ready) return "ready to run";
    return `${addedCount} of 6 participants present`;
  }, [addedCount, snapshot.pending, snapshot.ready, snapshot.running]);

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><Icon name="spark" /></span>maiku</div>
      <div className="statusline"><i className={error ? "down" : "up"} />live local runtime <span>·</span> {statusText}</div>
      <button className="quick-button" disabled={busy !== null || nonHumansReady} onClick={() => action("quick", () => api<Snapshot>("/api/quick-load", { method: "POST" }))}><Icon name="plus" />{busy === "quick" ? "loading…" : "quick-load 5"}</button>
    </header>

    <section className="hero">
      <div><span className="eyebrow">A two-minute live constellation</span><h1>Bring different kinds of intelligence into one working room.</h1><p>This is a local product demo: the cards add real Maiku participants, the event stream is live, and you are the human boundary.</p></div>
      <div className="run-card"><span>Prepared case</span><b>Loading-bay evidence review</b><small>11 visible stages · artifacts · a human-gated report write</small><button disabled={!snapshot.ready || snapshot.running || busy !== null} onClick={() => action("run", () => api<Snapshot>("/api/run", { method: "POST" }), "case")}><Icon name="play" />{snapshot.running ? "case in progress" : "run live case"}</button></div>
    </section>

    {error && <div className="error-banner"><b>Attention:</b> {error}<button onClick={() => setError(null)}>dismiss</button></div>}

    <nav className="tabs" aria-label="Demo areas">
      {([ ["participants", "01 Participants"], ["case", "02 Live case"], ["log", "03 Event log"], ["human", "04 Human desk"] ] as [Tab, string][]).map(([key, label]) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}{key === "human" && snapshot.pending && <i />}</button>)}
    </nav>

    <section className="workspace">
      {tab === "participants" && <Participants participants={snapshot.participants} busy={busy} onAdd={addParticipant} onQuick={() => action("quick", () => api<Snapshot>("/api/quick-load", { method: "POST" }))} />}
      {tab === "case" && <Case snapshot={snapshot} onRun={() => action("run", () => api<Snapshot>("/api/run", { method: "POST" }))} busy={busy} />}
      {tab === "log" && <LogView logs={logs} />}
      {tab === "human" && <HumanDesk request={snapshot.pending} human={human} busy={busy} onAdd={() => addParticipant("human")} onAnswer={answer} />}
    </section>

    <footer><Icon name="terminal" /> The demo runs only on this machine. Its report, if approved, lands at <code>{snapshot.reportPath || ".maiku-live-demo/casebook/reports/evidence-report.md"}</code>.</footer>
  </main>;
}

function Participants({ participants, busy, onAdd, onQuick }: { participants: Participant[]; busy: string | null; onAdd: (key: string) => void; onQuick: () => void }) {
  return <><div className="section-heading"><div><span>Participant staging</span><h2>Add the room in public, one native capability at a time.</h2></div><button className="outline" disabled={busy !== null} onClick={onQuick}>autoload the prepared five <Icon name="arrow" /></button></div><div className="participant-grid">{participants.map((participant, index) => <article className={`participant-card ${participant.added ? (participant.online ? "online" : "offline") : "empty"}`} key={participant.key}><div className="card-top"><span>0{index + 1}</span><i>{participant.category}</i></div><h3>{participant.title}</h3><p>{participant.description}</p><div className="handle">{participant.handle}</div>{participant.added ? <div className="connection"><i />{participant.online ? "adapted + healthy" : `added, probe says ${participant.health || "offline"}`}</div> : <button disabled={busy !== null} onClick={() => onAdd(participant.key)}><Icon name="plus" />{busy === `add:${participant.key}` ? "adding…" : `add ${participant.title}`}</button>}<div className="chips">{participant.affordances.length ? participant.affordances.map((item) => <span key={item}>{item}</span>) : <span>adapts on add</span>}</div></article>)}</div><p className="tip"><Icon name="pulse" />Individual add uses the same local adapter/probe path as the shortcut. “Autoload the prepared five” is only there to spare demo setup time; add <b>You</b> separately when you want the case to begin.</p></>;
}

function Case({ snapshot, onRun, busy }: { snapshot: Snapshot; onRun: () => void; busy: string | null }) {
  const states = ["Human sets intent", "CNN creates + classifies an MNIST artifact", "MCP reads case notes + renders a chart", "Verifier and calibrator check the evidence", "Gemma drafts only from established facts", "Human approves or holds the report write"];
  return <><div className="section-heading"><div><span>Loading-bay evidence review</span><h2>A deliberately mixed task, not six chatbots taking turns.</h2></div><span className="case-state">{snapshot.running ? "live trace underway" : snapshot.ready ? "room ready" : "waiting for all six"}</span></div><div className="timeline">{states.map((state, index) => <div key={state} className={snapshot.running ? "active" : ""}><b>{String(index + 1).padStart(2, "0")}</b><p>{state}</p></div>)}</div><div className="case-bottom"><div><span>Why it takes time</span><p>There are eleven paced, visible beats before any response latency. The human interactions make it naturally longer than two minutes.</p></div><button className="primary" disabled={!snapshot.ready || snapshot.running || busy !== null} onClick={onRun}><Icon name="play" />start the live case</button></div></>;
}

function LogView({ logs }: { logs: Log[] }) {
  return <><div className="section-heading"><div><span>Unified event stream</span><h2>What the runtime actually said, as it said it.</h2></div><span className="case-state">{logs.length} events in this browser</span></div><div className="log-list">{logs.length === 0 ? <div className="empty-log">Waiting for the control room to emit its first event.</div> : logs.map((event) => <article key={event.id} className={`log-item ${event.kind}`}><time>{new Date(event.at * 1000).toLocaleTimeString()}</time><span>{event.kind.replaceAll("_", " ")}</span><p>{event.message}</p>{event.participant && <code>{event.participant}</code>}</article>)}</div></>;
}

function HumanDesk({ request, human, busy, onAdd, onAnswer }: { request: Request | null; human?: Participant; busy: string | null; onAdd: () => void; onAnswer: (answer: string | boolean) => void }) {
  if (!human?.added) return <div className="human-empty"><Icon name="person" /><span>Human participant missing</span><h2>Add yourself as the sixth participant.</h2><p>The browser is registered as Maiku’s human channel. Until you join, the live case cannot start.</p><button className="primary" disabled={busy !== null} onClick={onAdd}><Icon name="plus" />add You</button></div>;
  if (!request) return <div className="human-empty"><Icon name="shield" /><span>Human desk standing by</span><h2>You are present in the runtime.</h2><p>Start the live case. This tab will receive real choose and approval requests from the running Maiku session.</p></div>;
  const options = request.detail.options || [];
  return <div className="decision-card"><span>{request.kind === "approval" ? "approval required" : "your choice required"}</span><h2>{request.prompt}</h2>{request.kind === "approval" && <pre>{JSON.stringify(request.detail.detail, null, 2)}</pre>}<div className="decision-actions">{request.kind === "approval" ? <><button className="primary" disabled={busy !== null} onClick={() => onAnswer(true)}>approve write</button><button className="outline" disabled={busy !== null} onClick={() => onAnswer(false)}>deny write</button></> : options.map((option) => <button key={option} className="primary" disabled={busy !== null} onClick={() => onAnswer(option)}>{option}</button>)}</div><p><Icon name="pulse" />This response is sent through the browser channel back into the active Maiku session.</p></div>;
}

createRoot(document.getElementById("root")!).render(<App />);
