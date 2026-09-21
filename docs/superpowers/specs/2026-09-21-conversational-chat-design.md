# Conversational chat in designated channels — design

Source: user request — move away from slash-command-only interaction and
let people talk to the bot in plain messages, without giving up the
existing slash commands as the precise/fast path.

## Purpose

Today every bot capability requires a slash command. This design adds a
second, conversational entry point: in specific admin-designated Discord
channels, any plain message is treated as directed at the bot and answered
via the same reasoning/tool-calling the bot already has (`/analyze`'s
loop), with a short rolling memory so natural follow-ups work ("what about
its speed?" after asking about a Pokemon).

## Constraints established during brainstorming

- **Coexist with slash commands, don't replace them.** `/calc`, `/stats`,
  `/ask`, `/analyze`, `/team`, etc. are untouched and keep working
  everywhere. Conversational mode is additive, in opt-in channels only.
- **Trigger: every message in designated channels**, not @mention/reply/DM.
  Configured via a new `CONVERSATION_CHANNEL_IDS` env var (comma-separated
  Discord channel IDs) — feature is entirely off if unset, same pattern as
  `BOT_OWNER_ID`-gated commands.
- **Reuse `/analyze`'s existing tool-calling loop**
  (`bot/agentic.py:analyze_response_async`, `OllamaAnswerer.answer_with_tools`)
  rather than building a separate pipeline — it already does tool-calling
  (damage calc, stored team, usage stats) with fallback to a plain grounded
  RAG answer when no tool applies. No new tools added in this design.
- **Short rolling history, per channel, in-memory only.** Not persisted —
  a bot restart clears context, which is acceptable for chat-style
  back-and-forth. Explicitly chosen over per-user or per-thread history:
  simplest to implement, matches the "every message in the channel"
  trigger choice. **Known limitation, accepted:** if multiple people talk
  to the bot in the same designated channel at once, they share one
  history — the bot can get confused about whose question a follow-up
  belongs to. Not solved here; revisit with per-thread history
  (auto-created threads) if this proves to be a real problem in practice.
- **Hard prerequisite: Discord's privileged "Message Content Intent"** must
  be enabled for this bot in the Discord Developer Portal (Bot →
  Privileged Gateway Intents). Without it, `on_message` never receives
  message text content regardless of code changes. This is a manual,
  one-time step only the bot owner can do — call out explicitly in the
  implementation plan as a blocking prerequisite, not an afterthought.

## Architecture

### `discord.Intents` change (`bot/main.py`)

`intents = discord.Intents.default()` gains `intents.message_content =
True`. This is the only intents change; no other privileged intents
needed.

### New module — `bot/conversation.py`

- `ConversationHistory`: a small in-memory class wrapping
  `dict[int, deque[dict]]` (channel ID → capped deque of past `{role,
  content}` turns). `append(channel_id, role, content)` pushes and trims
  to a cap (proposed: last 3 exchanges = 6 messages, tunable constant);
  `get(channel_id) -> list[dict]` returns the current buffer for that
  channel, empty list if none yet. Pure, easily unit-testable — no Discord
  types in this module at all.
- `should_respond(message, conversation_channel_ids) -> bool`: `True` only
  if the message's channel ID is in the configured set AND the author
  isn't a bot (covers both this bot's own messages and any other bot in
  the channel) — prevents response loops.

### `OllamaAnswerer.answer_with_tools` (`rag/answer.py`)

Gains an optional `history: Optional[list[dict]] = None` parameter.
When provided, its turns are inserted into the `messages` list after the
system prompt and before the new user question (same shape as the
existing `messages` list already uses: `{"role": ..., "content": ...}`).
Defaults to `None` (current behavior, current tests, and `/analyze`'s
slash-command call site) — fully backward-compatible, no existing caller
changes.

### `analyze_response_async` (`bot/agentic.py`)

Gains a matching optional `history` parameter, threaded straight through
to `answer_with_tools`. `/analyze`'s slash-command handler continues to
call it with no `history` argument (stateless, as today).

### `bot/main.py` — new `on_message` listener

```python
@client.event
async def on_message(message: discord.Message) -> None:
    if not should_respond(message, conversation_channel_ids):
        return
    if conversation_lock.get(message.channel.id):
        return  # one response in flight per channel, see below
    conversation_lock[message.channel.id] = True
    try:
        async with message.channel.typing():
            history = conversation_history.get(message.channel.id)
            answer = await analyze_response_async(
                raw_answerer, message.content, records, moves, items, usage,
                message.author.id, index=index, bm25_index=bm25_index,
                history=history,
            )
        await message.reply(answer)
        if answer not in (OFFLINE_MESSAGE, MALFORMED_TOOL_CALL_MESSAGE):
            conversation_history.append(message.channel.id, "user", message.content)
            conversation_history.append(message.channel.id, "assistant", answer)
    finally:
        conversation_lock[message.channel.id] = False
```

