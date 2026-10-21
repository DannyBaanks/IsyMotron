"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { buildDashboardSnapshot } from "../lib/dashboard.js";

const demoState = {
  hosts: [
    {
      identity: { host_id: "host-03", display_name: "Michael" },
      granted: ["filesystem.read", "process.inspect"],
      health: { power_state: "ACTIVE", network_state: "UP", power_epoch: 2 },
      capabilities: [
        { id: "filesystem.read", state: "GRANTED" },
        { id: "process.inspect", state: "GRANTED" },
        { id: "apps.launch", state: "AVAILABLE" },
      ],
    },
  ],
  awareness: { snapshot: { power_state: "ACTIVE", network_state: "UP", power_epoch: 2 } },
  receipts: [
    { decision: { decision: "DENY" }, receipt_id: "rcpt_7a8f", capability: "apps.launch", seal_ok: true },
    { decision: { decision: "ALLOW" }, receipt_id: "rcpt_7a90", capability: "process.inspect", seal_ok: true },
    { decision: { decision: "ALLOW" }, receipt_id: "rcpt_7a91", capability: "filesystem.read", seal_ok: true },
  ],
};

const emptyState = { hosts: [], awareness: { snapshot: { power_state: "UNKNOWN", network_state: "UNKNOWN", power_epoch: 0 } }, receipts: [] };

type ConnectionState = "checking" | "live" | "demo" | "empty" | "error";
type IconName = "spark" | "shield" | "activity" | "receipt" | "devices" | "arrow" | "check" | "lock" | "bolt";
const capabilityLabels: Record<string, string> = {
  "filesystem.read": "Leer archivos",
  "filesystem.write": "Escribir archivos",
  "process.inspect": "Inspeccionar procesos",
  "apps.launch": "Abrir aplicaciones",
};
function capabilityLabel(id: string) { return capabilityLabels[id] ?? id; }
function formatObservedAt(value: string | null | undefined, fallback: string) { if (!value) return fallback; const date = new Date(value); return Number.isNaN(date.getTime()) ? fallback : new Intl.DateTimeFormat("es", { dateStyle: "short", timeStyle: "short" }).format(date); }

