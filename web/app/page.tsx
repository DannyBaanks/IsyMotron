"use client";

import { useEffect, useState } from "react";
import { buildDashboardSnapshot } from "../lib/dashboard.js";

const demoState = {
  hosts: [{
    identity: { host_id: "host-03", display_name: "Michael" },
    granted: ["filesystem.read", "process.inspect"],
    health: { power_state: "ACTIVE", network_state: "UP", power_epoch: 2 },
    capabilities: [
      { id: "filesystem.read", state: "GRANTED" },
      { id: "process.inspect", state: "GRANTED" },
      { id: "apps.launch", state: "AVAILABLE" },
    ],
  }],
  awareness: { snapshot: { power_state: "ACTIVE", network_state: "UP", power_epoch: 2 } },
  receipts: [{ decision: { decision: "ALLOW" }, receipt_id: "rcpt_7a91", capability: "filesystem.read", seal_ok: true }],
};

const nodes = ["MODEL", "PLANNER", "HOST-03", "RECEIPT"];

export default function Home() {
  const [state, setState] = useState(demoState);
  const [live, setLive] = useState(false);
  const snapshot = buildDashboardSnapshot(state);

  useEffect(() => {
    fetch("/api/dashboard")
      .then((response) => response.json())
      .then((data) => {
        if (data.hosts?.length) { setState(data); setLive(true); }
      })
      .catch(() => undefined);
  }, []);

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">✦</span><span>ISY<span className="brand-hot">MOTRON</span></span></div>
        <div className="eyebrow">CAPABILITY FABRIC</div>
        <nav><a className="nav-item active" href="#overview"><span>◈</span> Overview</a><a className="nav-item" href="#fabric"><span>⌘</span> Capability Fabric</a><a className="nav-item" href="#receipts"><span>◌</span> Receipts</a><a className="nav-item" href="#hosts"><span>◉</span> Hosts</a></nav>
        <div className="sidebar-foot"><span className="pulse" /> surface online<br /><small>authority stays local</small></div>
      </aside>

      <section className="workspace" id="overview">
        <header className="topbar"><div><span className="eyebrow">CONTROL ROOM / 01</span><h1>Good morning, Michael<span className="cursor">_</span></h1></div><div className="top-actions"><span className={`live-chip ${live ? "is-live" : ""}`}><span /> {live ? "LIVE BACKEND" : "DEMO SURFACE"}</span><button className="avatar-button">M</button></div></header>
        <div className="status-rail"><div><span>HOST</span><strong>{snapshot.host.label}</strong></div><div><span>POWER</span><strong className="green">{snapshot.host.status}</strong></div><div><span>NETWORK</span><strong className="ice">{snapshot.host.network}</strong></div><div><span>LEASE</span><strong>18m 42s</strong></div><div><span>RISK</span><strong className="green">LOW</strong></div></div>

        <div className="content-grid">
          <section className="fabric-panel panel" id="fabric"><div className="panel-heading"><div><span className="eyebrow">EXECUTION TRACE</span><h2>Capability Fabric</h2></div><span className="tag live-tag"><span className="pulse" /> LIVE PATH</span></div><p className="panel-copy">Authority moves through explicit gates. Every green pulse is a decision the host made.</p><div className="fabric-stage">{nodes.map((node, index) => <div className="fabric-node-wrap" key={node}><div className={`fabric-node ${index === 3 ? "receipt-node" : "active-node"}`}><span className="node-icon">{index === 0 ? "✦" : index === 1 ? "⌁" : index === 2 ? "◉" : "✓"}</span><span>{node}</span><small>{index === 0 ? "proposal" : index === 1 ? "typed plan" : index === 2 ? "local gate" : "sealed proof"}</small></div>{index < nodes.length - 1 && <div className="fabric-link"><i /></div>}</div>)}</div><div className="trace-footer"><span className="trace-dot" /> <span>filesystem.read</span><span className="trace-arrow">→</span><span className="muted">hostfs://demo/brief.txt</span><span className="allow-pill">ALLOW</span></div></section>

          <aside className="stream-panel panel"><div className="panel-heading"><div><span className="eyebrow">EVENT STREAM</span><h2>Decisions</h2></div><span className="count">03</span></div><div className="event-list"><Event tone="allow" title="ALLOW" detail="filesystem.read" time="now" /><Event tone="ice" title="HOST ACTIVE" detail="power continuity verified" time="14s" /><Event tone="lavender" title="RECEIPT SEALED" detail="rcpt_7a91" time="28s" /></div><button className="ghost-button">View all events <span>↗</span></button></aside>
        </div>

        <section className="receipt-panel panel" id="receipts"><div className="panel-heading"><div><span className="eyebrow">LATEST ACTIVITY</span><h2>Receipts</h2></div><span className="tag">TAMPER-EVIDENT</span></div><div className="receipt-row"><div className="receipt-icon">✓</div><div className="receipt-main"><strong>filesystem.read</strong><span>hostfs://demo/brief.txt · {snapshot.host.label}</span></div><span className="allow-pill">ALLOW</span><div className="receipt-seal"><span>SEALED</span><code>rcpt_7a91</code></div><span className="duration">42ms</span></div></section>
        <footer className="footer"><span>ISyMotron surface v0.1</span><span>contracts over vibes <span className="green">●</span></span></footer>
      </section>
    </main>
  );
}

function Event({ tone, title, detail, time }: { tone: string; title: string; detail: string; time: string }) { return <div className="event"><span className={`event-icon ${tone}`}>•</span><div><strong>{title}</strong><span>{detail}</span></div><time>{time}</time></div>; }
