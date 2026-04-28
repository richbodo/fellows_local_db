// Shared data + small primitives matched to the existing app's visual language:
// system-ui, purple #4a2c6a section heads, plain blue underlined links,
// table-row label/value pattern, light grey #f0f0f0 row labels, modest density.

const FELLOWS = [
  { name: "Tatyana Mikayilova", tags: ["environment", "policy"], email: true },
  { name: "Tejas Viswanath", tags: ["fintech"], email: true },
  { name: "Teresa Tepania-Ashton", tags: ["indigenous", "policy"], email: true },
  { name: "Teruhide Sato", tags: ["investment", "fintech"], email: true },
  { name: "Tesh Randall", tags: ["food", "environment"], email: true },
  { name: "Tessa Vincent", tags: ["arts"], email: false },
  { name: "Thabiso Mashaba", tags: ["education", "africa"], email: true },
  { name: "Thea La Grou", tags: ["arts", "media"], email: true },
  { name: "Thiago Canellas", tags: ["fintech"], email: true },
  { name: "Thomas Staggs", tags: ["media"], email: false },
  { name: "Tilla Abbitt", tags: ["food", "environment"], email: true },
  { name: "Tillie Walton", tags: ["adventure", "environment"], email: true },
  { name: "Tim Chang", tags: ["investment", "wellbeing"], email: true },
  { name: "Tim Derrick", tags: ["pickleball", "wellbeing"], email: true },
  { name: "Tim Ferriss", tags: ["wellbeing", "media"], email: true },
  { name: "Tim Hawkey", tags: ["health", "design"], email: true },
  { name: "Tim Moor", tags: ["pickleball"], email: true },
  { name: "Tim Pare", tags: ["environment"], email: true },
  { name: "Timothy Allan", tags: ["design"], email: true },
  { name: "Tina Jennen", tags: ["energy", "environment"], email: true },
  { name: "Tjiu Liang Chua", tags: ["fintech"], email: false },
  { name: "Todd Porter", tags: ["design"], email: true },
  { name: "Tony Lai", tags: ["legal", "policy"], email: true },
  { name: "Topaz Adizes", tags: ["arts", "media"], email: true },
  { name: "Tory Patterson", tags: ["investment"], email: true },
  { name: "Tracy Chou", tags: ["tech", "policy"], email: true },
  { name: "Trevor Squier", tags: ["pickleball"], email: true },
  { name: "Tristan Harris", tags: ["tech", "policy"], email: true },
  { name: "Trushar Khetia", tags: ["africa", "investment"], email: true },
  { name: "Udit Shah", tags: ["food"], email: true },
  { name: "Uri Lopatin", tags: ["health"], email: true },
  { name: "Usman Iftikhar", tags: ["education"], email: true },
  { name: "Vanessa Coleman", tags: ["policy"], email: true },
  { name: "Vanessa Paranjothy", tags: ["food"], email: true },
  { name: "Venetia Pristavec", tags: ["design"], email: true },
  { name: "Veronica H-Stevenson", tags: ["education"], email: false },
  { name: "Vicky Robertson", tags: ["environment"], email: true },
  { name: "Victor Zonana", tags: ["health", "policy"], email: true },
  { name: "Vienna Nordstrom", tags: ["arts"], email: true },
  { name: "Vishal Chaddha", tags: ["fintech"], email: true },
];

const SAVED_GROUPS = [
  { id: "g_001", name: "Climate cohort", count: 14, created: "2026-04-12", note: "for the Wellington roundtable" },
  { id: "g_002", name: "Pickleball lunch crew", count: 4, created: "2026-04-18", note: "" },
  { id: "g_003", name: "Tāmaki design folks", count: 9, created: "2026-04-20", note: "intro book for Aroha" },
  { id: "g_004", name: "Fintech intros — Thiago", count: 6, created: "2026-04-23", note: "" },
];

