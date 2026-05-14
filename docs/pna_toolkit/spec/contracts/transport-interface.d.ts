// Communications slot — the transport interface every comms transport
// implements. Sub-contracts CO-1 through CO-6 from `_pna_triage.md` Part 4.
//
// A Transport is a pluggable outreach mechanism — mailto, signal-cli, a
// Matrix bridge, a future P2P pubkey-based channel. The workspace surfaces
// the user's configured transports and lets the user pick per outreach
// (AC-16). The transport's only job is to launch the user's external
// client (or in-bundle handler) with the composed payload pre-populated —
// it MUST NOT send autonomously, and it MUST NOT read message content
// (AC-18). The workspace shows the full payload to the user before any
// transport is launched (AC-19); the transport sees what the user already
// approved.
//
// CO-3 (transport eligibility, AC-18) is enforced by the workspace's
// transport-registration logic: a candidate Transport whose mechanism
// could read message contents is refused at register time. The interface
// below describes the runtime contract; the eligibility check is a build-
// time / registration-time decision on top of it.
//
// CO-6: This interface is for *workspace-launched* user outreach. The
// distribution-mechanism's auth-link transport (Postmark in
// fellows_local_db's magic-link distribution flavor) is governed by the
// Distribution slot's contracts, NOT by this interface. They look similar
// — both deliver bytes to a user — but their AC sets and trust postures
// are different.

/**
 * The fixed v0.1 action enum (CO-2). New action values can be added with
 * toolkit version bumps; transports are free to canHandle() a subset.
 *
 * - `email_one` — one recipient, visible To.
 * - `email_group_cc` — multiple recipients, visible Cc.
 * - `email_group_bcc` — multiple recipients, blind Bcc (privacy-preserving
 *   for group sends; the recommended default for >1 recipients).
 * - `direct_message_one` — one recipient via a DM channel (Signal, Matrix DM,
 *   etc.). Format depends on the transport's protocol.
 * - `share_link_one` — share a single URL to one recipient.
 * - `share_link_group` — share a single URL to multiple recipients.
 */
export type TransportAction =
  | "email_one"
  | "email_group_cc"
  | "email_group_bcc"
  | "direct_message_one"
  | "share_link_one"
  | "share_link_group";

/**
 * Static description a transport publishes about itself. The workspace
 * uses this to render the user's transport-picker (the "reach out via …"
 * menu) and to record which transport launched a given outreach in the
 * optional `record_comms_history` Private DB table (PR-2).
 */
export interface TransportDescriptor {
  /**
   * Stable identifier. Used as the key the user's transport-preference
   * settings are stored under and as the `transport` value in
   * `record_comms_history`. Snake-case ASCII.
   * Examples: `"mailto"`, `"signal_cli"`, `"matrix"`.
   */
  id: string;

  /** Human-readable label shown in the workspace's transport-picker. */
  name: string;

  /**
   * Optional self-reported security tier for UI sorting / labeling. The
   * workspace MAY use this to order the picker (more-secure first) and to
   * render a small badge ("encrypted in protocol"). NOT used as a gate —
   * AC-18 eligibility is enforced at registration time, not via this
   * advisory field.
   */
  secureLevel?: "plaintext" | "in-transit" | "end-to-end";

  /**
   * Optional human-readable note shown alongside the transport in the
   * picker (e.g., "requires Signal Desktop installed", "uses your default
   * mail client"). UI-only.
   */
  note?: string;
}

/**
 * Result of a launch call. Returned to the workspace so it can surface
 * outcome to the user and (when comms history is enabled — PR-2) record
 * the outreach.
 */
export interface LaunchResult {
  /**
   * `true` when the external client / handler was successfully invoked.
   * `false` when the transport refused (e.g., no recipients, payload
   * exceeded the transport's hard limit) — the workspace surfaces
   * `error` to the user.
   */
  ok: boolean;

  /** Human-readable error message when `ok === false`. */
  error?: string;

  /**
   * Transport-specific structured metadata for diagnostics or history —
   * e.g., `{ mailto_url_byte_length: 1487, recipient_count: 5 }` for the
   * mailto transport. The workspace MAY persist this into
   * `record_comms_history.summary` (or a transport-specific extension);
   * the spec does not pin the shape.
   */
  meta?: Record<string, unknown>;
}

/**
 * Payload passed to `launch()`. Shape is action-dependent; the workspace
 * has already validated and shown it to the user (AC-19) before calling.
 */
export interface LaunchPayload {
  /** Visible primary recipients. May be empty for BCC-only group sends. */
  to?: string[];

  /** Carbon-copied recipients. */
  cc?: string[];

  /** Blind-carbon-copied recipients. */
  bcc?: string[];

  /** Subject (email-style transports) / title (link-share transports). */
  subject?: string;

  /** Message body. */
  body?: string;

  /** URL to share (used by `share_link_*` actions). */
  url?: string;

  /**
   * Transport-specific extension fields. The workspace pre-shows these to
   * the user (AC-19); transports MUST NOT add fields here that the
   * workspace didn't surface.
   */
  extras?: Record<string, unknown>;
}

/**
 * CO-1: the interface every Communications transport implements.
 *
 * The workspace registers configured transports at startup (each
 * registration is gated on AC-18 eligibility — mechanism cannot read
 * message contents). At outreach time the workspace:
 *
 *   1. Asks each registered transport whether it `canHandle(action)`.
 *   2. Shows the user a picker of the transports that returned `true`.
 *   3. The user composes / reviews the full payload (AC-19).
 *   4. The workspace calls `launch(action, payload)` on the chosen
 *      transport.
 *   5. On `ok: true`, optionally records the outreach in
 *      `record_comms_history` if PR-2 is enabled.
 *
 * Transports MUST be stateless across calls. State that persists across
 * outreaches (per-recipient nicknames, address-book mappings) lives in
 * the Private DB, not in the transport.
 */
export interface Transport {
  /**
   * Returns true when this transport can handle the given action.
   * The workspace calls this to populate the user's transport-picker.
   * Cheap; must not perform I/O.
   */
  canHandle(action: TransportAction): boolean;

  /**
   * Launch the user's external client (or in-bundle handler) with the
   * composed payload pre-populated. The transport MUST NOT send
   * autonomously — opening a URL, spawning a process, or invoking the
   * OS's share sheet is acceptable; transmitting the payload itself
   * is not (AC-18).
   *
   * The workspace has already shown the user the full payload (AC-19);
   * the transport's job is to hand it off.
   *
   * Returns a Promise so transports that need an async handshake (e.g.,
   * checking that `signal-cli` is reachable) can resolve when ready.
   */
  launch(action: TransportAction, payload: LaunchPayload): Promise<LaunchResult>;

  /**
   * Static self-description. Stable across calls. Used by the workspace
   * for picker rendering and history attribution.
   */
  descriptor(): TransportDescriptor;
}
