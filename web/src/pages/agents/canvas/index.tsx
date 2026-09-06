import React, { useCallback, useRef } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  
  useReactFlow,
} from '@xyflow/react';
import type { Connection, Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { NodePalette } from './palette';
import { customNodeTypes } from './custom-nodes';
import { ConfigDrawer } from './config-drawer';

let id = 0;
const getId = () => `dndnode_${id++}`;

const CanvasArea = () => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { screenToFlowPosition } = useReactFlow();

  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      if (typeof type === 'undefined' || !type) {
        return;
      }

      // Project the screen coordinates to the React Flow instance's coordinate system
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      
      const newNode = {
        id: getId(),
        type,
        position,
        data: { label: `${type} node` },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, setNodes]
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      // Prevent self connections
      if (connection.source === connection.target) {
        return false;
      }
      return true;
    },
    []
  );

  return (
    <div className="flex-1 h-full w-full relative" ref={reactFlowWrapper}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        isValidConnection={isValidConnection}
        onDragOver={onDragOver}
        nodeTypes={customNodeTypes}
        fitView
      >
        <Controls />
        <Background gap={16} size={1} />
      </ReactFlow>
    </div>
  );
};

export const CanvasPage = () => {
  return (
    <div className="flex h-full w-full bg-white rounded-lg border shadow-sm overflow-hidden">
      <ReactFlowProvider>
        <NodePalette />
        <CanvasArea />
        <ConfigDrawer />
      </ReactFlowProvider>
    </div>
  );
};
