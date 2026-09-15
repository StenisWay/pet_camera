---
name: sdlc-matrix
description: Build or update rule_doc/99_SDLC矩陣圖.md — the traceability matrix mapping every feature to its artifacts across SDLC phases (requirements, functional spec, screen spec, data model, UML diagram, implementation, test, deployment), linking only to artifacts that actually exist. Use when a feature/spec/screen/diagram is added, renamed, or completed, or when asked to create/update the SDLC matrix.
---

# SDLC traceability matrix

Maintains `rule_doc/99_SDLC矩陣圖.md`: one row per feature, one column per SDLC phase, a link
where the artifact exists and a plain status word where it doesn't. The `99` prefix is
deliberate — it sorts after every two-digit spec file so the matrix reads as an appendix/index,
not another numbered spec.

## Rule that must never be violated

**Never link to something that doesn't exist yet.** If implementation, test cases, or a
deployment record haven't been produced, that cell is a plain word (`未開始`, or `進行中` /
`已完成` once appropriate — but still no link until there is a real file/PR/artifact to point
at). A link that 404s is worse than no link — it actively misleads whoever reads the matrix
next. This is the whole reason this file is a hand-maintained matrix and not something
auto-generated from a directory listing.

## Columns (current set — extend only if a new artifact *category* appears, not per-feature)

| Column | What it links to when done |
|---|---|
| 需求 | `功能需求/00_PRD_需求書.md` (same link on every row — the PRD covers all features) |
| 功能規格 | The feature's `功能需求/0X_spec_*.md` file |
| 畫面規格(App) | The relevant `功能需求/screens/app/0X_page_*.md` file — see "Screen columns are split by platform" below |
| 畫面規格(Web) | The relevant `功能需求/screens/web/0X_page_*.md` file — same filename as the App column, different folder and content |
| 資料模型 | `功能需求/01_資料模型與儲存規格.md`, with the specific table name(s) in parentheses, e.g. (`events`) or (`users`、`refresh_tokens`). Use `-` (no link) for a feature with no dedicated table (e.g. F1 即時串流, F4 推播通知 — they don't persist their own rows) |
| UML 流程圖 | `功能需求/diagrams/0X_flow_*.drawio` — see the `drawio-flowchart` skill for how these are produced. Every functional feature should eventually have one; if it doesn't exist yet, this cell is `未開始` too. (The system architecture diagram `00_architecture_*.drawio` and the DB schema ER diagram `01_er_*.drawio` aren't rows — they're whole-project artifacts, noted once in 說明 instead.) |
| 實作 | `未開始` until real code exists, then a link to the module/PR |
| 測試 | `未開始` until real test cases exist, then a link to the test file/plan |
| 部署 | `未開始` until it has actually shipped, then a link to the release/deploy record |

### Screen columns are split by platform

Screen specs live in two parallel folders, `功能需求/screens/app/` and `功能需求/screens/web/`,
same filenames in each, because App and Web genuinely have different navigation and layout
(bottom tab bar vs top nav, single-column tab-switching vs multi-column simultaneous panels —
see `rule-doc-writer` skill). The matrix mirrors that with two separate columns rather than one
link that only shows one platform. When a feature's App and Web screen entries differ in what
they cover (e.g. F0.4 帳號設定: App has no logout item, Web does), say so in each column's
parenthetical rather than using one shared note for both.

## Process

1. **Get the authoritative feature list from the PRD**, not by guessing from the file
   listing — read `00_PRD_需求書.md` 第 3.1 節 (範圍內功能). Its `#` column (F0.1, F0.2, ...,
   F1–F6, ...) is the row order and the row labels. If the PRD adds/removes/renumbers a
   feature, the matrix must follow it, not the other way around.

2. **For each row, resolve each column** using the rules above. When a screen or data-model
   mapping isn't a clean 1:1, add the short parenthetical rather than forcing a link to
   something unrelated or leaving it blank — blank reads as "forgotten," a parenthetical
   reads as "deliberately shared."

3. **Write the table**, plus a short "說明" section below it noting: (a) any column that's
   intentionally `-` and why (no dedicated table, etc.), (b) any cross-cutting doc that
   applies to every row and so isn't itself a row (e.g. `功能需求/10_錯誤處理與狀態規範.md`,
   the app/web `02_page_導覽與全域結構.md` pair), (c) the architecture diagram and ER diagram
   links (see above), (d) that
   the diagrams are `.drawio` format and need diagrams.net or the draw.io app to open.

4. **Verify every link resolves before finishing** — don't eyeball it. From `rule_doc/`
   (note: `99_SDLC矩陣圖.md` lives at `rule_doc/` root; every link inside it points *into*
   `功能需求/`, which the grep below already accounts for since the matrix's own links carry
   that prefix):
   ```bash
   grep -oE '\]\([^)]+\)' 99_SDLC矩陣圖.md | tr -d '()]' | sed 's/^\[//' | sort -u | while read -r link; do
     case "$link" in http*) continue ;; esac   # skip external URLs like diagrams.net
     [ -f "$link" ] || echo "BROKEN: $link"
   done
   ```
   Any output means a typo'd filename or a stale reference (very common right after a
   renumbering pass) — fix it before reporting the matrix as done.

5. **Keep it in sync going forward.** This file goes stale silently, so re-run step 4 (and
   re-check step 1's row list against the PRD) whenever:
   - A new functional spec, screen spec (either platform), or diagram is added → its cell
     flips from status word to link.
   - Any file under `rule_doc/功能需求/` is renamed or renumbered (this has happened before in
     this project, including a whole-folder move) → every row referencing it needs its link
     string updated, not just the file that got renamed.
   - A feature's scope changes (e.g. a data-model table is added/removed for that feature,
     as happened when `refresh_tokens` was added for F0.1) → update that cell's parenthetical.
