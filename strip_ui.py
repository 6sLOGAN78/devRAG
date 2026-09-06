import re

with open("web/src/pages/agents/canvas/index.tsx", "r") as f:
    content = f.read()

clean_nodes_code = """
        nodes: getNodes().map(n => ({
          id: n.id,
          type: n.type,
          position: n.position,
          data: n.data
        })),
        edges: getEdges().map(e => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle
        })),
"""

content = content.replace(
    "nodes: getNodes(),\n          edges: getEdges(),",
    clean_nodes_code.strip()
)

with open("web/src/pages/agents/canvas/index.tsx", "w") as f:
    f.write(content)
