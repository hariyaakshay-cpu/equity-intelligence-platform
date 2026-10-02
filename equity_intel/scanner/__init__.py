"""Non-functional scanner orchestration shell.

No module in this subpackage implements a business decision. Every stage
either performs a purely structural action (declaring the pipeline's
order) or raises NotImplementedError naming the governance gate it is
blocked by. No fake candidate list and no fake watchlist is ever produced.
"""
