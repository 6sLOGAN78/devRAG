import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MessageInput } from './index';

describe('MessageInput', () => {
  it('renders correctly', () => {
    render(<MessageInput onSend={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('calls onSend when send button is clicked', () => {
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole('textbox');
    const sendButton = screen.getByLabelText('Send message');
    
    fireEvent.change(input, { target: { value: 'Hello' } });
    fireEvent.click(sendButton);
    
    expect(onSend).toHaveBeenCalledWith('Hello');
  });

  it('calls onSend on Enter key', () => {
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole('textbox');
    
    fireEvent.change(input, { target: { value: 'Hello world' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false });
    
    expect(onSend).toHaveBeenCalledWith('Hello world');
  });

  it('does not send on Shift+Enter', () => {
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole('textbox');
    
    fireEvent.change(input, { target: { value: 'Hello' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    
    expect(onSend).not.toHaveBeenCalled();
  });

  it('prevents empty messages', () => {
    const onSend = vi.fn();
    render(<MessageInput onSend={onSend} onCancel={vi.fn()} />);
    const input = screen.getByRole('textbox');
    const sendButton = screen.getByLabelText('Send message');
    
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.click(sendButton);
    
    expect(onSend).not.toHaveBeenCalled();
    expect(sendButton).toBeDisabled();
  });
  
  it('shows cancel button during streaming', () => {
    const onCancel = vi.fn();
    render(<MessageInput onSend={vi.fn()} onCancel={onCancel} isStreaming={true} />);
    
    const cancelButton = screen.getByLabelText('Cancel generating');
    expect(cancelButton).toBeInTheDocument();
    
    fireEvent.click(cancelButton);
    expect(onCancel).toHaveBeenCalled();
  });
});
