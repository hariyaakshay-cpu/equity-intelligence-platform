"""Scoring abstraction layer -- interfaces only, no scoring logic.

No function or class in this subpackage implements the B2 band tables,
computes a composite value, or applies the candidate cutoff. Every
concrete method is a placeholder that raises NotImplementedError with a
message naming the blocking governance gate, per the implementation
task's own guidance: "A placeholder is preferable to silently
implementing the proposal."
"""
