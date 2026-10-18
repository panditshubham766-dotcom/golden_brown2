import { describe, it, expect } from 'vitest';
import { mockApiClient } from '../api/mock-api';
import { LexiGuardApiClient } from '../api/client';
import { ApiError } from '../api/errors';

describe('LexiGuard API Client & Mock Implementation', () => {
  it('exchanges launch code in mock client', async () => {
    const res = await mockApiClient.exchangeLaunchCode('valid-code');
    expect(res.token).toBeDefined();
    expect(typeof res.token).toBe('string');
  });

  it('rejects expired launch code in mock client', async () => {
    await expect(mockApiClient.exchangeLaunchCode('expired-code')).rejects.toThrow(ApiError);
  });

  it('lists documents in mock client with realistic properties', async () => {
    const docs = await mockApiClient.listDocuments();
    expect(Array.isArray(docs)).toBe(true);
    expect(docs.length).toBeGreaterThan(0);
    const doc = docs[0];
    expect(doc.document_id).toBeDefined();
    expect(doc.page_count).toBeGreaterThan(0);
    expect(doc.status).toBe('ready');
  });

  it('handles question answering with legal boundaries', async () => {
    const docs = await mockApiClient.listDocuments();
    const docId = docs[0].document_id;

    // Test legal limit scenario
    const legalAnswer = await mockApiClient.askDocument(docId, 'Is this clause legally valid and enforceable?');
    expect(legalAnswer.status).toBe('LEGAL_LIMIT');
    expect(legalAnswer.legal_verdict).toBeNull();
    expect(legalAnswer.external_law_required).toBe(true);
  });

  it('handles conflicting clauses in rental agreement', async () => {
    const docs = await mockApiClient.listDocuments();
    const docId = docs[0].document_id;

    // Test notice period conflict scenario
    const conflictAnswer = await mockApiClient.askDocument(docId, 'What is the notice period?');
    expect(conflictAnswer.conflicts.length).toBeGreaterThan(0);
    const conflict = conflictAnswer.conflicts[0];
    expect(conflict.evidence?.length).toBeGreaterThanOrEqual(2);
  });

  it('prevents question greater than 500 characters', async () => {
    const docs = await mockApiClient.listDocuments();
    const docId = docs[0].document_id;
    const longQ = 'a'.repeat(501);

    await expect(mockApiClient.askDocument(docId, longQ)).rejects.toThrow(ApiError);
  });

  it('requires bearer token on authenticated calls in production client', async () => {
    const client = new LexiGuardApiClient();
    // No token set
    await expect(client.getHealth()).rejects.toThrow(ApiError);
    await expect(client.listDocuments()).rejects.toThrow(ApiError);
  });

  it('handles document deletion truthfully reporting app removal', async () => {
    const docs = await mockApiClient.listDocuments();
    const docId = docs[0].document_id;

    const delRes = await mockApiClient.deleteDocument(docId);
    expect(delRes.document_id).toBe(docId);
    expect(delRes.app_files_removed).toBe(true);
    expect(delRes.fts_rows_removed).toBe(true);
    expect(delRes.note).toContain('SSD');
  });
});
