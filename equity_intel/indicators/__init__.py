"""Pure, side-effect-free technical-analysis math.

Every function in this subpackage is standard, general-purpose technical
analysis: it takes a period/window as a REQUIRED argument (no default that
would silently reproduce a B2-proposed period such as 20/50/200/14/10/60)
and returns raw numeric output. No function here applies a scoring band,
a classification trigger, a candidate cutoff, or any other B2 decision.

None of these functions perform I/O, call a broker, touch the OMS, or
import anything from core.paper_engine / core.continuous_engine /
core.execution_engine / core.oms.* / core.risk_manager / brokers.* /
strategies.* / main / core.historical_data.
"""
