import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusLabel } from '../components/StatusLabel/StatusLabel';
import { SourceCitation } from '../components/SourceCitation/SourceCitation';
import { RenderedAnswerView } from '../features/ask/RenderedAnswerView';
import type { EvidenceItem, RenderedAnswer } from '../api/contracts';

describe('LexiGuard UI Components & Render Rules', () => {
  it('StatusLabel displays accessible and truthful text', () => {
    render(<StatusLabel value="ANSWERED" />);
    expect(screen.getByText('Answered')).toBeInTheDocument();

    render(<StatusLabel value="NOT_FOUND" />);
    expect(screen.getByText('Not located')).toBeInTheDocument();

    render(<StatusLabel value="LEGAL_LIMIT" />);
    expect(screen.getByText('Legal boundary')).toBeInTheDocument();
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
    expect(screen.getByText(/Quoted source text/i)).toBeInTheDocument();
  });

  it('RenderedAnswerView handles legal boundaries without legal verdict', () => {
    const answer: RenderedAnswer = {
      status: 'LEGAL_LIMIT',
      answer: 'LexiGuard cannot provide legal verdicts or enforceability determinations.',
      claims: [
        {
          claim_id: 'c1',
          text: 'Clause 6 specifies a lock-in period of 6 months.',
          classification: 'DIRECT',
          evidence: [
            {
              sid: 'sid_6',
              page: 4,
              section: '6. LOCK-IN',
              quote: 'Both parties agree to a lock-in period of 6 months.',
              ocr_derived: false,
            },
          ],
        },
      ],
      interpretations: [],
      concerns: [],
      ambiguities: [],
      conflicts: [],
      general_explanations: [],
      missing_information: [],
      extraction_warnings: [],
      external_law_required: true,
      jurisdiction_flags: ['Local tenancy act may apply'],
      recommend_professional_review: true,
      legal_verdict: null,
    };

    const handleOpen = vi.fn();
    render(<RenderedAnswerView answer={answer} onOpenSourceView={handleOpen} />);

    expect(screen.getByText('Legal boundary')).toBeInTheDocument();
    expect(screen.getByText(/LexiGuard cannot provide legal verdicts/i)).toBeInTheDocument();
    expect(screen.getByText(/Local tenancy act may apply/i)).toBeInTheDocument();
    expect(screen.getByText(/Legal Professional Review Recommended/i)).toBeInTheDocument();
  });
});
