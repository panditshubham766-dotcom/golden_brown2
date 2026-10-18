/**
 * LexiGuard Mock API implementation.
 *
 * Used when VITE_USE_MOCK_API=true (development only).
 * Implements exactly the same LexiGuardApi interface as the production client.
 *
 * Rules:
 * - All data is in-memory only. Nothing is persisted.
 * - Never contacts any external host.
 * - Clearly labelled as synthetic mock data.
 */

import type { LexiGuardApi } from './index';
import type {
  SessionTokenResponse,
  HealthResponse,
  DocumentCard,
  UploadDocumentResponse,
  AskResponse,
  ReviewResponse,
  SummaryResponse,
  SourcePageResponse,
  DeletionResponse,
} from './contracts';
import { ApiError } from './errors';

const MOCK_DELAY_MS = 600;

function delay(ms: number = MOCK_DELAY_MS): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Synthetic fixtures ────────────────────────────────────────────────────────
// All data here is entirely synthetic. No real rental agreement was used.

const MOCK_DOC_ID_1 = 'aabbccdd11223344aabbccdd11223344';
const MOCK_DOC_ID_2 = 'deadbeef00112233deadbeef00112233';

const MOCK_DOCS: DocumentCard[] = [
  {
    document_id: MOCK_DOC_ID_1,
    page_count: 8,
    status: 'ready',
    quality_summary: '8 pages',
    warnings: [],
    created_at: '2026-10-17T10:30:00Z',
  },
  {
    document_id: MOCK_DOC_ID_2,
    page_count: 4,
    status: 'ready',
    quality_summary: '4 pages',
    warnings: ['Page 3: language gate triggered — possible non-English content.'],
    created_at: '2026-10-18T09:00:00Z',
  },
];

// Tracks in-memory uploaded docs (simulates runtime state only)
const RUNTIME_DOCS: Map<string, DocumentCard> = new Map(
  MOCK_DOCS.map(d => [d.document_id, d])
);

// Synthetic page texts — clearly artificial
const MOCK_PAGES: Record<string, Record<number, string>> = {
  [MOCK_DOC_ID_1]: {
    1: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\nThis Leave and Licence Agreement is made on the 1st day of November 2026 between:\n\nLicensor: Mr. Rajan Mehta, residing at 45, Green Valley Road, Pune 411001\nLicensee: Ms. Priya Sharma, residing at 22, Lakeview Apartments, Mumbai 400001\n\nProperty: Flat No. 301, Silver Heights, Kharadi, Pune 411014',
    2: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n2. TERM\n\nThis agreement shall be valid for a period of eleven (11) months commencing from 1st November 2026 and ending on 30th September 2027.\n\n3. LICENCE FEE\n\nThe monthly licence fee shall be Rs. 25,000/- (Rupees Twenty-Five Thousand Only) payable on or before the 5th day of each month.\n\nA late payment charge of Rs. 500/- per day shall apply after the 5th day of the month.',
    3: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n4. SECURITY DEPOSIT\n\nThe Licensee shall pay a refundable security deposit of Rs. 75,000/- (Rupees Seventy-Five Thousand Only) at the time of signing this agreement.\n\nThe deposit shall be refunded within 30 days of the Licensee vacating the premises, subject to deduction of outstanding dues and repair charges.',
    4: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n5. NOTICE PERIOD\n\nEither party wishing to terminate this agreement shall give 30 (thirty) days written notice to the other party.\n\n6. LOCK-IN PERIOD\n\nBoth parties agree to a lock-in period of 6 (six) months from the commencement date. During this period, neither party may terminate this agreement except by mutual written consent.',
    5: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n7. RESTRICTIONS\n\nThe Licensee shall not:\na) Sublet or assign the premises to any third party without prior written consent of the Licensor.\nb) Keep pets or animals on the premises.\nc) Make any structural alterations to the premises.\n\n8. TERMINATION BY LICENSOR\n\nThe Licensor may terminate this agreement by giving 60 (sixty) days written notice to the Licensee.',
  },
  [MOCK_DOC_ID_2]: {
    1: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\nRental Agreement for residential premises at Plot 12, Sector 5, Noida 201301.\nTenant: Mr. Arjun Das | Landlord: XYZ Properties Pvt. Ltd.\n\nMonthly Rent: Rs. 18,000/-. Duration: 11 months.',
    2: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n2. The tenant shall maintain the property in good condition.\n3. Maintenance of common areas is the responsibility of the housing society.',
    3: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n[PAGE LANGUAGE GATE TRIGGERED — possible non-English content detected on this page.]\n\n... [page content may be partially unassessed] ...',
    4: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n5. DISPUTE RESOLUTION\n\nAll disputes arising out of or in connection with this agreement shall be subject to the jurisdiction of courts in Noida, Uttar Pradesh.',
  },
};

