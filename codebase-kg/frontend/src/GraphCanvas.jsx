import { useEffect, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

const COLUMN_WIDTH = 340;
const ROW_HEIGHT = 96;

/**
 * Assign each file a column based on how deep it sits in the import graph.
 * Files that import nothing start at column 0.
 */
function computeColumns(nodes, edges) {
  const importers = new Map();
  nodes.forEach((node) => importers.set(node.id, []));
  edges.forEach((edge) => importers.get(edge.target)?.push(edge.source));

  const depths = new Map();
  const visiting = new Set();

  const depthOf = (id) => {
    if (depths.has(id)) return depths.get(id);
    if (visiting.has(id)) return 0; // break cycles
    visiting.add(id);
    let depth = 0;
    for (const importer of importers.get(id) ?? []) {
      depth = Math.max(depth, depthOf(importer) + 1);
    }
    visiting.delete(id);
    depths.set(id, depth);
    return depth;
  };

  nodes.forEach((node) => depthOf(node.id));
  return depths;
}

function buildLayout(apiNodes, apiEdges) {
  const depths = computeColumns(apiNodes, apiEdges);
  const byColumn = new Map();

  [...apiNodes]
    .sort((a, b) => a.path.localeCompare(b.path))
    .forEach((node) => {
      const column = depths.get(node.id) ?? 0;
      if (!byColumn.has(column)) byColumn.set(column, []);
      byColumn.get(column).push(node);
    });

  const tallest = Math.max(1, ...[...byColumn.values()].map((c) => c.length));
  const positions = new Map();

  byColumn.forEach((columnNodes, column) => {
    const offset = ((tallest - columnNodes.length) * ROW_HEIGHT) / 2;
    columnNodes.forEach((node, index) => {
      positions.set(node.id, {
        x: column * COLUMN_WIDTH,
        y: offset + index * ROW_HEIGHT,
      });
    });
  });

  return positions;
}

function Flow({ apiNodes, apiEdges, selectedNodeId, onSelectNode }) {
  const { setCenter } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const layout = useMemo(() => {
    const positions = buildLayout(apiNodes, apiEdges);
    const filenameCount = new Map();
    apiNodes.forEach((n) => {
      filenameCount.set(n.label, (filenameCount.get(n.label) ?? 0) + 1);
    });

    const flowNodes = apiNodes.map((node) => {
      const isSelected = node.id === selectedNodeId;
      return {
        id: String(node.id),
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        data: { label: node.label, path: node.path },
        style: {
          background: "#252526",
          color: "#e0e0e0",
          border: `2px solid ${isSelected ? "#1e90ff" : node.color || "#3c3c3c"}`,
          borderRadius: 8,
          padding: "8px 14px",
          fontSize: 12,
          width: 190,
          boxShadow: isSelected ? "0 0 0 4px rgba(30,144,255,0.25)" : "none",
        },
      };
    });

    const flowEdges = apiEdges.map((edge, index) => ({
      id: `${edge.source}-${edge.target}-${index}`,
      source: String(edge.source),
      target: String(edge.target),
      markerEnd: { type: MarkerType.ArrowClosed, color: "#5a5a5a" },
      style: { stroke: "#5a5a5a", strokeWidth: 1.5 },
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [apiNodes, apiEdges, selectedNodeId]);

  useEffect(() => {
    setNodes(layout.nodes);
    setEdges(layout.edges);
  }, [layout, setNodes, setEdges]);

  // Pan to the selected node when it changes.
  useEffect(() => {
    if (!selectedNodeId) return;
    const node = nodes.find((n) => n.id === String(selectedNodeId));
    if (!node) return;
    setCenter(node.position.x + 95, node.position.y + 20, {
      zoom: 1.2,
      duration: 500,
    });
  }, [selectedNodeId, nodes, setCenter]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      minZoom={0.15}
      onNodeClick={(_, node) => onSelectNode(Number(node.id))}
      onPaneClick={() => onSelectNode(null)}
      nodesDraggable
      proOptions={{ hideAttribution: false }}
    >
      <Background color="#2a2a2a" gap={20} />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        nodeColor={(node) => node.style?.border?.split(" ").pop() || "#787878"}
        maskColor="rgba(13,13,13,0.7)"
      />
    </ReactFlow>
  );
}

export default function GraphCanvas({ apiNodes, ...rest }) {
  if (!apiNodes.length) {
    return (
      <div className="graph-empty">
        No files were found in this project. Check the path and rescan.
      </div>
    );
  }

  return (
    <div className="graph-canvas">
      <ReactFlowProvider>
        <Flow apiNodes={apiNodes} {...rest} />
      </ReactFlowProvider>
    </div>
  );
}