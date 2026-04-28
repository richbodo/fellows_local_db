// Screen: BROWSE + ADD-TO-GROUP
// The right rail is "add to a group" with an auto-generated, editable title
// (search query / #tag) and a single "Create new group" button.
// mode="new"  — composing a fresh group
// mode="edit" — editing a saved group (yellow banner, "Done editing")

function ScreenBrowse({
  mode = "new",
  initialQuery = "",
  initialPicked,
  customTitle,         // explicitly typed title (we treat as user-edited)
  initialHasEmail,
  activeName,          // override the open detail card
}) {
  const [picked, setPicked] = React.useState(new Set(initialPicked || []));
  const [query, setQuery] = React.useState(initialQuery);
  const [hasEmail, setHasEmail] = React.useState(
    initialHasEmail !== undefined ? initialHasEmail : false
  );
  const [active, setActive] = React.useState(activeName || initialPicked?.[0] || null);

  // Auto-generated group title that follows the search,
  // unless the user has typed their own (we seed titleEdited true if customTitle given).
  const autoTitle = React.useMemo(() => {
    if (!query) return "";
    if (query.startsWith("#")) return query;
    return query.replace(/^./, c => c.toUpperCase());
  }, [query]);
  const [titleEdited, setTitleEdited] = React.useState(!!customTitle);
  const [title, setTitle] = React.useState(customTitle || autoTitle);
  React.useEffect(() => {
    if (!titleEdited) setTitle(autoTitle);
  }, [autoTitle, titleEdited]);

  const visible = FELLOWS.filter(f => {
    if (hasEmail && !f.email) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    if (q.startsWith("#")) {
      const tag = q.slice(1);
      return f.tags.some(t => t.includes(tag));
    }
    return f.name.toLowerCase().includes(q)
        || f.tags.some(t => t.includes(q));
  });

  const allVisibleSelected = visible.length > 0 && visible.every(f => picked.has(f.name));
  const activeFellow = FELLOWS.find(f => f.name === active);

  const toggle = (name) => setPicked(prev => {
    const n = new Set(prev);
    if (n.has(name)) n.delete(name); else n.add(name);
    return n;
  });

  const toggleAllVisible = () => setPicked(prev => {
    const n = new Set(prev);
    if (allVisibleSelected) visible.forEach(f => n.delete(f.name));
    else visible.forEach(f => n.add(f.name));
    return n;
  });

  const isEdit = mode === "edit";
  const titleAutoFollowing = !titleEdited;

  return (
    <AppFrame page="directory">
      {/* Edit-mode banner */}
      {isEdit && (
        <div style={{
          padding: "0.4rem 0.75rem",
          background: "#fff3cd", borderBottom: "1px solid #ffe69c",
          fontSize: "0.85rem", color: "#664d03",
          display: "flex", gap: "0.6rem", alignItems: "center"
        }}>
          <span>✎ <b>editing</b> "{title}" — search and tap <b>+</b> to add more, tap <b>✓</b> to remove.</span>
          <a href="#" title="revert this group to the state it was in when you opened edit mode"
             style={{ marginLeft: "auto", color: "#664d03", textDecoration: "underline" }}>cancel edits</a>
        </div>
      )}

      <div style={{ display: "flex", height: "100%", padding: "0.6rem", gap: "0.75rem", boxSizing: "border-box" }}>
        {/* Sidebar / directory list */}
        <div style={{ flex: "0 0 250px", display: "flex", flexDirection: "column",
          minHeight: 0, fontSize: "0.9rem" }}>
          <label style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.25rem" }}>Search</label>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="name, tag, or #tag"
            style={{
              padding: "0.25rem 0.5rem", fontSize: "0.9rem",
              border: `1px solid #bbb`, borderRadius: 2, marginBottom: 4
            }}
          />
          <div style={{ fontSize: "0.7rem", color: "#7a6f91", marginBottom: 4 }}>
            tip: <code>#walking</code> searches by tag
          </div>
          <div style={{
            display: "flex", justifyContent: "space-between",
            fontSize: "0.78rem", color: "#555", margin: "0.2rem 0 0.4rem"
          }}>
            <label style={{ display: "inline-flex", gap: 4, alignItems: "center", cursor: "pointer" }}>
              <input type="checkbox" checked={hasEmail} onChange={(e) => setHasEmail(e.target.checked)} />
              has email only
            </label>
            <span>{visible.length} of {FELLOWS.length}</span>
          </div>

          {/* Bulk-select bar (only show when filtered) */}
          {(query || hasEmail) && visible.length > 0 && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "4px 6px", margin: "0 0 2px",
              background: C.lightLavender, border: `1px solid ${C.lavenderBorder}`,
              borderRadius: 2, fontSize: "0.78rem"
            }}>
              <input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible}
                style={{ margin: 0 }} />
              <span style={{ color: "#3b2355", fontWeight: 500 }}>
                {allVisibleSelected ? "deselect" : "select"} all {visible.length} results
              </span>
            </div>
          )}

          {/* List */}
          <div style={{ flex: 1, overflow: "auto", paddingRight: 4 }}>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {visible.map(f => {
                const on = picked.has(f.name);
                const isActive = active === f.name;
                return (
                  <li key={f.name}
                    onClick={() => setActive(f.name)}
                    style={{
                      display: "flex", alignItems: "center", gap: 4,
                      padding: "2px 4px",
                      background: isActive ? "#e8e0f0" : "transparent",
                      cursor: "pointer"
                    }}>
                    <span
                      onClick={(e) => { e.stopPropagation(); toggle(f.name); }}
                      title={on ? "remove from group" : "add to group"}
                      style={{
                        width: 16, textAlign: "center",
                        fontSize: 14, lineHeight: 1, fontWeight: 700,
                        color: on ? C.purple : "#bbb",
                        userSelect: "none"
                      }}>{on ? "✓" : "+"}</span>
                    <a href="#" onClick={(e) => e.preventDefault()}
                      style={{ color: C.link, textDecoration: "underline", fontSize: "0.88rem" }}>
                      {f.name}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        {/* Detail pane */}
        <div style={{
          flex: 1, minWidth: 0, padding: "0.75rem 0.9rem",
          border: `1px solid ${C.border}`, background: "#fff",
          overflow: "auto", display: "flex", flexDirection: "column", gap: "0.6rem"
        }}>
          {activeFellow ? (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem",
                paddingBottom: "0.4rem", borderBottom: `1px solid ${C.border}` }}>
                <div style={{ fontSize: "1rem", fontWeight: 600 }}>{activeFellow.name}</div>
                <a href="#" onClick={(e) => { e.preventDefault(); toggle(activeFellow.name); }}
                  style={{ fontSize: "0.8rem", color: C.link, textDecoration: "underline" }}>
                  {picked.has(activeFellow.name) ? "remove from group" : "add to group"}
                </a>
                <div style={{ marginLeft: "auto", fontSize: "0.72rem", color: "#7a6f91" }}>
                  your tags: {activeFellow.tags.map(t => <Tag key={t}>{t}</Tag>)}
                  <span style={{ marginLeft: 4, color: "#aaa" }}>+ add</span>
                </div>
              </div>
              <SectionHead>How to Connect</SectionHead>
              <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: "0 0.4em", fontSize: "0.85rem" }}>
                <tbody>
                  <tr><td style={{ background: C.rowLabel, padding: "0.3em 0.5em", fontWeight: 600, width: "32%" }}>Status</td>
                    <td style={{ padding: "0.3em 0.5em" }}>Active Fellow</td></tr>
                  <tr><td style={{ background: C.rowLabel, padding: "0.3em 0.5em", fontWeight: 600 }}>Email</td>
                    <td style={{ padding: "0.3em 0.5em" }}>
                      <a href="#" onClick={(e) => e.preventDefault()} style={{ color: C.link }}>
                        {activeFellow.name.split(" ")[0].toLowerCase()}@example.com
                      </a>
                    </td></tr>
                </tbody>
              </table>
            </>
          ) : (
            <div style={{ color: "#888", fontSize: "0.85rem", padding: "1rem 0", textAlign: "center" }}>
              Select a fellow on the left to view their details.
            </div>
          )}
        </div>

        {/* Right rail — "add to a group" */}
        <div style={{
          flex: "0 0 240px", display: "flex", flexDirection: "column",
          minHeight: 0,
          border: `1px solid ${C.lavenderBorder}`, background: C.lightLavender,
          padding: "0.55rem 0.6rem"
        }}>
          <div style={{ fontSize: "0.78rem", color: "#7a6f91", textTransform: "uppercase",
            letterSpacing: "0.04em", marginBottom: 3 }}>
            {isEdit ? "editing group" : "add to a group"}
          </div>

          {/* Title field — soft tinted bg + ✎ icon when auto-following; solid white when user-edited */}
          <div style={{ position: "relative", marginBottom: 2 }}>
            <input
              value={title}
              onChange={(e) => { setTitle(e.target.value); setTitleEdited(true); }}
              placeholder="name your group…"
              style={{
                fontSize: "0.95rem", fontWeight: 600,
                padding: "0.25rem 0.4rem 0.25rem " + (titleAutoFollowing && !isEdit ? "1.45rem" : "0.4rem"),
                border: `1px solid ${C.lavenderBorder}`,
                borderRadius: 2,
                background: titleAutoFollowing && !isEdit ? "#fff7d6" : "#fff",
                boxSizing: "border-box", width: "100%",
                fontStyle: titleAutoFollowing && !isEdit && !title ? "italic" : "normal",
                color: titleAutoFollowing && !isEdit && title ? "#7a6326" : C.ink,
              }}
            />
            {titleAutoFollowing && !isEdit && (
              <span style={{
                position: "absolute", left: 6, top: "50%", transform: "translateY(-50%)",
                fontSize: "0.85rem", color: "#a8923a", pointerEvents: "none"
              }}>✎</span>
            )}
          </div>
          <div style={{ fontSize: "0.7rem", color: "#7a6f91", marginBottom: 6 }}>
            {titleAutoFollowing && !isEdit && query
              ? <>auto-named — click to rename · {picked.size} fellows</>
              : titleAutoFollowing && !isEdit
                ? <>type a name, or search to auto-fill · {picked.size} fellows</>
                : <>{picked.size} fellows</>}
          </div>
          <div style={{ flex: 1, overflow: "auto", marginBottom: 6,
            border: `1px solid ${C.lavenderBorder}`, background: "#fff", padding: "0.25rem 0.4rem" }}>
            {[...picked].length === 0 && (
              <div style={{ fontSize: "0.78rem", color: "#888", padding: "0.4rem 0" }}>
                tap <b style={{ color: C.purple }}>+</b> next to a name to add. Search again to add more.
              </div>
            )}
            {[...picked].map(n => (
              <div key={n} style={{
                display: "flex", alignItems: "center", gap: 4,
                padding: "1px 0", fontSize: "0.78rem"
              }}>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {n}
                </span>
                <span onClick={() => toggle(n)} title="remove"
                  style={{ color: "#999", cursor: "pointer", fontFamily: "ui-monospace, monospace", fontSize: 11 }}>×</span>
              </div>
            ))}
          </div>
          <Btn primary style={{ width: "100%" }} disabled={!isEdit && picked.size === 0}>
            {isEdit ? "Done editing" : "Create new group"}
          </Btn>
          <div style={{ fontSize: "0.7rem", color: "#7a6f91", marginTop: 4, lineHeight: 1.4 }}>
            {isEdit
              ? "changes save automatically as you add or remove."
              : "saves immediately to your groups. You can rename and edit it later."}
          </div>
        </div>
      </div>
    </AppFrame>
  );
}

window.ScreenBrowse = ScreenBrowse;
