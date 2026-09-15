---
name: rule-doc-writer
description: Write or extend this project's requirements/spec document set under rule_doc/功能需求/ — the PRD (00_PRD_需求書.md), per-feature functional specs (0X_spec_*.md), shared cross-cutting docs (data model, error/state handling), and screen/page specs (screens/0X_page_*.md). Use when asked to write a 需求書/規劃書/規格書, add a new feature's spec, or split/reorganize existing specs.
---

# Requirements & spec document writer

Produces this project's documentation set as a real, decisive product spec — not a hedged
draft. The single biggest failure mode here is writing prose that *explains and justifies*
decisions (demo-project caveats, "為了避免...", "MVP 先...之後再議") instead of just *stating*
them. State the decision; put rationale only where a future reader genuinely needs it to judge
an edge case (see feedback rule below).

## Folder layout

`rule_doc/` itself holds only `99_SDLC矩陣圖.md` (the index — see the `sdlc-matrix` skill).
Everything this skill produces lives one level down, in `rule_doc/功能需求/`, so that the
top level stays a single entry point. Don't write a new top-level file here without a strong
reason — it breaks that separation.

## Document types (don't blur these together)

| Type | File pattern | Location | Defines |
|---|---|---|---|
| PRD | `00_PRD_需求書.md` | `rule_doc/功能需求/` | Whole-product scope, NFRs, architecture, roadmap. One per project. |
| Shared/cross-cutting spec | `01_資料模型與儲存規格.md`, `10_錯誤處理與狀態規範.md` | `rule_doc/功能需求/` | Things every feature spec references instead of redefining: DB schema, R2/storage layout, global error codes, the 4-state UI model. Write these **before** the per-feature specs that depend on them. |
| Functional spec | `0X_spec_<功能名>.md` | `rule_doc/功能需求/` | One per feature (one row in the PRD's scope table). Behavior, API, feature-specific error codes, loading states, acceptance criteria. |
| Screen/page spec | `0X_page_<畫面名>.md` | `rule_doc/功能需求/screens/app/` and `.../screens/web/` (same filename, one file per platform) | One per UI screen per platform. Layout and navigation **only** — behavior/API/errors live in the functional spec(s) it references, never duplicated here. |

If asked for "流程圖" or "SDLC 矩陣圖" for these, that's a separate step — see the
`drawio-flowchart` and `sdlc-matrix` skills, which consume what this skill produces.

## Process

1. **Nail down MVP scope before writing anything**, if it's genuinely ambiguous — which
   features are in v1, what client platforms (native app / web / both), who the doc is for
   (interview portfolio / client deliverable / build blueprint — this affects how much
   architecture-decision framing to keep, but never affects the decisiveness of the language).
   Ask via AskUserQuestion rather than guessing a large scope call; don't ask about things you
   can reasonably default (naming conventions, table field names, minor error-code numbering).

2. **Write the PRD first.** It's the single source of truth for the feature list — every
   downstream file (functional spec, screen spec, diagram, SDLC matrix row) must trace back to
   a row in its scope table (§3.1), not be invented independently. PRD sections, in order:
   文件資訊表 → 產品背景 → 產品目標與目標使用者 → MVP範圍(範圍內/範圍外功能表,每列一個 F-number
   + 優先級 + 對應規格書連結)→ 核心使用者故事 → 系統架構(圖 + 已定案的架構決策,陳述式,不附
   理由鋪陳)→ NFR 表 → 里程碑規劃 → 名詞定義 → 關聯文件列表. Add a 瓶頸分析 section only if the
   project has a genuine resource-constraint story to tell (e.g. free-tier infra limits).

3. **Write shared/cross-cutting docs next**, before any feature spec that needs them:
   - Data model doc: one `###` subsection per table (fields/types/notes), a storage-key naming
     convention if there's an object store involved, a lifecycle/retention table, a state-machine
     section per entity that has one, and a deletion/cascade-rule table for every destructive
     action (device removal, account deletion, etc.) — this belongs here, not scattered across
     feature specs, because multiple features trigger the same cascade.
   - Error/state handling doc: the UI state model (Loading/Empty/Error/Loaded — define once),
     error *display* categories (full-page / inline / toast / modal, with when-to-use-which),
     and the **global** error code table only (auth/network/server/rate-limit/validation).
     Feature-specific codes do NOT go here.

4. **Write one functional spec per feature**, fixed section order:
   ```
   metadata table (優先級 | 相依功能 | 資料模型 | 共用規範 | NFR if relevant)
   1. 使用者故事
   2. 功能說明 (2.1, 2.2, ... — one subsection per distinct behavior; put a 平台差異
      subsection/table here, not a separate document, whenever App/Web genuinely differ —
      e.g. different token lifetimes, different push mechanisms)
   3. API 介面 (table: Method | Path | 說明)
   4. 讀取狀態 (table: 階段 | UI 呈現)
   5. 錯誤碼 (table: 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式)
   6. 驗收標準 (checklist)
   ```
   Error code prefix = one short uppercase tag per feature (`AUTH_`, `DEVICE_`, `STREAM_`,
   `EVENT_`, `TIMELINE_`, `PUSH_`, `CLIP_`, `SCREENSHOT_`, `DRIVE_`, ...), numbered continuing
   from where that feature's own table left off. **Never re-declare another feature's code in a
   new file** — if feature B needs to reference an error condition owned by feature A (e.g. a
   shared password-strength check), write one line pointing at A's file + section instead of
   copying the table row. (This exact mistake happened once in this project: `AUTH_006` got
   fully redefined in a second file instead of referenced — caught during a duplicate-content
   audit.)

5. **Write screen specs** only for how something is laid out and navigated to/from, citing the
   functional spec(s) for everything else:
   ```
   metadata table (平台 | 對應功能規格書 | 所屬導覽層級)
   1. 畫面用途
   2. 版面配置
   3. 空狀態 (if the screen can be empty)
   4. 讀取狀態與錯誤碼 → "沿用 `<functional-spec>.md` 第 N、M 節,本文件不重複定義."
   ```
   **Split by platform into `screens/app/` and `screens/web/`**, same filename in both, one file
   per platform — don't write a single file with a "平台差異" comparison table the way this
   project did at first. App and Web have genuinely different navigation/layout conventions
   (bottom tab bar vs top nav; single-column tab-switching vs multi-column simultaneous panels
   on the wider desktop viewport; different session/logout UX), so give each platform its own
   complete description rather than one shared file annotated with exceptions. Every parent
   reference from a screen file up to a functional spec is one level deeper than before
   (`../../0X_spec_...`, not `../0X_spec_...`) because of the extra `app/`/`web/` folder level.

   **Web does use RWD — the platform-scope rule is about OS, not screen width.** Web is
   responsive across desktop/laptop/tablet window and screen sizes (breakpoints, adaptive nav,
   etc. all belong in a web spec). The one thing Web never does is serve a phone: detection is
   by **User-Agent OS** (iOS or Android phone → redirect), not by viewport width — a narrow
   desktop browser window or a tablet still gets the real Web UI with RWD applied, only an
   actual phone OS gets bounced. Don't conflate the two mechanisms in a spec: RWD handles "what
   does this look like at different desktop widths," the OS check handles "phones use the native
   App, period." A phone-OS browser hitting *any* Web route (including pre-login, see
   `01_page_登入註冊忘記密碼.md`) gets a single redirect screen to the App's store listing instead
   of the Web UI — this is a global, above-everything rule defined once in
   `screens/web/02_page_導覽與全域結構.md` §0, not repeated per screen. (This project got this
   wrong once mid-session — first specified "no mobile web at all," corrected to "RWD yes, phone
   OS redirect only" — so don't default to the stricter reading without checking which one this
   project actually means.)

   A screen backing a feature that has no dedicated screen of its own (e.g. a settings menu
   item that opens a sub-flow) doesn't need its own file — note it as an entry inside the page
   that hosts it, in *both* the app and web version of that page, and point the SDLC matrix's
   two 畫面規格 columns there with a parenthetical (see the `sdlc-matrix` skill).

