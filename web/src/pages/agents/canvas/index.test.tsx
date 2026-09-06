import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { CanvasPage } from './index';

// Mock ResizeObserver for React Flow
global.ResizeObserver = class ResizeObserver {
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
