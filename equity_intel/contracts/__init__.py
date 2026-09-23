"""Neutral data contracts for the Equity Intelligence pipeline.

Every contract in this subpackage describes SHAPE only. No contract in this
subpackage assigns a default numeric score, cutoff, or vendor-specific value.
Where a governing document (B2 spec, decision freeze) already makes a name
or vocabulary authoritative, that name may appear as a field name or a
frozen enum; where it remains a proposal, the contract keeps the field
open-ended (Optional, free-form string, or an injected configuration value).
"""
