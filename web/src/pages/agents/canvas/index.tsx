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

import { useGetCanvas, useSaveCanvas } from '../../../hooks/use-agent-request';
import { Save, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';


let id = 0;
const getId = () => `dndnode_${id++}`;

const CanvasArea = () => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { screenToFlowPosition, getNodes, getEdges } = useReactFlow();

  const CANVAS_ID = 'default-canvas'; // Hardcoded for now per requirements

  const { data: canvasData, isLoading: isLoadingCanvas } = useGetCanvas(CANVAS_ID);
  const saveMutation = useSaveCanvas();
  const [saveStatus, setSaveStatus] = React.useState<'idle' | 'saving' | 'success' | 'error'>('idle');

  // Load existing graph
  React.useEffect(() => {
    if (canvasData?.graph) {
      setNodes(canvasData.graph.nodes || []);
      setEdges(canvasData.graph.edges || []);
      
      // Update our ID counter based on existing nodes so new nodes don't collide
      let maxId = 0;
      (canvasData.graph.nodes || []).forEach(n => {
        if (n.id.startsWith('dndnode_')) {
          const num = parseInt(n.id.split('_')[1]);
          if (!isNaN(num) && num >= maxId) {
            maxId = num + 1;
          }
        }
      });
      id = maxId;
    }
  }, [canvasData, setNodes, setEdges]);

  const handleSave = async () => {
    setSaveStatus('saving');
    try {
      await saveMutation.mutateAsync({
        id: CANVAS_ID,
        graph: {
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
        }
      });
      setSaveStatus('success');
      setTimeout(() => setSaveStatus('idle'), 3000);
    } catch (e) {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 5000);
    }
  };

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

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      
      const newNode = {
        id: getId(),
        type,
        position,
        data: { label: `${type} node`, config: {} },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, setNodes]
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      if (connection.source === connection.target) {
        return false;
      }
      return true;
    },
    []
  );

  if (isLoadingCanvas) {
    return (
      <div className="flex-1 h-full w-full flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center text-gray-500">
          <Loader2 className="w-8 h-8 animate-spin mb-2" />
          <p>Loading Agent Canvas...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full w-full relative" ref={reactFlowWrapper}>
      {/* Floating Toolbar */}
      <div className="absolute top-4 right-4 z-10">
        <button
          onClick={handleSave}
          disabled={saveStatus === 'saving'}
          className={`flex items-center px-4 py-2 rounded-md shadow-sm text-sm font-medium text-white transition-colors
            ${saveStatus === 'error' ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'}`}
        >
          {saveStatus === 'saving' && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
          {saveStatus === 'success' && <CheckCircle2 className="w-4 h-4 mr-2" />}
          {saveStatus === 'error' && <AlertCircle className="w-4 h-4 mr-2" />}
          {saveStatus === 'idle' && <Save className="w-4 h-4 mr-2" />}
          
          {saveStatus === 'saving' ? 'Saving...' :
           saveStatus === 'success' ? 'Saved' :
           saveStatus === 'error' ? 'Save Failed' : 'Save Workflow'}
        </button>
      </div>

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
};export const CanvasPage = () => {
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
