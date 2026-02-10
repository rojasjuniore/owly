# Context Carryover Feature

## Overview

Context Carryover allows the system to remember the last mentioned lender across follow-up questions, providing a more natural conversation flow.

## How It Works

1. When a user mentions a specific lender (e.g., "Tell me about Angel Oak"), the system stores it in `conversation.last_mentioned_lender`
2. For follow-up questions that reference "their" or "their programs", the system uses this stored lender
3. **CRITICAL**: Eligibility checks (e.g., "What are Conventional requirements?") NEVER use this filter

## Intent Routing

| Intent | Uses Lender Filter? | Reason |
|--------|---------------------|--------|
| PRODUCT_SEARCH | ✅ Yes | Follow-ups about a specific lender's products |
| GENERAL_QUESTION | ❌ No | System-wide questions don't need lender context |
| ELIGIBILITY_CHECK | ❌ **Never** | Must search ALL lenders for complete answers |
| SCENARIO_INPUT | ❌ No | Full analysis across all lenders |

## The Bug (Commit 36f7034)

The original implementation applied the lender filter to ALL intent types, including ELIGIBILITY_CHECK. This caused:

1. User asks about "Angel Oak" → `last_mentioned_lender = "Angel Oak"`
2. User asks "What are Conventional requirements?"
3. System only searched Angel Oak's rules/chunks
4. Result: Empty or incomplete answers for generic product questions

## The Fix

```python
# In chat_service.py

elif intent == IntentType.ELIGIBILITY_CHECK:
    # CRITICAL: DO NOT apply lender filter for eligibility checks!
    # This was the bug - filtering caused empty results.
    result = await self.general_qa.answer_eligibility_check(message, entities)
```

The `answer_eligibility_check` method in `GeneralQAService` intentionally does NOT accept a `lender_filter` parameter, ensuring all lenders are always searched.

## Testing

Unit tests in `tests/test_eligibility_flow.py` verify:

1. Eligibility checks search ALL lenders (no filtering)
2. Generic product questions (Conventional, VA, FHA) work correctly
3. Context carryover doesn't break eligibility queries

## Database

New column added to `conversations` table:

```sql
ALTER TABLE conversations 
ADD COLUMN last_mentioned_lender VARCHAR(255) NULL;
```

## Resetting Context

The `last_mentioned_lender` is:
- Set when a lender is explicitly mentioned
- Overwritten when a new lender is mentioned
- Reset when creating a new conversation

It does NOT need explicit reset logic because new conversations start with NULL.
