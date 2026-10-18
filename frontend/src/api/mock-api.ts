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
 * - Supports realistic edge cases: ambiguity, conflict, OCR, language limitation,
 *   legal limit, model unavailable, deletion failure.
 */

import type { LexiGuardApi } from './index';
import type {
  SessionTokenResponse,
  HealthResponse,
  DocumentCard,
  UploadDocumentResponse,
  RenderedAnswer,
  ReviewResponse,
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
    4: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n5. NOTICE PERIOD\n\nEither party wishing to terminate this agreement shall give 30 (thirty) days written notice to the other party.\n\n6. LOCK-IN PERIOD\n\nBoth parties agree to a lock-in period of 6 (six) months from the commencement date. During this period, neither party may terminate this agreement except by mutual written consent.\n\n[Note: Clause 5 gives 30 days notice. Clause 8 below refers to 60 days notice for the Licensor — this may constitute a conflict in the agreement.]',
    5: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n7. RESTRICTIONS\n\nThe Licensee shall not:\na) Sublet or assign the premises to any third party without prior written consent of the Licensor.\nb) Keep pets or animals on the premises.\nc) Make any structural alterations to the premises.\n\n8. TERMINATION BY LICENSOR\n\nThe Licensor may terminate this agreement by giving 60 (sixty) days written notice to the Licensee.',
  },
  [MOCK_DOC_ID_2]: {
    1: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\nRental Agreement for residential premises at Plot 12, Sector 5, Noida 201301.\nTenant: Mr. Arjun Das | Landlord: XYZ Properties Pvt. Ltd.\n\nMonthly Rent: Rs. 18,000/-. Duration: 11 months.',
    2: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n2. The tenant shall maintain the property in good condition.\n3. Maintenance of common areas is the responsibility of the housing society.',
    3: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n[PAGE LANGUAGE GATE TRIGGERED — possible non-English content detected on this page. The following text may not have been fully assessed.]\n\n... [page content may be partially unassessed] ...',
    4: '[SYNTHETIC — NOT A REAL AGREEMENT]\n\n5. DISPUTE RESOLUTION\n\nAll disputes arising out of or in connection with this agreement shall be subject to the jurisdiction of courts in Noida, Uttar Pradesh.',
  },
};