6. **Naming/numbering**: two-digit prefix shared across every artifact for the same feature —
   functional spec `0X_spec_<name>.md`, its diagram `diagrams/0X_flow_<name>.drawio`, its row
   label in the PRD and SDLC matrix. Screen specs number independently within `screens/app/` and
   `screens/web/` (they don't need to share the feature's number since one screen can serve
   several features), but the **same number+name must exist in both platform folders** — a
   screen spec with an app/ version and no web/ counterpart (or vice versa) is a bug, not a
   deliberate omission. If you ever split one spec into several (this project split
   "帳號與裝置配對" into F0.1–F0.4), renumber every file that comes after the split point and
   grep the **whole tree** (both platform folders) for the old filename before calling it done —
   a stale cross-reference is the most common bug here, closely followed by "moved the whole
   `rule_doc/` tree into a subfolder and forgot the SDLC matrix's links needed the prefix" (also
   happened once in this project).

7. **After writing or editing anything**, run a cross-reference audit — don't skip this even
   for "just one small edit," since a single retention-day change or renumber tends to have 2–4
   downstream references:
   ```bash
   cd rule_doc/功能需求 && for f in *.md screens/app/*.md screens/web/*.md; do
     dir=$(dirname "$f")
     grep -oE '`[0-9]{2}_[^`]*\.(md|drawio)`' "$f" | tr -d '`' | while read -r t; do
       [ -f "$dir/$t" ] || [ -f "$t" ] || echo "BROKEN in $f: $t"
     done
   done
   ```
   Also confirm every `screens/app/0X_page_*.md` has a same-named `screens/web/0X_page_*.md`
   (and vice versa) — a platform with a missing counterpart won't show up as a broken link,
   only as a silent gap:
   ```bash
   diff <(ls screens/app | sort) <(ls screens/web | sort)
   ```
   Also grep for any duplicated error-code row across files (same `CODE_NNN` fully defined
   in two tables) and for lingering `待確認事項` / hedging language before reporting done.

## Feedback rules learned on this project (apply by default, don't wait to be told again)

- **No rationale prose in the spec body.** State the rule/decision as a flat sentence. A short
  "理由:" line is fine only when it's load-bearing for judging an edge case later (e.g. *why*
  device removal cascades to deleting events — because the device may be re-paired to a
  different user). Cut everything else.
