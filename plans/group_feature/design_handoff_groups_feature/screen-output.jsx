// Screen 4: OUTPUT PREVIEW — what `create` produces.
// A self-contained HTML directory: alphabetical portrait grid with a popup
// showing name + contact info on click. This artboard mocks the *exported*
// page so you can see what gets written to disk.

function ScreenOutputPreview() {
  const members = [
    "Tatyana Mikayilova", "Tesh Randall", "Tilla Abbitt", "Tillie Walton",
    "Tim Derrick", "Tim Ferriss", "Tim Pare", "Tina Jennen", "Tony Lai",
    "Tracy Chou", "Trevor Squier", "Tristan Harris", "Vanessa Coleman",
    "Vicky Robertson"
  ].sort();
  const [openName, setOpenName] = React.useState("Tony Lai");
  const open = members.find(n => n === openName);
  const f = open ? FELLOWS.find(ff => ff.name === open) : null;

  return (
    <div style={{
      width: "100%", height: "100%",
      background: "#fafafa", color: "#222",
      fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      display: "flex", flexDirection: "column", overflow: "hidden", position: "relative"
    }}>
      {/* Browser-style chrome to make it clear this is the EXPORTED file */}
      <div style={{
        background: "#e8e4ef", padding: "0.4rem 0.7rem", fontSize: "0.78rem",
        color: "#3b2355", borderBottom: "1px solid #c9c2d4",
        display: "flex", gap: 8, alignItems: "center"
      }}>
        <span style={{ fontFamily: "ui-monospace, monospace" }}>
          file:///environment-pickleball-folks/index.html
        </span>
        <span style={{ marginLeft: "auto", fontStyle: "italic" }}>
          ↑ this is the exported portable directory (offline, sharable)
        </span>
      </div>

      <div style={{ padding: "1.2rem 1.6rem", flex: 1, overflow: "auto" }}>
        <h1 style={{ margin: "0 0 0.2rem", fontSize: "1.4rem" }}>Environment + pickleball folks</h1>
        <div style={{ fontSize: "0.85rem", color: "#666", marginBottom: "0.5rem" }}>
          {members.length} fellows · created Apr 28, 2026 · for Wairarapa weekend
        </div>

        {/* Group action bar */}
        <div style={{
          display: "flex", alignItems: "center", gap: "0.75rem",
          padding: "0.5rem 0.7rem", marginBottom: "1rem",
          background: "#f0ecf5", border: "1px solid #dcd6e8", borderRadius: 3,
          fontSize: "0.85rem"
        }}>
          <a href={`mailto:?cc=${members.map(n => `${n.split(" ")[0].toLowerCase()}@example.com`).join(",")}&subject=${encodeURIComponent("Environment + pickleball folks")}`}
            style={{ color: C.link, textDecoration: "underline", fontWeight: 500 }}>
            ✉ Contact the whole group
          </a>
          <span style={{ color: "#7a6f91", fontSize: "0.78rem" }}>
            opens your mail client with everyone in CC
          </span>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
          gap: "0.9rem"
        }}>
          {members.map(n => (
            <button key={n} onClick={() => setOpenName(n)}
              style={{
                background: "transparent", border: "none", padding: 0,
                cursor: "pointer", textAlign: "center", fontFamily: "inherit"
              }}>
              <div style={{
                width: "100%", aspectRatio: "1 / 1", borderRadius: "50%",
                backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80'><rect width='80' height='80' fill='%23d9cfc1'/><circle cx='40' cy='32' r='14' fill='%23a89682'/><path d='M14 76c4-16 18-22 26-22s22 6 26 22z' fill='%23a89682'/></svg>")`,
                backgroundSize: "cover", backgroundPosition: "center",
                border: "1px solid #ccc"
              }} title={`portrait of ${n}`} />
              <div style={{ fontSize: "0.78rem", marginTop: 4, lineHeight: 1.2 }}>{n}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Popup */}
      {open && (
        <div onClick={() => setOpenName(null)}
          style={{
            position: "absolute", inset: 0,
            background: "rgba(30, 25, 50, 0.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 10
          }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{
              background: "#fff", border: "1px solid #ccc", borderRadius: 4,
              padding: "1rem 1.1rem", width: 360, boxShadow: "0 6px 24px rgba(0,0,0,0.18)",
              position: "relative"
            }}>
            <button onClick={() => setOpenName(null)} aria-label="close"
              style={{
                position: "absolute", top: 6, right: 8,
                background: "transparent", border: "none", fontSize: 18,
                cursor: "pointer", color: "#888"
              }}>×</button>
            <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 10 }}>
              <div style={{
                width: 80, height: 80, borderRadius: "50%",
                backgroundImage: `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 80'><rect width='80' height='80' fill='%23d9cfc1'/><circle cx='40' cy='32' r='14' fill='%23a89682'/><path d='M14 76c4-16 18-22 26-22s22 6 26 22z' fill='%23a89682'/></svg>")`,
                backgroundSize: "cover", backgroundPosition: "center",
                border: "1px solid #ccc",
                display: "flex", alignItems: "flex-end", justifyContent: "center",
                fontSize: "0.6rem", fontWeight: 600, color: "#fff",
                textShadow: "0 1px 1px rgba(0,0,0,0.4)", paddingBottom: 2
              }}>{initials(open)}</div>
              <div>
                <div style={{ fontSize: "1.05rem", fontWeight: 600 }}>{open}</div>
                <div style={{ fontSize: "0.78rem", color: "#666" }}>real photo from <code>fellows.db</code> images table</div>
              </div>
            </div>
            <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: "0 0.3em", fontSize: "0.85rem" }}>
              <tbody>
                {f?.email && (
                  <tr><td style={{ background: "#f0f0f0", padding: "0.3em 0.5em", fontWeight: 600, width: "32%" }}>email</td>
                    <td style={{ padding: "0.3em 0.5em" }}>
                      <a href={`mailto:${open.split(" ")[0].toLowerCase()}@example.com`}>
                        {open.split(" ")[0].toLowerCase()}@example.com
                      </a></td></tr>
                )}
                <tr><td style={{ background: "#f0f0f0", padding: "0.3em 0.5em", fontWeight: 600, width: "32%" }}>phone</td>
                  <td style={{ padding: "0.3em 0.5em" }}><a href="#" onClick={(e) => e.preventDefault()}>+64 21 555 0142</a></td></tr>
                <tr><td style={{ background: "#f0f0f0", padding: "0.3em 0.5em", fontWeight: 600 }}>linkedin</td>
                  <td style={{ padding: "0.3em 0.5em" }}><a href="#" onClick={(e) => e.preventDefault()}>linkedin.com/in/{open.split(" ")[0].toLowerCase()}</a></td></tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

window.ScreenOutputPreview = ScreenOutputPreview;
