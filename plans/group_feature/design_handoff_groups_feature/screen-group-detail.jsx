// Screen: GROUP DETAIL — what you see when you click a group's name.
// Single-pane, mobile-friendly: title row, then one action bar with three
// peer buttons (Contact / Export / Edit), then note, then members.
// "Contact the whole group" is a plain mailto:?cc= — no expansion.
// "Export a directory" expands a checkbox panel inline.
// "Edit group" returns to the directory in editing mode.

function ScreenGroupDetail({ name = "Climate cohort", count = 14, mode = "default" }) {
  const members = [
    "Tatyana Mikayilova", "Tesh Randall", "Tilla Abbitt", "Tillie Walton",
    "Tim Derrick", "Tim Ferriss", "Tim Pare", "Tina Jennen", "Tony Lai",
    "Tracy Chou", "Trevor Squier", "Tristan Harris", "Vanessa Coleman",
    "Vicky Robertson"
  ].slice(0, count);
  const [showExport, setShowExport] = React.useState(mode === "export");

  const slug = name.toLowerCase().replace(/^#/, "").replace(/[^a-z0-9]+/g, "-");
  const cc = members.map(n => `${n.split(" ")[0].toLowerCase()}@example.com`).join(",");

  return (
    <AppFrame page="groups">
      <div style={{ padding: "0.8rem 1rem", display: "flex", flexDirection: "column",
        height: "100%", boxSizing: "border-box", gap: "0.7rem", maxWidth: 760, margin: "0 auto", width: "100%" }}>

        {/* Breadcrumb */}
        <div style={{ fontSize: "0.8rem", color: C.muted }}>
          <a href="#" style={{ color: C.link, textDecoration: "underline" }}>groups</a>
          {" › "}<span>{name}</span>
        </div>

        {/* Title row */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.7rem", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontSize: "1.25rem" }}>{name}</h2>
          <a href="#" style={{ fontSize: "0.78rem", color: C.link, textDecoration: "underline" }}>rename</a>
          <span style={{ fontSize: "0.85rem", color: C.muted }}>
            {members.length} fellows · created Apr 12, 2026
          </span>
        </div>

        {/* Single action bar — three peer buttons */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 8,
          padding: "0.5rem 0.6rem",
          background: C.lightLavender, border: `1px solid ${C.lavenderBorder}`,
        }}>
          <Btn primary>
            <a href={`mailto:?cc=${cc}&subject=${encodeURIComponent(name)}`}
               style={{ color: "inherit", textDecoration: "none" }}>
              ✉ Contact the whole group
            </a>
          </Btn>
          <Btn onClick={() => setShowExport(!showExport)}>
            ⬇ Export a directory
          </Btn>
          <Btn>
            ✎ Edit group
          </Btn>
          <span style={{ marginLeft: "auto", fontSize: "0.72rem", color: "#7a6f91", alignSelf: "center" }}>
            mailto: opens your client with everyone in CC
          </span>
        </div>

        {/* Inline export panel — appears beneath the action bar when toggled */}
        {showExport && (
          <div style={{
            background: "#fff", border: `1px solid ${C.lavenderBorder}`,
            fontSize: "0.85rem"
          }}>
            <SectionHead>Export a directory</SectionHead>
            <div style={{ padding: "0.55rem 0.7rem", display: "flex", flexWrap: "wrap", gap: "0.6rem 1.2rem" }}>
              <label style={{ display: "flex", alignItems: "flex-start", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" defaultChecked style={{ marginTop: 3 }} />
                <div>
                  <div>PDF directory</div>
                  <div style={{ fontSize: "0.7rem", color: "#7a6f91" }}><code>{slug}.pdf</code></div>
                </div>
              </label>
              <label style={{ display: "flex", alignItems: "flex-start", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" style={{ marginTop: 3 }} />
                <div>
                  <div>HTML directory</div>
                  <div style={{ fontSize: "0.7rem", color: "#7a6f91" }}><code>{slug}/</code> · view offline</div>
                </div>
              </label>
              <label style={{ display: "flex", alignItems: "flex-start", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" defaultChecked style={{ marginTop: 3 }} />
                <div>
                  <div>email it to me</div>
                  <div style={{ fontSize: "0.7rem", color: "#7a6f91" }}>your registered address</div>
                </div>
              </label>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 6,
              padding: "0 0.7rem 0.6rem" }}>
              <Btn small onClick={() => setShowExport(false)}>cancel</Btn>
              <Btn small primary>Export</Btn>
            </div>
          </div>
        )}

        {/* Note */}
        <div style={{
          padding: "0.4em 0.6em", background: "#fffbe6",
          border: "1px dashed #e8d77a", fontSize: "0.85rem",
          color: "#444", fontStyle: "italic"
        }}>
          for the Wellington roundtable
          <a href="#" style={{ marginLeft: 8, fontStyle: "normal",
            color: C.link, textDecoration: "underline", fontSize: "0.78rem" }}>edit</a>
        </div>

        {/* Members table */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column",
          border: `1px solid ${C.border}`, background: "#fff" }}>
          <SectionHead>Members</SectionHead>
          <div style={{ flex: 1, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
              <tbody>
                {members.map(n => (
                  <tr key={n} style={{ borderBottom: `1px solid #efefef` }}>
                    <td style={{ padding: "0.35em 0.7em" }}>
                      <a href="#" onClick={(e) => e.preventDefault()}
                         style={{ color: C.link, textDecoration: "underline" }}>{n}</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{
            padding: "0.4em 0.6em", borderTop: `1px solid ${C.border}`,
            background: C.lightLavender, fontSize: "0.78rem", color: "#3b2355",
            display: "flex", justifyContent: "space-between"
          }}>
            <span>showing all {members.length} members</span>
            <span style={{ color: "#7a6f91" }}>tap <b>Edit group</b> to add or remove</span>
          </div>
        </div>
      </div>
    </AppFrame>
  );
}

window.ScreenGroupDetail = ScreenGroupDetail;