// Synthetic answer fixtures
function makeMockAnswer(docId: string, question: string): RenderedAnswer {
  const lowerQ = question.toLowerCase();

  // Legal limit scenario
  if (lowerQ.includes('enforceable') || lowerQ.includes('valid') || lowerQ.includes('legal')) {
    return {
      status: 'LEGAL_LIMIT',
      answer: 'LexiGuard provides factual document triage and cannot provide legal verdicts, enforceability determinations, or judicial predictions. Below are the relevant clauses located in your agreement. Please consult a qualified legal professional to evaluate enforceability under applicable jurisdiction law.',
      claims: [
        {
          claim_id: 'item_001',
          text: 'The agreement states a lock-in period of 6 months from the commencement date.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_lock_001', page: 4, section: '6. LOCK-IN PERIOD', quote: 'Both parties agree to a lock-in period of 6 (six) months from the commencement date. During this period, neither party may terminate this agreement except by mutual written consent.', ocr_derived: false }
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
      jurisdiction_flags: ['May depend on local law — confirm locally.'],
      recommend_professional_review: true,
      legal_verdict: null,
    };
  }

  // Notice period conflict scenario
  if (lowerQ.includes('notice')) {
    return {
      status: 'AMBIGUOUS',
      answer: 'The agreement contains two different notice periods that may conflict with each other.',
      claims: [
        {
          claim_id: 'item_001',
          text: 'Clause 5 states that either party wishing to terminate shall give 30 days written notice.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_notice_001', page: 4, section: '5. NOTICE PERIOD', quote: 'Either party wishing to terminate this agreement shall give 30 (thirty) days written notice to the other party.', ocr_derived: false }
          ],
        },
      ],
      interpretations: [],
      concerns: [],
      ambiguities: [],
      conflicts: [
        {
          item_id: 'conflict_001',
          text: 'Clause 5 refers to a 30-day notice period for either party, while Clause 8 separately specifies a 60-day notice period for the Licensor\'s termination. These two clauses give different notice periods for the same scenario.',
          evidence: [
            { sid: 'sid_notice_001', page: 4, section: '5. NOTICE PERIOD', quote: 'Either party wishing to terminate this agreement shall give 30 (thirty) days written notice to the other party.', ocr_derived: false },
            { sid: 'sid_term_001', page: 5, section: '8. TERMINATION BY LICENSOR', quote: 'The Licensor may terminate this agreement by giving 60 (sixty) days written notice to the Licensee.', ocr_derived: false },
          ],
        },
      ],
      general_explanations: [],
      missing_information: [],
      extraction_warnings: [],
      external_law_required: false,
      jurisdiction_flags: [],
      recommend_professional_review: true,
      legal_verdict: null,
    };
  }

  // Rent query
  if (lowerQ.includes('rent') || lowerQ.includes('payment') || lowerQ.includes('fee')) {
    return {
      status: 'ANSWERED',
      answer: 'The agreement sets out the monthly licence fee and a late payment charge.',
      claims: [
        {
          claim_id: 'item_001',
          text: 'The monthly licence fee is Rs. 25,000/- payable on or before the 5th day of each month.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_rent_001', page: 2, section: '3. LICENCE FEE', quote: 'The monthly licence fee shall be Rs. 25,000/- (Rupees Twenty-Five Thousand Only) payable on or before the 5th day of each month.', ocr_derived: false }
          ],
        },
        {
          claim_id: 'item_002',
          text: 'A late payment charge of Rs. 500/- per day applies after the 5th day of the month.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_rent_002', page: 2, section: '3. LICENCE FEE', quote: 'A late payment charge of Rs. 500/- per day shall apply after the 5th day of the month.', ocr_derived: false }
          ],
        },
      ],
      interpretations: [],
      concerns: [
        {
          item_id: 'concern_001',
          text: 'The daily late payment charge accrues from the 5th day of the month. This could result in significant amounts over a payment cycle.',
          evidence: [
            { sid: 'sid_rent_002', page: 2, section: '3. LICENCE FEE', quote: 'A late payment charge of Rs. 500/- per day shall apply after the 5th day of the month.', ocr_derived: false }
          ],
        },
      ],
      ambiguities: [],
      conflicts: [],
      general_explanations: [],
      missing_information: [],
      extraction_warnings: [],
      external_law_required: false,
      jurisdiction_flags: [],
      recommend_professional_review: false,
      legal_verdict: null,
    };
  }

  // Deposit query
  if (lowerQ.includes('deposit')) {
    return {
      status: 'ANSWERED',
      answer: 'The agreement specifies a refundable security deposit amount and refund conditions.',
      claims: [
        {
          claim_id: 'item_001',
          text: 'The security deposit is Rs. 75,000/- to be paid at the time of signing.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_dep_001', page: 3, section: '4. SECURITY DEPOSIT', quote: 'The Licensee shall pay a refundable security deposit of Rs. 75,000/- (Rupees Seventy-Five Thousand Only) at the time of signing this agreement.', ocr_derived: false }
          ],
        },
        {
          claim_id: 'item_002',
          text: 'The deposit is to be refunded within 30 days of vacating, subject to deduction of outstanding dues and repair charges.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_dep_002', page: 3, section: '4. SECURITY DEPOSIT', quote: 'The deposit shall be refunded within 30 days of the Licensee vacating the premises, subject to deduction of outstanding dues and repair charges.', ocr_derived: false }
          ],
        },
      ],
      interpretations: [
        {
          item_id: 'interp_001',
          text: 'The phrase "subject to deduction of outstanding dues and repair charges" leaves the specific basis for deductions unspecified in this clause.',
          evidence: [
            { sid: 'sid_dep_002', page: 3, section: '4. SECURITY DEPOSIT', quote: 'subject to deduction of outstanding dues and repair charges', ocr_derived: false }
          ],
        },
      ],
      concerns: [],
      ambiguities: [
        {
          item_id: 'amb_001',
          text: 'The agreement does not define "repair charges" or specify how the cost of repairs will be assessed. This ambiguity relates to how much of the deposit may be retained.',
          evidence: [
            { sid: 'sid_dep_002', page: 3, section: '4. SECURITY DEPOSIT', quote: 'subject to deduction of outstanding dues and repair charges', ocr_derived: false }
          ],
        },
      ],
      conflicts: [],
      general_explanations: [],
      missing_information: [],
      extraction_warnings: [],
      external_law_required: false,
      jurisdiction_flags: ['May depend on local law — confirm locally.'],
      recommend_professional_review: false,
      legal_verdict: null,
    };
  }

  // Out of scope scenario
  if (lowerQ.includes('stock') || lowerQ.includes('tax return') || lowerQ.includes('cricket')) {
    return {
      status: 'OUT_OF_SCOPE',
      answer: 'This question is outside the scope of what LexiGuard can help with. LexiGuard is designed to help you understand what your rental or leave-and-licence agreement states. Please ask a question about your uploaded document.',
      claims: [],
      interpretations: [],
      concerns: [],
      ambiguities: [],
      conflicts: [],
      general_explanations: [],
      missing_information: [],
      extraction_warnings: [],
      external_law_required: false,
      jurisdiction_flags: [],
      recommend_professional_review: false,
      legal_verdict: null,
    };
  }

  // OCR language limitation scenario for doc 2
  if (docId === MOCK_DOC_ID_2 && (lowerQ.includes('page 3') || lowerQ.includes('third page'))) {
    return {
      status: 'LIMITED',
      answer: 'Page 3 of this document triggered the language gate — possible non-English content was detected. This page could not be fully assessed.',
      claims: [],
      interpretations: [],
      concerns: [],
      ambiguities: [],
      conflicts: [],
      general_explanations: [],
      missing_information: [
        { code: 'UNREADABLE_CONTENT', message: 'Page 3: language gate triggered — possible non-English content detected. This page has not been fully assessed.' },
      ],
      extraction_warnings: ['Page 3: language gate triggered — possible non-English content.'],
      external_law_required: false,
      jurisdiction_flags: [],
      recommend_professional_review: false,
      legal_verdict: null,
    };
  }

  // Not located scenario
  if (lowerQ.includes('pet') || lowerQ.includes('cat') || lowerQ.includes('dog')) {
    return {
      status: 'ANSWERED',
      answer: 'The agreement addresses keeping pets on the premises.',
      claims: [
        {
          claim_id: 'item_001',
          text: 'The Licensee is restricted from keeping pets or animals on the premises.',
          classification: 'DIRECT',
          evidence: [
            { sid: 'sid_rest_001', page: 5, section: '7. RESTRICTIONS', quote: 'Keep pets or animals on the premises.', ocr_derived: false }
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
      external_law_required: false,
      jurisdiction_flags: [],
      recommend_professional_review: false,
      legal_verdict: null,
    };
  }

  // Default: general answer
  return {
    status: 'ANSWERED',
    answer: 'Based on the retrieved provisions, here is what the agreement states about this topic.',
    claims: [
      {
        claim_id: 'item_001',
        text: 'This agreement is a Leave and Licence agreement valid for 11 months between a Licensor and a Licensee.',
        classification: 'DIRECT',
        evidence: [
          { sid: 'sid_term_gen', page: 1, section: '', quote: 'This Leave and Licence Agreement is made on the 1st day of November 2026...', ocr_derived: false },
          { sid: 'sid_term_dur', page: 2, section: '2. TERM', quote: 'This agreement shall be valid for a period of eleven (11) months commencing from 1st November 2026 and ending on 30th September 2027.', ocr_derived: false },
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
    external_law_required: false,
    jurisdiction_flags: [],
    recommend_professional_review: false,
    legal_verdict: null,
  };
}

function makeMockReview(docId: string): ReviewResponse {
  const baseTopics = [
    { topic_id: 'parties', label: 'Parties', status: 'FOUND' as const, evidence: [{ sid: 'sid_parties', page: 1, section: '', quote: 'This Leave and Licence Agreement is made on the 1st day of November 2026...', ocr_derived: false }] },
    { topic_id: 'term', label: 'Term', status: 'FOUND' as const, evidence: [{ sid: 'sid_term', page: 2, section: '2. TERM', quote: 'This agreement shall be valid for a period of eleven (11) months...', ocr_derived: false }] },
    { topic_id: 'rent', label: 'Rent', status: 'FOUND' as const, evidence: [{ sid: 'sid_rent_001', page: 2, section: '3. LICENCE FEE', quote: 'The monthly licence fee shall be Rs. 25,000/-...', ocr_derived: false }], attention_reason: 'Contains a late payment penalty clause.' },
    { topic_id: 'deposit', label: 'Deposit', status: 'AMBIGUOUS' as const, evidence: [{ sid: 'sid_dep_001', page: 3, section: '4. SECURITY DEPOSIT', quote: 'The Licensee shall pay a refundable security deposit of Rs. 75,000/-...', ocr_derived: false }], attention_reason: 'Deduction criteria are not specified.' },
    { topic_id: 'notice', label: 'Notice', status: 'POSSIBLE_CONFLICT' as const, evidence: [{ sid: 'sid_notice_001', page: 4, section: '5. NOTICE PERIOD', quote: 'Either party wishing to terminate this agreement shall give 30 (thirty) days written notice...', ocr_derived: false }], attention_reason: 'Listed first because two clauses give different notice periods.' },
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

export class MockApiClient implements LexiGuardApi {
  async exchangeLaunchCode(code: string): Promise<SessionTokenResponse> {
    await delay(300);
    if (code === 'invalid-code' || code === 'expired-code') {
      throw new ApiError('session-expired', 'Invalid, expired or already-used launch code.', 401);
    }
    // Accept any code in mock mode
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
    await delay(1500); // Simulate processing time

    // Simulate unsupported type
    const name = file.name.toLowerCase();
    if (!name.endsWith('.pdf') && !name.endsWith('.txt')) {
      throw new ApiError('unsupported-type', 'File is not a supported format. Upload a PDF (starting with %PDF-) or a plain-text (.txt) file.', 422);
    }

    // Simulate size check
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
    // Add synthetic pages
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

  async askDocument(documentId: string, question: string): Promise<RenderedAnswer> {
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
    // Page images not available in mock mode
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