function initials(name) {
  const parts = name.split(/[\s-]+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase();
}

// Match the app's swatches
const C = {
  bg: "#f5f5f8",
  paper: "#fff",
  ink: "#222",
  muted: "#555",
  border: "#ccc",
  rowLabel: "#f0f0f0",
  purple: "#4a2c6a",
  purpleDark: "#3b2355",
  link: "#0066cc",
  linkHover: "#004499",
  warnBg: "#fff3cd",
  warnBorder: "#ffe69c",
  warnText: "#664d03",
  lightLavender: "#faf8fc",
  lavenderBorder: "#dcd6e8",
  pillBg: "#ede7f3",
  pillText: "#3b2355",
};

// One-line section header in the app's purple style
function SectionHead({ children, secondary, style }) {
  return (
    <div style={{
      padding: "0.35em 0.5em",
      background: secondary ? "#e8e8e8" : C.purple,
      color: secondary ? "#333" : "#fff",
      fontSize: "0.95rem",
      fontWeight: 600,
      ...style
    }}>{children}</div>
  );
}

// Tag pill, low-key
function Tag({ children, onClick, removable }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "1px 7px", marginRight: 4,
      fontSize: "0.72rem", fontWeight: 500,
      background: C.pillBg, color: C.pillText,
      border: `1px solid ${C.lavenderBorder}`, borderRadius: 10,
      cursor: onClick ? "pointer" : "default"
    }} onClick={onClick}>
      {children}{removable && <span style={{ opacity: 0.6 }}>×</span>}
    </span>
  );
}

// Plain app-style button
function Btn({ children, onClick, primary, danger, small, disabled, style }) {
  const base = {
    padding: small ? "0.2rem 0.55rem" : "0.3rem 0.7rem",
    fontSize: small ? "0.78rem" : "0.85rem",
    borderRadius: 3, cursor: disabled ? "not-allowed" : "pointer",
    fontFamily: "inherit", lineHeight: 1.3,
    opacity: disabled ? 0.5 : 1,
  };
  let scheme;
  if (primary) scheme = { background: C.purple, color: "#fff", border: `1px solid ${C.purple}` };
  else if (danger) scheme = { background: "#fff", color: "#7a1f1f", border: "1px solid #c9a3a3" };
  else scheme = { background: "#fff", color: "#333", border: `1px solid ${C.border}` };
  return <button onClick={disabled ? undefined : onClick} style={{ ...base, ...scheme, ...style }}>{children}</button>;
}

// Small framing for each artboard so they all read as the same app
function AppFrame({ children, page = "directory", title = "Confidential — Fellows Local-Only Directory" }) {
  return (
    <div style={{
      width: "100%", height: "100%", background: C.bg, color: C.ink,
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      fontSize: "0.95rem", display: "flex", flexDirection: "column",
      overflow: "hidden"
    }}>
      {/* Top bar */}
      <div style={{
        padding: "0.55rem 0.75rem", borderBottom: `1px solid ${C.border}`,
        background: "#fff", display: "flex", alignItems: "center", gap: "1rem", flexShrink: 0
      }}>
        <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>EHF Fellows</div>
        <nav style={{ display: "flex", gap: "0.9rem", fontSize: "0.85rem" }}>
          <a href="#" style={{ color: page === "directory" ? C.purple : C.link,
            fontWeight: page === "directory" ? 600 : 400,
            textDecoration: page === "directory" ? "none" : "underline" }}>directory</a>
          <a href="#" style={{ color: page === "groups" ? C.purple : C.link,
            fontWeight: page === "groups" ? 600 : 400,
            textDecoration: page === "groups" ? "none" : "underline" }}>groups</a>
          <a href="#" style={{ color: C.link, textDecoration: "underline" }}>about</a>
        </nav>
        <div style={{ marginLeft: "auto", fontSize: "0.7rem", color: "#7a6f91",
          fontFamily: "ui-monospace, Menlo, monospace" }}>{title}</div>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>{children}</div>
    </div>
  );
}

Object.assign(window, {
  FELLOWS, SAVED_GROUPS, initials, C, SectionHead, Tag, Btn, AppFrame
});
