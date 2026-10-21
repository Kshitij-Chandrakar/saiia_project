import dagre from '@dagrejs/dagre'
import { lines } from './diagram_labels.js'

export function layoutGraph(data) {
  if (!data || data.nodes?.length > 20 || data.edges?.length > 32 || data.nodes?.length < 2) throw Error('invalid_graph')
  const graph = new dagre.graphlib.Graph().setGraph({ rankdir: 'TB', ranksep: 85, nodesep: 35, marginx: 24, marginy: 24 }).setDefaultEdgeLabel(() => ({}))
  const padding = { client: 76, service: 36, database: 56, storage: 56, queue: 44, cache: 52, external: 68 }
  for (const node of data.nodes) graph.setNode(node.id, { width: 190, height: (padding[node.kind] || 36) + lines(node.label).length * 18 })
  for (const edge of data.edges) graph.setEdge(edge.source, edge.target, { width: 150, height: lines(edge.label).length * 18 })
  dagre.layout(graph)
  const { width, height } = graph.graph()
  if (!Number.isFinite(width) || !Number.isFinite(height) || width > 10000 || height > 20000) throw Error('layout_failed')
  return { width, height,
    nodes: data.nodes.map(node => ({ ...node, ...graph.node(node.id) })),
    edges: data.edges.map(edge => ({ ...edge, ...graph.edge(edge.source, edge.target) })) }
}
