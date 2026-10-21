import { layoutGraph } from './diagram_layout.js'
self.onmessage = event => {
  try { self.postMessage({ identity: event.data.identity, layout: layoutGraph(event.data.graph) }) }
  catch { self.postMessage({ identity: event.data.identity, error: 'layout_failed' }) }
}
