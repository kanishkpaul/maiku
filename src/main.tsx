import { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type ParticipantKind = "model" | "tool" | "pipeline" | "human";
type Participant = {
  id: string;
  name: string;
  kind: ParticipantKind;
  description: string;
  affordances: string[];
  status: "ready" | "waiting" | "needs-you";
  color: "lime" | "sky" | "coral" | "cream";
};

type EventItem = { time: string; kind: "started" | "artifact" | "delegate" | "approval" | "finished"; text: string };

const initialParticipants: Participant[] = [
  {
    id: "cassia",
    name: "cassia",
    kind: "model",
    description: "A local language model that can reason and stream text.",
    affordances: ["stream: respond", "invoke: plan", "delegate"],
    status: "ready",
    color: "lime",
  },
  {
    id: "digits",
    name: "digits",
    kind: "pipeline",
    description: "A vision pipeline that classifies an image without becoming a chatbot.",
    affordances: ["invoke: classify", "artifact input", "tensor output"],
    status: "ready",
    color: "sky",
  },
  {
    id: "files",
    name: "files",
    kind: "tool",
    description: "An MCP filesystem server with scoped read and write affordances.",
    affordances: ["invoke: read", "invoke: write", "artifact access"],
    status: "ready",
    color: "cream",
  },
  {
    id: "you",
    name: "you",
    kind: "human",
    description: "A first-class participant who can answer, choose, and approve.",
    affordances: ["ask", "choose", "approve"],
    status: "needs-you",
    color: "coral",
  },
];

const initialEvents: EventItem[] = [
  { time: "now", kind: "started", text: "The shared session is ready. Nothing is running yet." },
  { time: "—", kind: "delegate", text: "Participants can only use the affordances you grant." },
];

const candidates: Record<ParticipantKind, Omit<Participant, "id" | "status">> = {
  model: { name: "new model", kind: "model", description: "An OpenAI-compatible or local model.", affordances: ["stream: respond", "invoke: tool call"], color: "lime" },
  tool: { name: "new tool", kind: "tool", description: "A service, MCP server, API, or command-line tool.", affordances: ["invoke: action", "event"], color: "cream" },
  pipeline: { name: "new pipeline", kind: "pipeline", description: "A model, function, notebook, or specialised pipeline.", affordances: ["invoke: process", "artifact input"], color: "sky" },
  human: { name: "a person", kind: "human", description: "A person who can answer, choose, and approve at human latency.", affordances: ["ask", "choose", "approve"], color: "coral" },
};

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    plus: <><path d="M12 5v14M5 12h14" /></>,
    spark: <><path d="m12 2 1.8 7.1L21 11l-7.2 1.9L12 20l-1.8-7.1L3 11l7.2-1.9L12 2Z" /></>,
    brain: <><path d="M9 4a3 3 0 0 0-5 2.2A3.3 3.3 0 0 0 5 12.5 3.2 3.2 0 0 0 9 17.7V20m6-16a3 3 0 0 1 5 2.2 3.3 3.3 0 0 1-1 6.3 3.2 3.2 0 0 1-4 5.2V20M9 8c1.2 0 2 .8 3 2.2C13 8.8 13.8 8 15 8m-6 6c1.2 0 2-.8 3-2.2 1 1.4 1.8 2.2 3 2.2" /></>,
    eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></>,
    file: <><path d="M6 3h8l4 4v14H6V3Z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>,
    person: <><circle cx="12" cy="7" r="3.2" /><path d="M5.5 21c.7-4 3-6 6.5-6s5.8 2 6.5 6" /></>,
    play: <><path d="m8 5 11 7-11 7V5Z" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    branch: <><path d="M6 3v13a3 3 0 0 0 3 3h9" /><circle cx="6" cy="3" r="2" /><circle cx="18" cy="19" r="2" /><path d="M6 9h12a3 3 0 0 1 3 3v1" /><circle cx="21" cy="13" r="2" /></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function ParticipantGlyph({ kind }: { kind: ParticipantKind }) {
  return <span className={`participant-glyph ${kind}`}><Icon name={kind === "model" ? "brain" : kind === "pipeline" ? "eye" : kind === "tool" ? "file" : "person"} size={25} /></span>;
}

function App() {
  const [participants, setParticipants] = useState(initialParticipants);
  const [selectedId, setSelectedId] = useState("cassia");
  const [events, setEvents] = useState(initialEvents);
  const [runState, setRunState] = useState<"idle" | "running" | "approval" | "finished">("idle");
  const [showAdd, setShowAdd] = useState(false);
  const [addingKind, setAddingKind] = useState<ParticipantKind>("model");

  const selected = useMemo(() => participants.find((item) => item.id === selectedId) ?? participants[0], [participants, selectedId]);

  function runDemo() {
    if (runState === "running") return;
    setRunState("running");
    setEvents([
      { time: "now", kind: "started", text: "cassia started a triage task in the shared session." },
      { time: "+01", kind: "artifact", text: "digits classified the image and wrote an artifact reference." },
      { time: "+02", kind: "delegate", text: "cassia requested scoped access to files/write." },
    ]);
    window.setTimeout(() => {
      setRunState("approval");
      setSelectedId("you");
      setEvents((current) => [...current, { time: "+03", kind: "approval", text: "Writing the report is irreversible. Your approval is required." }]);
    }, 850);
  }

  function approve() {
    setRunState("finished");
    setEvents((current) => [...current, { time: "+04", kind: "finished", text: "You approved the report. files wrote it and the session finished." }]);
  }

  function addParticipant() {
    const candidate = candidates[addingKind];
    const id = `${addingKind}-${participants.length + 1}`;
    const participant: Participant = { ...candidate, id, status: addingKind === "human" ? "needs-you" : "ready" };
    setParticipants((current) => [...current, participant]);
    setSelectedId(id);
    setEvents((current) => [...current, { time: "now", kind: "started", text: `${candidate.name} joined this demonstration session.` }]);
    setShowAdd(false);
  }

  return <main className="app-shell">
    <header className="topbar">
      <a className="brand" href="#top" aria-label="maiku demo home"><span className="brand-mark"><Icon name="spark" size={18} /></span>maiku</a>
      <div className="session-label"><span className="pulse" />Signal Garden <span>interactive demo</span></div>
      <button className="quiet-button" onClick={() => setShowAdd(true)}><Icon name="plus" />Add anything</button>
    </header>

    <section className="intro" id="top">
      <div>
        <p className="statement">Anything intelligent can work with everything else.</p>
        <p className="substatement">This is one shared Maiku session. Each participant keeps its own nature; you decide what may happen.</p>
      </div>
      <button className={`run-button ${runState === "running" ? "is-running" : ""}`} onClick={runDemo} disabled={runState === "running"}>
        <Icon name={runState === "finished" ? "shield" : "play"} />
        {runState === "idle" ? "Run the session" : runState === "running" ? "Following the trace" : runState === "approval" ? "Waiting for you" : "Run it again"}
      </button>
    </section>

    <section className="workspace" aria-label="Maiku demonstration workspace">
      <aside className="participants-panel">
        <div className="panel-heading"><span>In this session</span><strong>{participants.length}</strong></div>
        <div className="participant-list">
          {participants.map((participant) => <button key={participant.id} className={`participant-row ${selectedId === participant.id ? "selected" : ""}`} onClick={() => setSelectedId(participant.id)}>
            <ParticipantGlyph kind={participant.kind} />
            <span><b>{participant.name}</b><small>{participant.kind}</small></span>
            <i className={`status-dot ${participant.status}`} />
          </button>)}
        </div>
        <button className="add-row" onClick={() => setShowAdd(true)}><Icon name="plus" />Bring in something else</button>
        <div className="truth-note"><Icon name="shield" size={16} /><span>Participants see only the capabilities and artifacts you grant.</span></div>
      </aside>

      <section className="garden" aria-label="Connected participant map">
        <div className="garden-topline"><span className="map-caption">shared runtime</span><span>click a participant to inspect it</span></div>
        <div className="constellation" aria-label="Participants connected through a shared session">
          <svg className="signal-lines" viewBox="0 0 680 450" preserveAspectRatio="none" aria-hidden="true">
            <path d="M340 218 L340 66 M340 218 L558 218 M340 218 L340 378 M340 218 L122 218" />
            <path className="outer" d="M340 66 C470 75 550 128 558 218 C550 310 470 365 340 378 C210 365 130 310 122 218 C130 128 210 75 340 66Z" />
          </svg>
          <button className="task-seed" onClick={runDemo}><span>shared task</span><b>{runState === "idle" ? "frame triage" : runState === "approval" ? "needs approval" : runState === "finished" ? "report saved" : "in progress"}</b><small>one trace · four native kinds</small></button>
          {participants.slice(0, 4).map((participant, index) => <button key={participant.id} className={`orbit-node node-${index} ${selectedId === participant.id ? "active" : ""} ${participant.color}`} onClick={() => setSelectedId(participant.id)}>
            <ParticipantGlyph kind={participant.kind} /><span>{participant.name}</span><i className={`status-dot ${participant.status}`} />
          </button>)}
        </div>
        <div className="garden-footer"><span><i className="legend-dot lime" />can run</span><span><i className="legend-dot coral" />requires you</span><span><i className="legend-dot sky" />artifact-aware</span></div>
      </section>

      <aside className="inspector" aria-label="Selected participant details">
        <div className="inspector-title"><span>Participant</span><button aria-label="Close inspector" className="icon-button"><Icon name="close" /></button></div>
        <div className="selected-summary"><ParticipantGlyph kind={selected.kind} /><div><h2>{selected.name}</h2><p>{selected.kind} · {selected.status === "needs-you" ? "waiting on you" : "ready"}</p></div></div>
        <p className="description">{selected.description}</p>
        <div className="detail-group"><h3>Native affordances</h3>{selected.affordances.map((affordance) => <span className="affordance" key={affordance}>{affordance}</span>)}</div>
        <div className="detail-group"><h3>Current grant</h3><div className="grant"><Icon name="shield" size={16} /><span>{selected.kind === "human" ? "ask · choose · approve" : "read artifacts · invoke listed affordances"}</span></div></div>
        {runState === "approval" && selected.kind === "human" && <div className="approval-card"><span>Irreversible action</span><p>Allow <b>files/write</b> to save the incident report?</p><div><button className="approve" onClick={approve}>Approve write</button><button className="decline" onClick={() => setRunState("idle")}>Decline</button></div></div>}
        {runState === "finished" && <div className="completed-note"><Icon name="shield" size={16} />Approval recorded in the same event stream.</div>}
      </aside>
    </section>

    <section className="trace-panel" aria-label="Live session trace">
      <div className="trace-heading"><div><span>One event stream</span><h2>What happened, in a form every participant can share.</h2></div><button onClick={() => setEvents(initialEvents)} className="reset-button">Reset trace</button></div>
      <div className="event-list">{events.map((event, index) => <article className={`event ${event.kind}`} key={`${event.time}-${index}`}><time>{event.time}</time><span className="event-symbol"><Icon name={event.kind === "artifact" ? "file" : event.kind === "approval" ? "person" : event.kind === "delegate" ? "branch" : event.kind === "finished" ? "shield" : "spark"} size={16} /></span><p>{event.text}</p><span className="event-kind">{event.kind.replace("_", " ")}</span></article>)}</div>
    </section>

    <section className="explain-strip"><div><span>Not a chat wrapper</span><p>A classifier stays a classifier. A human stays a human. Maiku makes the capability between them legible.</p></div><button onClick={() => setShowAdd(true)}>Explore another participant <Icon name="arrow" /></button></section>

    {showAdd && <div className="modal-backdrop" role="presentation"><section className="add-modal" role="dialog" aria-modal="true" aria-labelledby="add-title"><button className="modal-close" onClick={() => setShowAdd(false)} aria-label="Close add participant"><Icon name="close" /></button><span className="modal-overline">Add anything intelligent</span><h2 id="add-title">What is joining the room?</h2><p>Choose its native shape. In a full Maiku runtime, an adapter derives its descriptor from the thing itself.</p><div className="kind-picker">{(Object.keys(candidates) as ParticipantKind[]).map((kind) => <button key={kind} className={addingKind === kind ? "picked" : ""} onClick={() => setAddingKind(kind)}><ParticipantGlyph kind={kind} /><span><b>{kind}</b><small>{candidates[kind].affordances[0]}</small></span></button>)}</div><div className="modal-action"><div><b>{candidates[addingKind].name}</b><span>{candidates[addingKind].description}</span></div><button className="approve" onClick={addParticipant}>Add to demo <Icon name="arrow" /></button></div></section></div>}
  </main>;
}

createRoot(document.getElementById("root")!).render(<App />);
