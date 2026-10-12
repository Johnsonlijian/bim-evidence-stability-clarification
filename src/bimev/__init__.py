"""bimev: interpretation-robust evidence reasoning and evidence acquisition for BIM rule checks.

Modules
-------
ifcutil   IFC access helpers (units, typed property values, geometry extents, name parsing)
catalog   declared rulebooks, interpretation catalogue and action costs
extract   per-family evidence extraction into a JSON evidence ledger
engine    version-space reasoning (interpretations, fault modes, minimum-cardinality diagnosis),
          verdict sets and conclusion stability
planner   acquisition policies, simulated test outcomes, hindsight reference and metrics
"""

__version__ = "0.9.0"
