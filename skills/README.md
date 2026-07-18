# Skills used by this project

Vendored Claude Code skill collections and agent frameworks, each
**security-vetted before download** (see [Security vetting](#security-vetting)).
14 sources · ~7,500 files · ~166 MB · 578 `SKILL.md` scanned.

> These are third-party sources (except the four first-party Anthropic ones,
> noted below). They are stored here as reference/source. **No install script or
> hook from any of them has been run.** A skill activates only when Claude Code
> loads it from a skills directory or you install it deliberately. `git clone`
> executes nothing, so these files are inert on disk.

## Inventory

### Finance & trading (the stock platform)

| Folder | Source | ★ | License | What it is |
| ------ | ------ | - | ------- | ---------- |
| `financial-services/` | anthropics/financial-services | 33k | Apache-2.0 | **First-party Anthropic.** DCF models, XLS audit, IB deck checks; 7 finance verticals + 10 agent plugins. |
| `claude-trading-skills/` | tradermonty/claude-trading-skills | 2.4k | MIT | 70+ equity skills: technical analysis, backtesting, breadth/sector, screeners (VCP, CANSLIM), FMP data fetchers. |
| `ai-trading-claude/` | zubair-trabzada/ai-trading-claude | 197 | MIT | `/trade` orchestrator + 15 sub-skills + 5 agents; PDF reports. |

### Design & frontend (the React UI)

| Folder | Source | ★ | License | What it is |
| ------ | ------ | - | ------- | ---------- |
| `frontend-design/` | anthropics/claude-code · `plugins/frontend-design` | — | — | **First-party Anthropic.** Frontend design guidance skill. |
| `ui-ux-pro-max/` | nextlevelbuilder/ui-ux-pro-max-skill | 107k | MIT | 84 UI styles, 161 palettes, 73 font pairings, UX guidelines across 17 stacks. |
| `motion-framer/` | freshtechbro/claudedesignskills · `motion-framer` | 567 | MIT | Motion (Framer Motion) animation skill: variants, gestures, springs, scroll. |

### Dev workflow, review & quality

| Folder | Source | ★ | License | What it is |
| ------ | ------ | - | ------- | ---------- |
| `code-review-skill/` | awesome-skills/code-review-skill | 1.4k | MIT | Language-specific review guides (used in our `/code-review` passes). |
| `claude-code-security-review/` | anthropics/claude-code-security-review | 5.5k | — | **First-party Anthropic.** AI security-review GitHub Action. |
| `skill-creator/` | anthropics/claude-plugins-official · `plugins/skill-creator` | 32k | — | **First-party Anthropic.** Scaffolds new skills. |
| `superpowers/` | obra/superpowers | 256k | MIT | Agent skills framework (brainstorming, systematic debugging, SDD). |
| `gsd-core/` | open-gsd/gsd-core | — | MIT | GSD spec-driven workflow (the archived `gsd-build/get-shit-done` moved here). |
| `gstack/` | garrytan/gstack | 122k | MIT | Opinionated toolkit (office-hours, qa, ship, design-review, cso). |
| `ruflo-skills/` | ruvnet/ruflo | 65k | MIT | **Skills-only subset** of the ruflo meta-harness (see note). |

### Memory

| Folder | Source | ★ | License | What it is |
| ------ | ------ | - | ------- | ---------- |
| `claude-mem/` | thedotmack/claude-mem | 87k | MIT | Persistent cross-session memory. **Read the note below before relying on it.** |

## Security vetting

Vetted read-only on **2026-07-18** before download — skills can carry scripts,
auto-running hooks, and prompt-injection in the instructions Claude reads:

- **No npm `postinstall`/`preinstall` hooks** in any of the 14 sources — nothing
  auto-executes on install. (claude-mem installs via an explicit `npx claude-mem
  install`, not a silent hook.)
- **Prompt injection** — scanned all **578 `SKILL.md`** files. Zero malicious
  instructions. The only keyword hits were legitimate: `<script>` inside
  HTML/design-generation skills, and defensive content (a skill teaching the
  agent to *resist* "ignore previous instructions" from untrusted issue text; an
  AI-defense skill that *lists* exfiltration as a thing to detect).
- **Network endpoints** — all outbound calls go to expected destinations:
  Anthropic/Claude APIs, GitHub, `financialmodelingprep.com` (market data),
  LLM providers, official Bun/uv installers, and the tools' own domains. No
  Discord/Slack/pastebin/ngrok/raw-IP exfiltration. The `curl … | bash` strings
  are all documentation or official-installer references, never hidden execution.
- **No** reverse shells (`/dev/tcp`), miners (`xmrig`/`stratum`),
  decode-and-execute, or unexpected credential-file reads. No executables or
  binaries (only chart JPEGs and `.skill` archive bundles).
- `gsd-core` is itself security-conscious — it ships its own
  `prompt-injection-scan.sh`, `base64-scan.sh`, and `secret-scan.sh`, plus
  symlink-attack defenses.

**Verdict: all 14 sources passed. None rejected.** Two informed-consent notes:

### ⚠️ claude-mem reads your Claude credentials + sends telemetry

`claude-mem` is legitimate and popular, but it is the most privacy-invasive of
the set, and it is **already installed** (as a plugin, from an earlier session):

- It reads your **Claude Code OAuth token** from the OS credential store (macOS
  Keychain / Windows Credential Manager / Linux libsecret, service
  `"Claude Code-credentials"`) and reuses it to call the Claude API on your
  behalf to summarize/embed memories. The token goes only to Anthropic — it is
  not sent to third parties — but the tool is using your credentials and your
  API quota.
- It sends **telemetry to PostHog and crash reports to Sentry**, and offers
  optional cloud sync of memories to `cmem.ai`.
- On macOS it also reads the **Zscaler** corporate-proxy root CA from the
  keychain to fix TLS behind a proxy (same class of fix as this repo's Avast
  workaround) — a public cert, not a secret.

None of that is malicious, but decide knowingly. To remove it:
`claude plugin uninstall claude-mem@thedotmack`.

### ⚠️ Heavyweight frameworks with hooks

`superpowers`, `gstack`, `gsd-core`, and `ruflo` are full frameworks whose hooks
auto-run **only if wired into `settings.json`**. Vendoring the files here is
inert; don't blindly wire their hooks or run their installers.

**ruflo** is a 5,250-file agent *meta-harness*, not a skill pack — only its
skill content was vendored (`.claude/skills`, `.agents/skills`,
`plugins/ruflo-aidefence`). Its daemons, Rust crate, binary DB, install scripts,
and hooks were **intentionally excluded**.

## ⚠️ Size / git note

This folder is ~166 MB across ~7,500 files of external tooling with their own
licenses and (for claude-mem) telemetry. It is **not committed** and `.gitignore`
was **not** modified — you choose whether to vendor this into git. Recommended:
add `skills/` to `.gitignore` (or commit only the finance/design folders you
actually want versioned) rather than committing all 166 MB of frameworks.
