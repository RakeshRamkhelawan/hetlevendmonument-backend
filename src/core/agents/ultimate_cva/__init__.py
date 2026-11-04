"""Ultimate CVA agent package.

Heavy symbols such as UltimateCVAAgent are intentionally NOT re-exported at
package level; import them directly from the submodules (e.g.
``from src.core.agents.ultimate_cva.agent import UltimateCVAAgent``). This
keeps imports of lightweight utilities like ``system_prompt`` fast and avoids
paying the agent instantiation cost during router module load.
"""

__all__ = []