`conversation_channel_ids` is parsed once at startup from
`CONVERSATION_CHANNEL_IDS` (empty set if unset — `should_respond` then
always returns `False`, so the listener is a no-op and costs nothing on
unrelated deployments/tests). `conversation_history` is one
`ConversationHistory` instance built in `main()`/`build_client()` the same
way `bm25_index`/`index` already are.

### Concurrency guard

No Discord-enforced ack window applies to plain messages (unlike slash
commands' 3-second interaction deadline), but a chatty channel could still
stack multiple concurrent 90-second LLM calls. A simple per-channel
in-flight flag (`conversation_lock: dict[int, bool]`) drops (silently
ignores, no error reply) any message that arrives in a channel while a
response to an earlier message in that same channel is still being
generated. This is a blunt instrument — acceptable for a first version,
revisit with a real queue if it feels too aggressive in practice.

### Reply style

Plain `message.reply(answer)` — no embed. Conversational back-and-forth
should read like a chat message, not a command result card; embeds are
reserved for slash commands, which stay unchanged. Not ephemeral (this is
public channel conversation, and ephemeral doesn't apply to non-interaction
messages anyway), and not `interaction.followup.send()` since there's no
interaction object for a plain message.

## Data flow

1. Message arrives in a designated channel, author isn't a bot.
2. If a response is already in flight for this channel, silently drop.
3. Show the channel's typing indicator (responses may take up to the
   configured `LLM_TIMEOUT`, currently 90s).
4. Look up this channel's rolling history (empty on first message).
5. Call the extended `analyze_response_async` with history + the new
   message content, same tool-calling-with-RAG-fallback path `/analyze`
   already uses.
6. Reply to the triggering message with the answer.
7. On a real (non-degraded, non-malformed-tool-call) answer, append the
   question+answer pair to that channel's history, trimmed to the cap. A
   degraded (`OFFLINE_MESSAGE`) or malformed-tool-call answer is *not*
   appended, keeping history clean of non-substantive turns.

## Error handling

- **Author is a bot (including this bot itself):** ignored before any
  other check — the one hard requirement to avoid response loops.
- **LLM offline/timeout:** `answer_with_tools` already returns
  `OFFLINE_MESSAGE` rather than raising (existing behavior, unchanged);
  the listener replies with it but doesn't pollute history with it.
- **Malformed/hallucinated tool call:** `analyze_response_async` already
  falls back to a plain RAG answer (existing behavior); only if *that*
  somehow also fails does `MALFORMED_TOOL_CALL_MESSAGE` itself surface,
  same edge case `/analyze` already has.
- **Concurrent messages in one channel:** dropped silently per the
  concurrency guard above, not queued or erred.
- **An exception inside the listener itself** (a bug, not a normal
  degradation path): let it propagate to discord.py's default
  `on_error` handler (logs to stderr/journal) rather than adding new
  bespoke handling — matches how unhandled errors are already surfaced
  elsewhere in this codebase (`print(...)` + default framework behavior),
  not a new pattern.

## Testing

- `ConversationHistory`: unit tests for append/trim/cap, per-channel
  isolation (channel A's history never leaks into channel B's), empty
  buffer for an unseen channel.
- `should_respond`: unit tests for the designated-channel allowlist check
  and the bot-author exclusion, including the empty-allowlist (feature
  off) case.
- `answer_with_tools`'s new `history` param: a test confirming history
  turns land in the right position in the constructed `messages` list,
  and a test confirming omitting `history` reproduces today's exact
  behavior (regression guard for `/analyze`'s existing tests).
- Handler-level test for `on_message`, mocking `discord.Message` the way
  existing tests mock `discord.Interaction`: confirms ignore-non-designated-channel,
  ignore-bot-author, typing-indicator-used, reply-sent, history-updated on
  success, history-NOT-updated on `OFFLINE_MESSAGE`, and the
  one-in-flight-per-channel drop behavior.

## Out of scope

- Per-thread or per-user history (see the accepted shared-history
  limitation above) — revisit only if real usage shows it's actually a
  problem.
- Persisting conversation history across a bot restart.
- Any new tools beyond the three `/analyze` already has.
- Rate-limiting beyond the one-in-flight-per-channel guard (e.g. a
  per-user cooldown) — revisit if abuse becomes a real concern.
- Changing `/analyze`'s or `/ask`'s own behavior in any way.
