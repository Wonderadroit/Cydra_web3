# Post-fix replay objective

This branch replays the same pinned Immunefi Vaults Splitter revision after the generic payable-state and helper-mediated-write modeling change.

Expected measurement:
- Confirm the model now surfaces feeRecipient as mutable state and propagates the _changeFeeRecipient write to changeFeeRecipient.
- Do not expect an authorization hypothesis merely because a state write exists: the exposed setter is protected by onlyOwner.
- Preserve the result as NOT_SELECTED / BLOCKED if no authorization candidate is selected. This is not a finding and does not prove the target secure.