// ── Single-Pass RAG mock answers ──────────────────────────────────────────────
function makeMockAnswer(docId: string, question: string): AskResponse {
  const lowerQ = question.toLowerCase();

  // Legal boundary
  if (lowerQ.includes('enforceable') || lowerQ.includes('valid') || lowerQ.includes('legal')) {
    return {
      status: 'ANSWERED',
      answer: 'LexiGuard provides factual document triage and cannot provide legal verdicts or enforceability determinations. The agreement contains a lock-in period of 6 months (Page 4). Please consult a qualified legal professional for enforceability questions.',
      citations: [
        { page: 4, snippet: 'Both parties agree to a lock-in period of 6 (six) months from the commencement date.', section: '6. LOCK-IN PERIOD' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Notice period
  if (lowerQ.includes('notice')) {
    return {
      status: 'ANSWERED',
      answer: 'The agreement specifies a 30-day written notice period for either party wishing to terminate (Page 4). Note: Clause 8 on Page 5 separately specifies 60 days for the Licensor — these may conflict.',
      citations: [
        { page: 4, snippet: 'Either party wishing to terminate this agreement shall give 30 (thirty) days written notice to the other party.', section: '5. NOTICE PERIOD' },
        { page: 5, snippet: 'The Licensor may terminate this agreement by giving 60 (sixty) days written notice to the Licensee.', section: '8. TERMINATION BY LICENSOR' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Rent / fee
  if (lowerQ.includes('rent') || lowerQ.includes('payment') || lowerQ.includes('fee')) {
    return {
      status: 'ANSWERED',
      answer: 'The monthly licence fee is Rs. 25,000/- payable on or before the 5th day of each month (Page 2). A late payment charge of Rs. 500/- per day applies after the 5th.',
      citations: [
        { page: 2, snippet: 'The monthly licence fee shall be Rs. 25,000/- (Rupees Twenty-Five Thousand Only) payable on or before the 5th day of each month.', section: '3. LICENCE FEE' },
        { page: 2, snippet: 'A late payment charge of Rs. 500/- per day shall apply after the 5th day of the month.', section: '3. LICENCE FEE' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Deposit
  if (lowerQ.includes('deposit')) {
    return {
      status: 'ANSWERED',
      answer: 'The security deposit is Rs. 75,000/- payable at signing (Page 3). It shall be refunded within 30 days of vacating, subject to deduction of outstanding dues and repair charges.',
      citations: [
        { page: 3, snippet: 'The Licensee shall pay a refundable security deposit of Rs. 75,000/- (Rupees Seventy-Five Thousand Only) at the time of signing this agreement.', section: '4. SECURITY DEPOSIT' },
        { page: 3, snippet: 'The deposit shall be refunded within 30 days of the Licensee vacating the premises, subject to deduction of outstanding dues and repair charges.', section: '4. SECURITY DEPOSIT' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Parties
  if (lowerQ.includes('parties') || lowerQ.includes('licensor') || lowerQ.includes('licensee')) {
    return {
      status: 'ANSWERED',
      answer: 'The Licensor is Mr. Rajan Mehta and the Licensee is Ms. Priya Sharma (Page 1). The property is Flat No. 301, Silver Heights, Kharadi, Pune 411014.',
      citations: [
        { page: 1, snippet: 'Licensor: Mr. Rajan Mehta, residing at 45, Green Valley Road, Pune 411001\nLicensee: Ms. Priya Sharma, residing at 22, Lakeview Apartments, Mumbai 400001', section: '' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Out of scope
  if (lowerQ.includes('stock') || lowerQ.includes('tax return') || lowerQ.includes('cricket')) {
    return {
      status: 'NOT_LOCATED',
      answer: 'The document does not contain this information.',
      citations: [],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Language gate
  if (docId === MOCK_DOC_ID_2 && (lowerQ.includes('page 3') || lowerQ.includes('third page'))) {
    return {
      status: 'ANSWERED',
      answer: 'Page 3 of this document triggered the language gate — possible non-English content was detected. This page could not be fully assessed. (Page 3)',
      citations: [
        { page: 3, snippet: '[PAGE LANGUAGE GATE TRIGGERED — possible non-English content detected on this page.]', section: '' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Pets / restrictions
  if (lowerQ.includes('pet') || lowerQ.includes('cat') || lowerQ.includes('dog') || lowerQ.includes('restriction')) {
    return {
      status: 'ANSWERED',
      answer: 'The Licensee is restricted from keeping pets or animals on the premises (Page 5). Subletting and structural alterations are also prohibited.',
      citations: [
        { page: 5, snippet: 'Keep pets or animals on the premises.', section: '7. RESTRICTIONS' },
      ],
      fallback: false,
      legal_verdict: null,
    };
  }

  // Default general answer
  return {
    status: 'ANSWERED',
    answer: `Based on the retrieved document provisions: This is a Leave and Licence Agreement valid for 11 months between Mr. Rajan Mehta (Licensor) and Ms. Priya Sharma (Licensee) for Flat No. 301, Silver Heights, Kharadi, Pune. (Pages 1–2)`,
    citations: [
      { page: 1, snippet: 'This Leave and Licence Agreement is made on the 1st day of November 2026...', section: '' },
      { page: 2, snippet: 'This agreement shall be valid for a period of eleven (11) months commencing from 1st November 2026 and ending on 30th September 2027.', section: '2. TERM' },
    ],
    fallback: false,
    legal_verdict: null,
  };
}

function makeMockReview(docId: string): ReviewResponse {
  const baseTopics = [
    { topic_id: 'parties', label: 'Parties', status: 'FOUND' as const, evidence: [{ sid: 'sid_parties', page: 1, section: '', quote: 'This Leave and Licence Agreement is made on the 1st day of November 2026...', ocr_derived: false }] },
    { topic_id: 'term', label: 'Term', status: 'FOUND' as const, evidence: [{ sid: 'sid_term', page: 2, section: '2. TERM', quote: 'This agreement shall be valid for a period of eleven (11) months...', ocr_derived: false }] },
    { topic_id: 'rent', label: 'Rent', status: 'FOUND' as const, evidence: [{ sid: 'sid_rent_001', page: 2, section: '3. LICENCE FEE', quote: 'The monthly licence fee shall be Rs. 25,000/-...', ocr_derived: false }], attention_reason: 'Contains a late payment penalty clause.' },
    { topic_id: 'deposit', label: 'Deposit', status: 'AMBIGUOUS' as const, evidence: [{ sid: 'sid_dep_001', page: 3, section: '4. SECURITY DEPOSIT', quote: 'The Licensee shall pay a refundable security deposit of Rs. 75,000/-...', ocr_derived: false }], attention_reason: 'Deduction criteria are not specified.' },
    { topic_id: 'notice', label: 'Notice', status: 'POSSIBLE_CONFLICT' as const, evidence: [{ sid: 'sid_notice_001', page: 4, section: '5. NOTICE PERIOD', quote: 'Either party wishing to terminate this agreement shall give 30 (thirty) days written notice...', ocr_derived: false }], attention_reason: 'Two clauses give different notice periods (30 days vs 60 days).' },
    { topic_id: 'lock_in', label: 'Lock-in', status: 'FOUND' as const, evidence: [{ sid: 'sid_lock_001', page: 4, section: '6. LOCK-IN PERIOD', quote: 'Both parties agree to a lock-in period of 6 (six) months...', ocr_derived: false }], attention_reason: 'Contains forfeiture/lock-in obligation.' },
    { topic_id: 'penalties', label: 'Penalties', status: 'FOUND' as const, evidence: [{ sid: 'sid_rent_002', page: 2, section: '3. LICENCE FEE', quote: 'A late payment charge of Rs. 500/- per day shall apply after the 5th day of the month.', ocr_derived: false }] },
    { topic_id: 'restrictions', label: 'Restrictions', status: 'FOUND' as const, evidence: [{ sid: 'sid_rest_001', page: 5, section: '7. RESTRICTIONS', quote: 'The Licensee shall not: a) Sublet or assign the premises...', ocr_derived: false }] },
    { topic_id: 'maintenance', label: 'Maintenance', status: 'NOT_FOUND' as const, evidence: [] },
    { topic_id: 'disputes', label: 'Disputes', status: docId === MOCK_DOC_ID_2 ? 'FOUND' as const : 'NOT_ASSESSED' as const, evidence: docId === MOCK_DOC_ID_2 ? [{ sid: 'sid_dispute', page: 4, section: '5. DISPUTE RESOLUTION', quote: 'All disputes...shall be subject to the jurisdiction of courts in Noida, Uttar Pradesh.', ocr_derived: false }] : [] },
  ];

  return {
    topics: baseTopics,
    professional_questions: [
      {
        question_id: 'pq_001',
        text: 'The agreement contains two different notice periods (30 days in Clause 5 and 60 days in Clause 8). Which notice period applies when the Licensor wishes to terminate?',
        evidence: [
          { sid: 'sid_notice_001', page: 4, section: '5. NOTICE PERIOD', quote: 'Either party wishing to terminate this agreement shall give 30 (thirty) days written notice to the other party.', ocr_derived: false },
          { sid: 'sid_term_001', page: 5, section: '8. TERMINATION BY LICENSOR', quote: 'The Licensor may terminate this agreement by giving 60 (sixty) days written notice to the Licensee.', ocr_derived: false },
        ],
      },
      {
        question_id: 'pq_002',
        text: 'What specific types of damage or repair charges can be deducted from the security deposit, and how are they assessed?',
        evidence: [
          { sid: 'sid_dep_002', page: 3, section: '4. SECURITY DEPOSIT', quote: 'subject to deduction of outstanding dues and repair charges', ocr_derived: false },
        ],
      },
    ],
  };
}

function makeMockSummary(docId: string): SummaryResponse {
  const isDoc2 = docId === MOCK_DOC_ID_2;
  return {
    document_id: docId,
    summary_markdown: isDoc2
      ? `## Document Overview\n\n**Document Type & Identified Parties**  \nResidential Rental Agreement between Mr. Arjun Das (Tenant) and XYZ Properties Pvt. Ltd. (Landlord) for Plot 12, Sector 5, Noida 201301.\n\n**Effective Date & Term/Duration**  \n11-month duration. Exact commencement date not located in readable pages.\n\n**Core Purpose / Key Obligations**  \nResidential tenancy at Rs. 18,000/- per month. Tenant responsible for maintaining property in good condition.\n\n**Critical Clauses** *(rent, deposit, notice, lock-in, penalties)*  \nMonthly rent: Rs. 18,000/-. Dispute resolution under Noida court jurisdiction (Page 4). Page 3 was not fully assessed (language gate).\n\n**Notable Risks / Items Requiring Attention**  \nPage 3 triggered the language gate — content may be incomplete. Deposit and notice terms not clearly located.`
      : `## Document Overview\n\n**Document Type & Identified Parties**  \nLeave and Licence Agreement between Mr. Rajan Mehta (Licensor) of Pune and Ms. Priya Sharma (Licensee) of Mumbai, for Flat No. 301, Silver Heights, Kharadi, Pune 411014. (Page 1)\n\n**Effective Date & Term/Duration**  \n11 months from 1st November 2026 to 30th September 2027. (Page 2)\n\n**Core Purpose / Key Obligations**  \nResidential leave and licence arrangement. Monthly licence fee of Rs. 25,000/- due by the 5th of each month. Licensee must maintain the property and comply with restrictions. (Pages 2–5)\n\n**Critical Clauses** *(rent, deposit, notice, lock-in, penalties)*  \nLicence fee: Rs. 25,000/-/month with Rs. 500/-/day late penalty (Page 2). Security deposit: Rs. 75,000/- refundable within 30 days of vacating (Page 3). Notice period: 30 days (Clause 5, Page 4) — conflicts with 60 days in Clause 8 (Page 5). Lock-in: 6 months (Page 4).\n\n**Notable Risks / Items Requiring Attention**  \nConflicting notice periods (30 days vs 60 days) in Clauses 5 and 8. Deposit deduction criteria are unspecified. Maintenance obligations are not explicitly covered.`,
    key_points: isDoc2
      ? [
          { label: 'Identified Parties', value: 'Mr. Arjun Das (Tenant) and XYZ Properties Pvt. Ltd. (Landlord).', page_refs: [1] },
          { label: 'Rent / Licence Fee', value: 'Monthly rent: Rs. 18,000/-', page_refs: [1] },
          { label: 'Dispute Resolution', value: 'Courts in Noida, Uttar Pradesh.', page_refs: [4] },
        ]
      : [
          { label: 'Identified Parties', value: 'Licensor: Mr. Rajan Mehta (Pune). Licensee: Ms. Priya Sharma (Mumbai).', page_refs: [1] },
          { label: 'Effective Date & Term', value: '11 months: 1st November 2026 to 30th September 2027.', page_refs: [2] },
          { label: 'Core Purpose / Key Obligations', value: 'Residential leave & licence. Monthly fee Rs. 25,000/- due by the 5th.', page_refs: [2] },
          { label: 'Critical Clauses', value: 'Deposit Rs. 75,000/- (Page 3). Notice: 30 days/60 days conflict (Pages 4–5). Lock-in: 6 months (Page 4).', page_refs: [3, 4, 5] },
          { label: 'Notable Risks / Items Requiring Attention', value: 'Conflicting notice periods. Unspecified deposit deduction criteria. No explicit maintenance clause.', page_refs: [4, 5] },
        ],
    referenced_pages: isDoc2 ? [1, 2, 4] : [1, 2, 3, 4, 5],
    model_used: 'mock-gemma4',
    fallback: false,
  };
}

export class MockApiClient implements LexiGuardApi {
  async exchangeLaunchCode(code: string): Promise<SessionTokenResponse> {
    await delay(300);
    if (code === 'invalid-code' || code === 'expired-code') {
      throw new ApiError('session-expired', 'Invalid, expired or already-used launch code.', 401);
    }
    return { token: 'mock-token-synthetic-data-only' };
  }

  async getHealth(): Promise<HealthResponse> {
    await delay(200);
    return { ok: true, fts5: true };
  }

  async listDocuments(): Promise<DocumentCard[]> {
    await delay();
    return Array.from(RUNTIME_DOCS.values());
  }

  async uploadDocument(file: File): Promise<UploadDocumentResponse> {
    await delay(1500);

    const name = file.name.toLowerCase();
    if (!name.endsWith('.pdf') && !name.endsWith('.txt')) {
      throw new ApiError('unsupported-type', 'File is not a supported format. Upload a PDF or a plain-text (.txt) file.', 422);
    }

    if (file.size > 50 * 1024 * 1024) {
      throw new ApiError('too-large', 'File size exceeds the maximum upload size of 50 MB.', 413);
    }

    const docId = `mock${Date.now().toString(16)}${'0'.repeat(20)}`.slice(0, 32);
    const newCard: DocumentCard = {
      document_id: docId,
      page_count: 5,
      status: 'ready',
      quality_summary: '5 pages',
      warnings: [],
      created_at: new Date().toISOString(),
    };
    RUNTIME_DOCS.set(docId, newCard);
    MOCK_PAGES[docId] = {
      1: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\nUploaded document: Page 1 of synthetic test content.\nThis is mock data created for development purposes only.',
      2: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\nPage 2 — synthetic content for development.',
    };

    return {
      document_id: docId,
      page_count: 5,
      quality: { pages_read: 5, pages_unread: 0, overall: 'good' },
      warnings: [],
      status: 'ready',
    };
  }

  async askDocument(documentId: string, question: string): Promise<AskResponse> {
    await delay(1200);
    if (!RUNTIME_DOCS.has(documentId)) {
      throw new ApiError('not-found', 'Document not found.', 404);
    }
    if (question.length > 500) {
      throw new ApiError('validation-error', 'Question exceeds maximum allowed length of 500 characters.', 422);
    }
    return makeMockAnswer(documentId, question);
  }

  async getReview(documentId: string): Promise<ReviewResponse> {
    await delay(800);
    if (!RUNTIME_DOCS.has(documentId)) {
      throw new ApiError('not-found', 'Document not found.', 404);
    }
    return makeMockReview(documentId);
  }

  async summarizeDocument(documentId: string): Promise<SummaryResponse> {
    await delay(2000); // Simulate Gemma inference time
    if (!RUNTIME_DOCS.has(documentId)) {
      throw new ApiError('not-found', 'Document not found.', 404);
    }
    return makeMockSummary(documentId);
  }

  async getPage(documentId: string, physicalPage: number): Promise<SourcePageResponse> {
    await delay(300);
    if (!RUNTIME_DOCS.has(documentId)) {
      throw new ApiError('not-found', 'Document not found.', 404);
    }
    const pages = MOCK_PAGES[documentId] ?? {};
    const text = pages[physicalPage];
    if (!text) {
      throw new ApiError('not-found', `Page ${physicalPage} not found.`, 404);
    }
    return {
      physical_page: physicalPage,
      printed_label: `Page ${physicalPage}`,
      norm_text: text,
      is_readable: physicalPage !== 3 || documentId !== MOCK_DOC_ID_2,
      lang_supported: physicalPage !== 3 || documentId !== MOCK_DOC_ID_2,
      warnings: physicalPage === 3 && documentId === MOCK_DOC_ID_2
        ? ['Language gate triggered — possible non-English content.']
        : [],
    };
  }

  async getPageImage(_documentId: string, _physicalPage: number): Promise<Blob> {
    throw new ApiError('not-found', 'Page images are not available in mock mode.', 404);
  }

  async deleteDocument(documentId: string): Promise<DeletionResponse> {
    await delay(800);
    if (!RUNTIME_DOCS.has(documentId)) {
      throw new ApiError('not-found', 'Document not found.', 404);
    }
    RUNTIME_DOCS.delete(documentId);
    delete MOCK_PAGES[documentId];
    return {
      document_id: documentId,
      app_files_removed: true,
      fts_rows_removed: true,
      directory_absent: true,
      note: 'App-controlled files removed. This does NOT constitute forensic erasure from SSD, OS swap, or external backups. See docs/LIMITATIONS.md. [MOCK MODE — no real data was stored]',
    };
  }
}

export const mockApiClient = new MockApiClient();
