import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CanvasPage } from './index';

// Mock ResizeObserver for React Flow
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

describe('CanvasPage', () => {
  it('renders palette and canvas area', () => {
    render(<CanvasPage />);
    expect(screen.getByText('Node Palette')).toBeInTheDocument();
    
    // Check if the node types are in the palette
    expect(screen.getByText('LLM Node')).toBeInTheDocument();
    expect(screen.getByText('Retrieval Node')).toBeInTheDocument();
    expect(screen.getByText('Code Node')).toBeInTheDocument();
    expect(screen.getByText('Switch Node')).toBeInTheDocument();
  });
});