- **No "待確認事項" sections left dangling.** Either make the call and state it as decided, or
  leave it out of the doc entirely — a shipped spec reads as settled, not as a running list of
  open questions.
- **Don't invent scope the user hasn't confirmed** (e.g. a specific mobile framework, a specific
  ML model) — write the behavior/interface generically and let engineering pick the
  implementation, rather than silently deciding for them.
- **A conflicting new requirement wins over an old NFR** — e.g. when "view up to a month of
  history" was requested after a "7-day video retention" NFR was already written, the fix was to
  update the retention number (and recheck the cost math still holds), not to hedge both
  numbers into the doc.
- **A one-sentence architectural correction usually encodes one specific, narrow fact — get that
  fact exactly right before writing anything, and expect it to have a wide blast radius once you
  do — and expect the fact itself to still need a follow-up refinement.** A terse message like
  "web不只有app,還有純web版" is easy to misread as several different things; asking one
  clarifying question beats guessing. This project's own history is the cautionary example: the
  first answer landed as "mobile = native app only, web = desktop-only, no responsive fallback at
  all" and got written into three files (PRD, web nav spec, pre-login screen) — then the very
  next message refined it again: Web *does* use RWD across desktop/tablet sizes, only an actual
  phone OS (not a narrow viewport) gets redirected. Every one of those three files needed a
  second pass. Don't stop at patching the file that was literally mentioned, and don't treat the
  first answer as final just because it resolved the ambiguity you asked about — a short
  correction can still be under-specified in a way that only surfaces on the next message.
- **A structural decision touches more documents than the one the user is looking at.** The
  microservice/dual-node ADR in this project needed the PRD, the architecture diagram, the SDLC
  matrix, and every downstream `interfaces/` file updated together, not just the ADR itself —
  and doing it revealed the ADR's own service list was incomplete (F3 had no owning service).
  When a request changes an architectural decision, re-open every doc whose content assumed the
  old decision, not only the doc named in the request.
