// Screen 3: GROUPS PAGE — permalinked, like /about
// Lists saved groups. Inline rename, reload-into-cart, duplicate, delete, re-create.

function ScreenGroups() {
  const [groups, setGroups] = React.useState(SAVED_GROUPS);
  const [editingId, setEditingId] = React.useState(null);

  return (
    <AppFrame page="groups">
      <div style={{ padding: "0.7rem 0.9rem", display: "flex", flexDirection: "column",
        height: "100%", boxSizing: "border-box", gap: "0.6rem" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "0.9rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.15rem" }}>Groups</h2>
          <div style={{ fontSize: "0.85rem", color: C.muted }}>
            {groups.length} saved · stored in <code>fellows.db</code>
          </div>
          <div style={{ marginLeft: "auto" }}>
            <Btn primary>+ start a new group</Btn>
          </div>
        </div>

        <div style={{ border: `1px solid ${C.border}`, background: "#fff", flex: 1,
          minHeight: 0, overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem" }}>
            <thead>
              <tr style={{ background: C.rowLabel, fontSize: "0.78rem", color: "#555" }}>
                <th style={{ textAlign: "left", padding: "0.4em 0.7em", fontWeight: 600 }}>Name</th>
                <th style={{ textAlign: "left", padding: "0.4em 0.7em", fontWeight: 600, width: "85px" }}>Members</th>
                <th style={{ textAlign: "left", padding: "0.4em 0.7em", fontWeight: 600, width: "120px" }}>Created</th>
                <th style={{ textAlign: "left", padding: "0.4em 0.7em", fontWeight: 600 }}>Note</th>
                <th style={{ width: "320px", padding: "0.4em 0.7em" }}></th>
              </tr>
            </thead>
            <tbody>
              {groups.map(g => (
                <tr key={g.id} style={{ borderBottom: `1px solid #efefef` }}>
                  <td style={{ padding: "0.4em 0.7em" }}>
                    {editingId === g.id ? (
                      <input
                        autoFocus defaultValue={g.name}
                        onBlur={(e) => {
                          setGroups(prev => prev.map(x => x.id === g.id ? { ...x, name: e.target.value } : x));
                          setEditingId(null);
                        }}
                        style={{ padding: "0.2rem 0.4rem", fontSize: "0.88rem",
                          border: "1px solid #bbb", borderRadius: 2 }}
                      />
                    ) : (
                      <a href="#" onClick={(e) => e.preventDefault()}
                         title="open this group"
                         style={{ color: C.link, textDecoration: "underline", fontWeight: 500 }}>
                        {g.name}
                      </a>
                    )}
                  </td>
                  <td style={{ padding: "0.4em 0.7em", color: "#444" }}>{g.count}</td>
                  <td style={{ padding: "0.4em 0.7em", color: "#666",
                    fontFamily: "ui-monospace, monospace", fontSize: "0.78rem" }}>{g.created}</td>
                  <td style={{ padding: "0.4em 0.7em", color: "#666", fontStyle: g.note ? "italic" : "normal" }}>
                    {g.note || <span style={{ color: "#bbb" }}>—</span>}
                  </td>
                  <td style={{ padding: "0.4em 0.7em", textAlign: "right", whiteSpace: "nowrap" }}>
                    <a href="#" onClick={(e) => e.preventDefault()}
                       title="open the visual portrait directory"
                       style={{ color: C.link, textDecoration: "underline", marginRight: 10, fontSize: "0.8rem" }}>view directory</a>
                    <a href="#" onClick={(e) => { e.preventDefault(); setEditingId(g.id); }}
                       style={{ color: C.link, textDecoration: "underline", marginRight: 10, fontSize: "0.8rem" }}>rename</a>
                    <a href="#" onClick={(e) => {
                      e.preventDefault();
                      setGroups(prev => prev.filter(x => x.id !== g.id));
                    }}
                       style={{ color: "#7a1f1f", textDecoration: "underline", marginRight: 10, fontSize: "0.8rem" }}>delete</a>
                    <a href="#" onClick={(e) => e.preventDefault()}
                       title="add or remove members from this group"
                       style={{ color: C.link, textDecoration: "underline", fontSize: "0.8rem" }}>edit</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ fontSize: "0.78rem", color: "#7a6f91", lineHeight: 1.5 }}>
          Click a group's name to open its detail page — that's where you edit, view, and export it.
          Deleting only removes the saved group; the fellows themselves are unaffected.
        </div>
      </div>
    </AppFrame>
  );
}

window.ScreenGroups = ScreenGroups;