export default function Home() {
  const [state, setState] = useState(demoState);
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [lastChecked, setLastChecked] = useState("Ahora");
  const [expandedReceipt, setExpandedReceipt] = useState<string | null>(null);
  const [receiptFilter, setReceiptFilter] = useState<"all" | "ALLOW" | "DENY">("all");
  const [chatOpen, setChatOpen] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const snapshot = buildDashboardSnapshot(state);
  const isLive = connection === "live";
  const activeHostCount = isLive ? (state.hosts ?? []).filter((host) => host.health?.power_state === "ACTIVE" && host.health?.network_state === "UP").length : 0;
  const hostCount = isLive ? state.hosts?.length ?? 0 : 0;
  const hostOnline = isLive && snapshot.host.status === "ACTIVE" && snapshot.host.network === "UP";
  const latestReceipt = isLive ? snapshot.receipts[0] : undefined;
  const visibleReceipts = snapshot.receipts.filter((receipt: { decision: string }) => receiptFilter === "all" || receipt.decision === receiptFilter);

  const loadDashboard = useCallback(async () => {
    setConnection("checking");
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.reason ?? "No se pudo conectar");
      if (data.hosts?.length) {
        setState(data);
        setConnection("live");
      } else if (data.reason === "missing session token") {
        setState(demoState);
        setConnection("demo");
      } else {
        setState(emptyState);
        setConnection("empty");
      }
      setLastChecked("Ahora");
    } catch {
      setConnection("error");
      setLastChecked("Hace un momento");
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const activity: { tone: string; title: string; detail: string; time: string; icon: IconName }[] = useMemo(() => {
    const firstReceipt = isLive ? snapshot.receipts[0] : undefined;
    const secondReceipt = isLive ? snapshot.receipts[1] : undefined;
    if (!firstReceipt) {
      return [{ tone: "info", title: isLive ? "Sin actividad todavía" : "Vista de demostración", detail: isLive ? "Aquí aparecerán tus decisiones" : "Los eventos de esta lista son ejemplos", time: "—", icon: "devices" }];
    }
    return [
      { tone: firstReceipt.decision === "ALLOW" ? "success" : "warning", title: firstReceipt.decision === "ALLOW" ? "Acción permitida" : "Acción rechazada", detail: firstReceipt.capability, time: formatObservedAt(firstReceipt.observedAt, "Ahora"), icon: firstReceipt.decision === "ALLOW" ? "check" : "lock" },
      ...(hostOnline ? [{ tone: "info", title: "Equipo disponible", detail: `${snapshot.host.label} está listo para trabajar`, time: "14 s", icon: "devices" as IconName }] : []),
      ...(secondReceipt ? [{ tone: secondReceipt.seal === "SEALED" ? "violet" : "warning", title: secondReceipt.seal === "SEALED" ? "Recibo verificado" : "Recibo pendiente", detail: secondReceipt.id, time: "28 s", icon: "receipt" as IconName }] : []),
    ];
  }, [snapshot, hostOnline, isLive]);

  const isDemo = connection === "demo" || connection === "error";
  const isEmpty = connection === "empty";
  const connectionLabel = connection === "checking" ? "Comprobando conexión" : connection === "live" ? "Conectado en vivo" : connection === "error" ? "Conexión interrumpida" : connection === "empty" ? "Sin equipos conectados" : "Modo demostración";

  return (
    <main className="app-shell" data-design-system="ISYMOTRON_DESIGN_V1">
      <aside className="sidebar" aria-label="Navegación principal">
        <a className="brand" href="#overview" aria-label="IsyMotron, ir al resumen"><span className="brand-mark"><Icon name="spark" /></span><span className="brand-name">ISY<span>MOTRON</span></span></a>
        <div className="brand-note">Tu capa de control para IA</div>
        <nav className="main-nav">
          <span className="nav-label">Espacio de trabajo</span>
          <a className="nav-item active" href="#overview" aria-label="Resumen" aria-current="page"><Icon name="activity" /><span>Resumen</span></a>
          <a className="nav-item" href="#flow" aria-label="Flujo de confianza"><Icon name="arrow" /><span>Flujo de confianza</span></a>
          <a className="nav-item" href="#activity" aria-label="Actividad"><Icon name="bolt" /><span>Actividad</span><span className="nav-count">{isLive ? snapshot.receipts.length : 0}</span></a><a className="nav-item" href="#capabilities" aria-label="Capabilities"><Icon name="shield" /><span>Capabilities</span></a>
          <a className="nav-item" href="#receipts" aria-label="Recibos"><Icon name="receipt" /><span>Recibos</span></a>
          <a className="nav-item" href="#hosts" aria-label="Mis equipos"><Icon name="devices" /><span>Mis equipos</span></a>
        </nav>
        <div className="sidebar-explainer"><div className="explainer-icon"><Icon name="shield" /></div><strong>La autoridad se queda contigo</strong><p>La IA puede proponer. Solo tu equipo decide qué se ejecuta.</p><a href="#how-it-works">Entender cómo funciona <span>↗</span></a></div>
        <div className="sidebar-foot"><span className={`status-dot ${hostOnline ? "online" : "offline"}`} /> {hostOnline ? "Sistema protegido" : "Esperando equipo"} <small>v0.1 · local-first</small></div>
      </aside>

      <section className="workspace" id="overview">
        <header className="topbar"><div className="topbar-copy"><div className="breadcrumb"><span>Espacio personal</span><span className="breadcrumb-divider">/</span><span>Resumen</span></div><h1>{isLive ? `Buenos días, ${snapshot.host.label}` : "Explora tu espacio"}<span className="headline-dot">.</span></h1><p>Todo está bajo control. Aquí tienes una vista clara de lo que tu IA puede hacer.</p></div><div className="top-actions"><div className={`connection-pill ${connection}`} role="status" aria-live="polite"><span className="connection-dot" /><span>{connectionLabel}</span></div><button className="advanced-toggle" type="button" onClick={() => setAdvancedMode((value) => !value)} aria-pressed={advancedMode}>{advancedMode ? "Vista simple" : "Detalles técnicos"}</button><span className="profile-button" aria-label="Perfil de Michael">M</span></div></header>

        {(isDemo || isEmpty) && <div className={`notice-banner ${connection === "error" ? "notice-error" : isEmpty ? "notice-empty" : "notice-demo"}`} role="status"><div className="notice-symbol"><Icon name={connection === "error" ? "activity" : isEmpty ? "devices" : "spark"} /></div><div className="notice-copy"><strong>{connection === "error" ? "Mostrando la última vista disponible" : isEmpty ? "Todavía no hay equipos conectados" : "Estás explorando una vista de demostración"}</strong><span>{connection === "error" ? "No hemos podido hablar con tu equipo. Tus datos no se han modificado." : isEmpty ? "Conecta un equipo autorizado para empezar a ver decisiones y recibos." : "Los datos de esta pantalla son de ejemplo. Conecta un host para ver actividad real."}</span></div><button className="notice-action" onClick={() => void loadDashboard()}>{connection === "error" ? "Reintentar conexión" : isEmpty ? "Volver a comprobar" : "Comprobar conexión"} <span>↗</span></button></div>}

        <section className="trust-rail" aria-label="Estado de confianza"><TrustItem icon="devices" label="Conexión" value={connectionLabel} tone={isLive ? "success" : connection === "checking" ? "info" : "warning"} /><TrustItem icon="shield" label="Autoridad" value={hostOnline ? "Decisiones locales activas" : "Esperando decisión local"} tone={hostOnline ? "success" : "warning"} /><TrustItem icon="activity" label="Datos" value={connection === "demo" ? "Datos de ejemplo" : connection === "error" ? "Última vista · revisar frescura" : lastChecked} tone={connection === "error" ? "warning" : "info"} /><TrustItem icon="receipt" label="Evidencia" value={latestReceipt ? "Último receipt disponible" : "Sin receipt real"} tone={latestReceipt ? "success" : "warning"} />{advancedMode && <div className="advanced-meta"><span>host_id: {isLive ? snapshot.host.id : "no disponible"}</span><span>power_epoch: {isLive ? snapshot.host.epoch : "—"}</span><span>network: {isLive ? snapshot.host.network : "UNKNOWN"}</span></div>}</section>
        {!isLive && <ConnectionGuide connection={connection} />}
        <section className="summary-grid" aria-label="Estado general">
          <article className="summary-card summary-card-featured"><div className="summary-icon green"><Icon name="shield" /></div><div className="summary-content"><span className="summary-label">Protección local</span><strong>{hostOnline ? "Activa y funcionando" : "Esperando un equipo"}</strong><span className="summary-detail"><span className={`status-dot ${hostOnline ? "online" : "offline"}`} /> {hostOnline ? "Tu equipo decide cada acción" : "Conecta un equipo para activarla"}</span></div><span className="summary-arrow">↗</span></article>
          <article className="summary-card"><div className="summary-icon blue"><Icon name="devices" /></div><div className="summary-content"><span className="summary-label">Tus equipos</span><strong>{isLive ? activeHostCount : "—"} <small>{isLive ? (activeHostCount === 1 ? "activo" : "activos") : "demo"}</small></strong><span className="summary-detail">{isLive ? (hostCount ? `${snapshot.host.label} · ${hostOnline ? "listo para trabajar" : "sin conexión"}` : "Ningún equipo conectado") : "Sin conexión real"}</span></div></article>
          <article className="summary-card"><div className="summary-icon violet"><Icon name="bolt" /></div><div className="summary-content"><span className="summary-label">Capacidades disponibles</span><strong>{snapshot.host.capabilities} <small>{isLive ? "permitidas" : "de ejemplo"}</small></strong><span className="summary-detail">{isLive ? "Controladas por ti" : "No son autoridad real"}</span></div></article>
          <article className="summary-card"><div className="summary-icon coral"><Icon name="receipt" /></div><div className="summary-content"><span className="summary-label">Recibos verificables</span><strong>{snapshot.receipts.length} <small>{isLive ? "registrados" : "de ejemplo"}</small></strong><span className="summary-detail">{isLive ? "Cada acción deja evidencia" : "Evidencia simulada"}</span></div></article>
        </section>

        <section className="capability-section panel" id="capabilities" aria-labelledby="capability-title"><div className="panel-header"><div><span className="eyebrow">PERMISOS EXPLÍCITOS</span><h2 id="capability-title">Qué puede hacer tu equipo</h2><p>La interfaz explica cada capability sin ampliar su alcance. Los campos ausentes permanecen como desconocidos.</p></div><span className="small-count">{snapshot.capabilities.length.toString().padStart(2, "0")}</span></div><div className="capability-grid">{snapshot.capabilities.length ? snapshot.capabilities.map((capability: { id: string; state?: string; description?: string; scope?: string; risk?: string }) => <article className="capability-card" key={capability.id}><div className="capability-card-top"><div><strong>{capabilityLabel(capability.id)}</strong><code>{capability.id}</code></div><span className={`capability-status ${capability.state === "GRANTED" ? "granted" : "unknown"}`}>{capability.state ?? "UNKNOWN"}</span></div><p>{capability.description ?? (isLive ? "Descripción no disponible en el contrato actual." : "Capability de ejemplo; no es autoridad real.")}</p><div className="capability-meta"><span>Alcance: {capability.scope ?? "No especificado"}</span><span>Riesgo: {capability.risk ?? "No especificado"}</span></div></article>) : <div className="capability-empty">Conecta un equipo autorizado para ver sus capabilities reales.</div>}</div></section>
        <section className="flow-section" id="flow"><div className="section-heading"><div><span className="eyebrow">ASÍ FUNCIONA</span><h2>De una idea a una acción segura</h2><p>La IA propone el camino. Tu equipo comprueba que cada paso esté permitido.</p></div><a className="text-link" href="#how-it-works">Ver explicación <span>↗</span></a></div><div className="flow-card"><div className="flow-line" aria-hidden="true"><span /><span /><span /></div><FlowStep number="01" icon="spark" title="La IA propone" detail="Entiende tu intención y sugiere un plan." state="completed" /><FlowStep number="02" icon="shield" title="Tu equipo decide" detail="Comprueba permisos, alcance y seguridad." state={latestReceipt ? "completed" : "active"} /><FlowStep number="03" icon="bolt" title="Se ejecuta" detail="Solo ocurre lo que tú autorizaste." state={latestReceipt?.decision === "ALLOW" ? "completed" : "next"} /><FlowStep number="04" icon="receipt" title="Queda registrado" detail="Un recibo verificable cuenta lo que pasó." state={latestReceipt ? "completed" : "next"} /></div><div className="flow-caption"><span className={`status-dot ${latestReceipt ? "online" : "offline"}`} /><strong>{latestReceipt ? "Todo en orden" : "Esperando tu primera acción"}</strong><span>{latestReceipt ? (latestReceipt.decision === "ALLOW" ? "La última decisión fue permitida y quedó sellada." : "La última solicitud fue rechazada y quedó registrada.") : "Cuando conectes un equipo, aquí verás su recorrido."}</span><span className="caption-id">{latestReceipt?.id ?? "—"}</span></div></section>

        <div className="dashboard-grid"><section className="panel activity-panel" id="activity"><div className="panel-header"><div><span className="eyebrow">EN TIEMPO REAL</span><h2>Actividad reciente</h2></div><a className="panel-link" href="#receipts">Ver todo <span>↗</span></a></div><div className="activity-list">{activity.map((item) => <ActivityItem key={`${item.title}-${item.time}`} {...item} />)}</div><div className="activity-footer"><span className="activity-pulse" /> Actualizado {lastChecked}<button onClick={() => void loadDashboard()} aria-label="Actualizar actividad">↻</button></div></section>
          <section className="panel host-panel" id="hosts"><div className="panel-header"><div><span className="eyebrow">TU EQUIPO</span><h2>Mis equipos</h2></div><span className="small-count">{String(hostCount).padStart(2, "0")}</span></div><div className="host-card"><div className="host-avatar"><Icon name="devices" /></div><div className="host-info"><strong>{isLive && hostCount ? snapshot.host.label : "Host de ejemplo"}</strong><span><span className={`status-dot ${hostOnline ? "online" : "offline"}`} /> {isLive ? (hostOnline ? "Disponible ahora" : "Esperando conexión") : "No conectado · demo"}</span></div><span className="more-button" aria-hidden="true">•••</span></div><div className="host-facts"><div><span>Conexión</span><strong className="blue-text">{isLive ? (hostOnline ? "Estable" : hostCount ? "Revisar" : "Sin conexión") : "Demo"}</strong></div><div><span>Permisos</span><strong>{isLive ? `${snapshot.host.capabilities} activos` : "Datos demo"}</strong></div></div><a className="outline-action" href="#hosts">Administrar equipos <span>↗</span></a></section></div>

        <section className="panel receipts-panel" id="receipts"><div className="panel-header"><div><span className="eyebrow">EVIDENCIA DE CADA DECISIÓN</span><h2>Recibos verificables</h2><p>Una historia clara de lo que se pidió, lo que se permitió y lo que ocurrió.</p></div><label className="outline-action compact filter-control"><span>Filtrar</span><select aria-label="Filtrar recibos" value={receiptFilter} onChange={(event) => setReceiptFilter(event.target.value as "all" | "ALLOW" | "DENY")}><option value="all">Todos</option><option value="ALLOW">Permitidos</option><option value="DENY">Rechazados</option></select></label></div><div className="receipt-table" role="table" aria-label="Recibos recientes"><div className="receipt-table-head" role="row"><span role="columnheader">Resultado</span><span role="columnheader">Qué se hizo</span><span role="columnheader">Equipo</span><span role="columnheader">Identificador</span><span role="columnheader">Estado</span></div>{visibleReceipts.length ? visibleReceipts.map((receipt: { id: string; decision: string; capability: string; action?: string | null; owner?: string | null; observedAt?: string | null; source?: string | null; freshness?: string | null; seal: string }, index: number) => <div className="receipt-entry" key={receipt.id}><ReceiptRow receipt={receipt} host={snapshot.host.label} time={isLive ? formatObservedAt(receipt.observedAt, index === 0 ? "Ahora" : `${(index + 1) * 14} s`) : "Demo"} expanded={expandedReceipt === receipt.id} onToggle={() => setExpandedReceipt(expandedReceipt === receipt.id ? null : receipt.id)} />{expandedReceipt === receipt.id && <div className="receipt-detail" role="note"><strong>Detalle de auditoría</strong><span>Capacidad: {receipt.capability}</span><span>Decisión local: {receipt.decision === "ALLOW" ? "permitida" : "rechazada"}</span><span>Recibo: {receipt.seal === "SEALED" ? "sello verificado" : "sello pendiente"}</span>{receipt.owner && <span>Owner: {receipt.owner}</span>}{receipt.source && <span>Origen: {receipt.source}</span>}{receipt.freshness && <span>Frescura: {receipt.freshness}</span>}<button onClick={() => setExpandedReceipt(null)}>Cerrar detalle</button></div>}</div>) : <div className="receipt-empty">{receiptFilter === "all" ? "Aún no hay recibos. Conecta un equipo para empezar." : "No hay recibos con este filtro."}</div>}</div></section>

        <section className="how-section" id="how-it-works"><div className="how-icon"><Icon name="lock" /></div><div><span className="eyebrow">LA IDEA CENTRAL</span><h2>Más útil no significa más poder.</h2><p>IsyMotron ayuda a la IA a hacer cosas útiles sin darle las llaves de tu equipo. Las capacidades se conceden de forma explícita, se mantienen locales y no pueden ampliarse por sí solas.</p></div><a className="text-link" href="#flow">Volver al flujo <span>↑</span></a></section>
        <footer className="footer"><span>IsyMotron <strong>·</strong> tu capa de control local</span><span><span className="footer-mark">✦</span> contratos sobre suposiciones</span></footer>
      </section>
      <MalbolgatoLauncher open={chatOpen} onToggle={() => setChatOpen((value) => !value)} />
      {chatOpen && <ChatDrawer onClose={() => setChatOpen(false)} />}
    </main>
  );
}


function MalbolgatoLauncher({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const handleToggle = () => {
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("isymotron:open-chat"));
    onToggle();
  };
  return <button className={`malbolgato-launcher ${open ? "is-open" : ""}`} type="button" onClick={handleToggle} aria-label="Abrir chat de ISyMotron" aria-expanded={open} aria-controls="gus-chat-drawer"><img src="/malbolgato/idle.gif" alt="" width="64" height="64" /></button>;
}

function ChatDrawer({ onClose }: { onClose: () => void }) {
  return <aside className="chat-drawer" id="gus-chat-drawer" role="dialog" aria-modal="false" aria-labelledby="gus-chat-title"><div className="chat-drawer-header"><div><span className="eyebrow">GUS / CHAT</span><h2 id="gus-chat-title">Malbolgato está listo</h2></div><button className="chat-close" type="button" onClick={onClose} aria-label="Cerrar chat">×</button></div><div className="chat-companion"><img src="/malbolgato/idle.gif" alt="Malbolgato" width="72" height="72" /><div><strong>Representa. No autoriza.</strong><p>Este companion solo abre el acceso a GUS y refleja su estado. Nunca concede permisos ni ejecuta acciones.</p></div></div><div className="chat-connection"><span className="status-dot offline" /><div><strong>Chat real pendiente de conexión</strong><span>La superficie web actual todavía no expone un endpoint de conversación. No mostraremos mensajes inventados.</span></div></div><div className="chat-states"><span>PROPOSED</span><span>AUTHORIZED</span><span>EXECUTED</span><span>VERIFIED</span><span>DENIED</span></div><p className="chat-note">Cuando GUS esté conectado, este mismo launcher conservará la conversación y separará propuesta, autorización, ejecución y receipt verificado.</p></aside>;
}


function TrustItem({ icon, label, value, tone }: { icon: IconName; label: string; value: string; tone: string }) { return <article className="trust-item"><div className={`trust-icon ${tone}`}><Icon name={icon} /></div><div><span>{label}</span><strong>{value}</strong></div></article>; }
function ConnectionGuide({ connection }: { connection: ConnectionState }) { return <section className="connection-guide" aria-label="Cómo conectar un equipo"><div className="guide-copy"><span className="eyebrow">SIGUIENTE PASO</span><h2>{connection === "error" ? "Comprueba tu conexión local" : "Conecta tu primer equipo"}</h2><p>{connection === "error" ? "El host no respondió. No se ejecutó ninguna acción y tus datos no se modificaron." : "IsyMotron no puede autorizarse a sí mismo. La confirmación ocurre en tu equipo."}</p></div><ol><li><span>01</span><div><strong>Inicia el host local</strong><small>El proceso mantiene la autoridad cerca de ti.</small></div></li><li><span>02</span><div><strong>Confirma la sesión</strong><small>La conexión se valida antes de mostrar actividad.</small></div></li><li><span>03</span><div><strong>Revisa capabilities</strong><small>Solo se presentan permisos que el host expone.</small></div></li></ol></section>; }

function FlowStep({ number, icon, title, detail, state }: { number: string; icon: IconName; title: string; detail: string; state: "completed" | "active" | "next" }) { return <div className={`flow-step ${state}`}><div className="step-top"><span className="step-number">{number}</span><div className="step-icon"><Icon name={icon} /></div>{state === "completed" && <span className="step-check"><Icon name="check" /></span>}</div><strong>{title}</strong><span>{detail}</span>{state === "active" && <em>Ahora</em>}</div>; }
function ActivityItem({ tone, title, detail, time, icon }: { tone: string; title: string; detail: string; time: string; icon: IconName }) { return <article className="activity-item"><div className={`activity-icon ${tone}`}><Icon name={icon} /></div><div className="activity-copy"><strong>{title}</strong><span>{detail}</span></div><time>{time}</time></article>; }
function ReceiptRow({ receipt, host, time, expanded, onToggle }: { receipt: { id: string; decision: string; capability: string; action?: string | null; owner?: string | null; observedAt?: string | null; source?: string | null; freshness?: string | null; seal: string }; host: string; time: string; expanded: boolean; onToggle: () => void }) { const allowed = receipt.decision === "ALLOW"; const sealed = receipt.seal === "SEALED"; return <div className={`receipt-row ${expanded ? "is-expanded" : ""}`} role="row"><div className={`result-badge ${allowed ? "allowed" : "denied"}`} role="cell"><Icon name={allowed ? "check" : "lock"} /><span>{allowed ? "Permitido" : "Rechazado"}</span></div><div className="receipt-action" role="cell"><strong>{capabilityLabel(receipt.capability)}</strong><span>{receipt.capability}</span></div><span className="receipt-host" role="cell">{host}</span><code role="cell">{receipt.id}</code><div className="seal-status" role="cell"><span className={`seal-icon ${sealed ? "" : "pending"}`}><Icon name={sealed ? "check" : "lock"} /></span><span><strong>{sealed ? "Verificado" : "Pendiente"}</strong><small>{time}</small></span><button className="receipt-detail-toggle" onClick={onToggle} aria-expanded={expanded}>{expanded ? "Cerrar" : "Detalle"}</button></div></div>; }

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    spark: <><path d="m12 2 1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2Z" /><path d="m19 16 .6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6L19 16Z" /></>,
    shield: <path d="M12 3 20 6v5c0 5-3.4 8.1-8 10-4.6-1.9-8-5-8-10V6l8-3Zm-3.2 8.8 2.1 2.1 4.5-4.6" />,
    activity: <><path d="M3 12h4l2-5 4 10 2-5h6" /><path d="M3 5h3M18 19h3" /></>,
    receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
    devices: <><rect x="3" y="4" width="13" height="16" rx="2" /><path d="M7 17h5M19 8h2v8h-2M18 19h4" /></>,
    arrow: <><path d="M4 12h15" /><path d="m14 6 6 6-6 6" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" /></>,
    bolt: <path d="m13 2-8 12h6l-1 8 8-12h-6l1-8Z" />,
  };
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
