# Reasoning/Content Separation Fix

## Problem
When the model puts everything in `reasoning_content` and leaves `content` empty (None), the UI shows no clear separation between reasoning and the actual response. Two issues:
1. At refresh: `effective = content or reasoning or ""` dumps reasoning text into a chat bubble as if it were a regular response — no visual distinction.
2. At streaming end: the fallback creates a content bubble from reasoning, duplicating text when `show_reasoning` is ON.
3. Save fallback (`content = total_reasoning`) corrupts the content/reasoning distinction in the DB.

## Root Cause
Models often emit reasoning + tool calls without a separate `content` field. The current code tries to "fix" this by promoting reasoning to content, which destroys the semantic distinction and leads to duplicate/confusing display.

## Solution

### Principle
- `content` and `reasoning_content` are semantically different fields.
- NEVER promote `reasoning_content` to `content` at save time — preserve the raw model output.
- At display time, use fallback only when necessary (show_reasoning OFF → reasoning would be hidden).

### Changes

#### 1. `_process_response()` — Save logic
Remove fallback: save `content = total_response or None` (not `total_reasoning`).
Remove streaming-end bubble creation when `show_reasoning` is ON (reasoning card already visible).

#### 2. `_process_response()` — Streaming end fallback
Only create a content bubble from reasoning when `show_reasoning` is OFF (reasoning cards were deleted, message would be invisible).

#### 3. `refresh_chat_display()` — Display logic
- Content bubble only when `content` exists.
- If only `reasoning` exists and `show_reasoning` is OFF, show reasoning in content bubble as fallback.
- Reasoning card only when `show_reasoning` is ON and `reasoning` exists.
- Separator only between genuine content bubble and reasoning card.

### Cases covered

| Scenario | show_reasoning | content | reasoning | Display |
|----------|---------------|---------|-----------|---------|
| A | ON | exists | exists | content bubble → separator → reasoning card |
| B | ON | empty | exists | reasoning card only (no duplicate bubble) |
| C | OFF | exists | exists | content bubble only |
| D | OFF | empty | exists | content bubble with reasoning text (fallback) |
| E | any | exists | empty | content bubble only |
