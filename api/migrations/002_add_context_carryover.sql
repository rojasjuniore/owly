-- Migration: Add Context Carryover support
-- Date: 2026-02-09
-- Description: Adds last_mentioned_lender column to conversations table
--              for context carryover feature (remembering lender across follow-up questions)
--
-- IMPORTANT: This field is ONLY used for PRODUCT_SEARCH follow-ups.
--            ELIGIBILITY_CHECK always searches ALL lenders (no filtering).

-- Add the column (nullable, no default needed)
ALTER TABLE conversations 
ADD COLUMN IF NOT EXISTS last_mentioned_lender VARCHAR(255) NULL;

-- Add comment for documentation
COMMENT ON COLUMN conversations.last_mentioned_lender IS 
'Context carryover: remembers last mentioned lender for follow-up questions. 
Only used in PRODUCT_SEARCH, NOT in ELIGIBILITY_CHECK.';
