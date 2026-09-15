# Pika-RAG: /team Button UI — Design

Status: Approved
Date: 2026-09-15

## Purpose

The eventual goal (tracked as an open backlog item since the 2026-09-13
brainstorm) is replacing this bot's slash-command interactions with
Discord's native button/component UI, in the style of Pokétwo's
Pokémon-browsing panels. That's a large surface — 10 existing commands
(`/ping`, `/ask`, `/stats`, `/moves`, `/calc`, `/import`, `/scout`,
`/team`, `/debug-last`, `/llmstatus`) — and this bot has no
`discord.ui` usage anywhere today, so committing to a pattern across
all of them before validating it on one command risks designing 9 UIs
against an approach that turns out to need revision after real use.

This spec is **Phase 1**: validate the button/View pattern on a single,
low-risk slice of one command, `/team`. Once it ships and the pattern
holds up, each remaining command gets its own short follow-up
brainstorm (applying the now-proven recipe) rather than a large
upfront redesign here. Full-command migration is explicitly out of
scope for this spec — see "Out of scope."

## Scope

In scope:
- `/team` gains two buttons — "Your team" / "Opponent's team" —
  replacing its current `side: Literal["mine", "opponent"]` slash
  command parameter. Clicking a button re-renders the same message in
  place with the other side's team.
- The interaction is restricted to whoever ran `/team` originally.
- No persistence across bot restarts; the view uses discord.py's
  default timeout, after which Discord greys the buttons out.

Out of scope (see "Out of scope" section for detail):
- Per-slot pagination (browsing team members one at a time).
- Editing a team slot via buttons/modals (still `/scout`/`/import`).
- Any other command's button UI — `/ask`, `/stats`, `/moves`, `/calc`,
  `/import`, `/scout`, `/debug-last`, `/llmstatus`, `/ping` are
  untouched by this spec.
- Persistent views (surviving a bot restart via registered `custom_id`s).

## Architecture

A new `TeamView(discord.ui.View)` class in `bot/commands/team.py`,
alongside the file's existing pure functions
(`format_team_block`, `view_team_response`, etc. — unchanged). It is
constructed with `user_id` and the currently-displayed `side`, and
holds two `discord.ui.Button`s. Each button's callback:

1. Reads the *other* side's team via the existing, unchanged
   `view_team_response(user_id, other_side)`.
2. Calls `interaction.response.edit_message(embed=..., view=<a new
   TeamView reflecting the new side>)` — editing the message in place
   rather than sending a new one.

`bot/main.py`'s `/team` command handler changes from taking a `side`
slash-command parameter to always starting on `"mine"`, sending its
initial embed with `view=TeamView(interaction.user.id, "mine")`
attached. `view_team_response`, `format_team_block`, and the
`_embed("team", ...)` helper are all reused unchanged — this task adds
only the View/button wiring on top of logic that already exists and is
already tested.

## Interaction model

- **Invoker-only:** `TeamView.interaction_check(interaction)` checks
  `interaction.user.id == self.user_id`. Unlike `app_commands.check`
  (used by `/debug-last`/`/llmstatus`'s owner gate, which raises
  `CheckFailure` into `bot/main.py`'s existing `@tree.error` handler),
  a `discord.ui.View`'s `interaction_check` is a *different* mechanism
  that does not route through that handler — if it simply returns
  `False`, discord.py silently no-ops the click with no feedback to
  the user, which reads as a broken button. `interaction_check` must
  therefore send its own ephemeral rejection before returning `False`:
  `await interaction.response.send_message("This isn't your team
  view.", ephemeral=True)`, then `return False`. This mirrors the
  wording/tone of the existing owner-only rejection message in
  `bot/main.py`'s `@tree.error` handler without reusing its code path
  (the two systems don't share one).
- **Edit in place:** every button click calls
  `interaction.response.edit_message(...)`, never sends a new message
  — this is the entire reason to use a View instead of a fresh command
  invocation.
- **No persistence:** the view relies on discord.py's default
  (non-`custom_id`) timeout (~15 minutes of inactivity). After it
  times out, Discord automatically disables the buttons on the last
  rendered message. No explicit `on_timeout` handling is added for
  this pilot — greyed-out buttons are an acceptable end state, and a
  user can just re-run `/team` for a fresh view.

## Error handling

`view_team_response` already returns a plain "No team loaded" message
when the side has nothing stored — a button click on an empty side
just re-renders that same message via the existing function,
unchanged. The one new error path is the invoker-only rejection
described above, which `interaction_check` handles directly (its own
ephemeral send) rather than through the bot's existing
`@tree.error`/`CheckFailure` handler, since `discord.ui.View` checks
don't route through that system.

## Testing plan

- `TeamView`'s two button callbacks: construct the view directly,
  build a `MagicMock` interaction with a given `user.id`, call the
  button's callback coroutine via `asyncio.run(...)`, and assert on
  `interaction.response.edit_message`'s captured `embed`/`view`
  kwargs — mirrors the existing pattern already used for command
  callbacks in `tests/test_bot_main.py` (e.g. its `_extract_text`
  helper reading a captured `embed.description`).
- `interaction_check`: a `MagicMock` interaction with a `user.id`
  different from the view's `user_id` returns `False` AND triggers an
  ephemeral `interaction.response.send_message`; the matching
  `user_id` returns `True` and sends nothing.
- `/team`'s command registration: `build_client()`'s `/team` command
  still exists and its callback attaches a `TeamView` to the initial
  response (no `side` parameter anymore — a registration-level test
  confirming the parameter was removed, mirroring existing
  command-registration tests in `tests/test_bot_main.py`).
- No test needs real Discord network access — everything above uses
  fakes/mocks, consistent with every other test in this codebase.

## Out of scope

- **Per-slot pagination and edit-in-place modals** — deliberately
  deferred to a later phase once the side-switcher pattern (View
  construction, invoker-only checks, edit-in-place re-rendering) is
  proven in production. Building pagination or a `discord.ui.Modal`
  edit flow now would mean debugging two new patterns at once instead
  of one.
- **Migrating any other command to buttons** — `/ask`, `/stats`,
  `/moves`, `/calc`, `/import`, `/scout`, `/debug-last`, `/llmstatus`,
  and `/ping` are all untouched. Each gets its own short brainstorm
  once this phase ships, reusing the `TeamView` pattern (a View class
  per command, invoker-only `interaction_check`, edit-in-place
  callbacks) rather than a fresh design each time.
- **Persistent views surviving a bot restart** — would require
  registering `custom_id`-keyed views on startup and reconstructing
  their state (which side, which user) from the `custom_id` itself
  rather than from in-memory Python objects. Not needed for a
  15-minute-lifetime side-switcher; revisit if a future phase needs a
  view that must survive a bot restart (e.g. a long-lived dashboard
  message).
