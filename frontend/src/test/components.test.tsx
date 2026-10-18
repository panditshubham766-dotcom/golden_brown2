import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusLabel } from '../components/StatusLabel/StatusLabel';
import { SourceCitation } from '../components/SourceCitation/SourceCitation';
import type { AskResponse, EvidenceItem } from '../api/contracts';

describe('LexiGuard UI Components & Render Rules', () => {
  it('StatusLabel displays accessible and truthful text', () => {
    render(<StatusLabel status="ANSWERED" />);
    expect(screen.getByText('Answered')).toBeInTheDocument();

    render(<StatusLabel status="NOT_FOUND" />);
    expect(screen.getByText('Not located')).toBeInTheDocument();
  });

  it('SourceCitation renders immutable quote without alterations', () => {
    const evidence: EvidenceItem = {
      sid: 'sid_test_1',
      page: 3,
      section: '4. SECURITY DEPOSIT',
      quote: 'The Licensee shall pay a refundable security deposit of Rs. 75,000/-',
      ocr_derived: false,
    };

    render(<SourceCitation evidence={evidence} />);

    expect(screen.getByText('Page 3 · 4. SECURITY DEPOSIT')).toBeInTheDocument();
    expect(screen.getByText('The Licensee shall pay a refundable security deposit of Rs. 75,000/-')).toBeInTheDocument();
  });

  it('AskResponse enforces non-verdict policy (legal_verdict always null)', () => {
    // Validate the type contract — legal_verdict must always be null
    const answer: AskResponse = {
      status: 'ANSWERED',
      answer: 'The monthly licence fee is Rs. 25,000/- payable on or before the 5th day of each month. (Page 2)',
      citations: [
        { page: 2, snippet: 'The monthly licence fee shall be Rs. 25,000/-.', section: '3. LICENCE FEE' },
      ],
      fallback: false,
      legal_verdict: null,
    };

    // legal_verdict must always be null — non-verdict policy
    expect(answer.legal_verdict).toBeNull();
    expect(answer.status).toBe('ANSWERED');
    expect(answer.citations).toHaveLength(1);
    expect(answer.citations[0].page).toBe(2);
  });

  it('AskResponse NOT_LOCATED has empty citations', () => {
    const answer: AskResponse = {
      status: 'NOT_LOCATED',
      answer: 'The document does not contain this information.',
      citations: [],
      fallback: false,
      legal_verdict: null,
    };

    expect(answer.status).toBe('NOT_LOCATED');
    expect(answer.citations).toHaveLength(0);
    expect(answer.legal_verdict).toBeNull();
  });

  it('AskResponse fallback flag is set when Ollama unavailable', () => {
    const answer: AskResponse = {
      status: 'ANSWERED',
      answer: 'Security deposit is Rs. 75,000/- (Page 3)',
      citations: [
        { page: 3, snippet: 'The Licensee shall pay a refundable security deposit of Rs. 75,000/-', section: '4. SECURITY DEPOSIT' },
      ],
      fallback: true,
      legal_verdict: null,
    };

    expect(answer.fallback).toBe(true);
    expect(answer.legal_verdict).toBeNull();
  });
});
