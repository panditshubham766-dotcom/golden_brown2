import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

describe('Privacy and Security Static Verifications', () => {
  const srcDir = path.resolve(__dirname, '..');
  const indexHtmlPath = path.resolve(__dirname, '../../index.html');

  function scanFiles(dir: string, fileList: string[] = []): string[] {
    const files = fs.readdirSync(dir);
    for (const file of files) {
      const fullPath = path.join(dir, file);
      if (fs.statSync(fullPath).isDirectory()) {
        scanFiles(fullPath, fileList);
      } else if (/\.(ts|tsx|js|jsx|css|html)$/.test(file)) {
        fileList.push(fullPath);
      }
    }
    return fileList;
  }

  it('contains zero usage of localStorage or sessionStorage in src', () => {
    const files = scanFiles(srcDir);
    const violations: string[] = [];

    for (const file of files) {
      // Skip test files themselves
      if (file.includes('test')) continue;
      let content = fs.readFileSync(file, 'utf8');
      // Strip single-line and multi-line comments to avoid false positives in docstrings
      content = content.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
      if (/\blocalStorage\b/.test(content) || /\bsessionStorage\b/.test(content)) {
        violations.push(file);
      }
    }

    expect(violations).toEqual([]);
  });

  it('contains zero usage of document.cookie in src', () => {
    const files = scanFiles(srcDir);
    const violations: string[] = [];

    for (const file of files) {
      if (file.includes('test')) continue;
      let content = fs.readFileSync(file, 'utf8');
      content = content.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
      if (content.includes('document.cookie')) {
        violations.push(file);
      }
    }

    expect(violations).toEqual([]);
  });

  it('contains zero external CDN scripts or fonts in index.html', () => {
    const indexHtml = fs.readFileSync(indexHtmlPath, 'utf8');
    expect(indexHtml).not.toMatch(/https?:\/\/fonts\.googleapis\.com/i);
    expect(indexHtml).not.toMatch(/https?:\/\/cdnjs\.cloudflare\.com/i);
    expect(indexHtml).not.toMatch(/https?:\/\/cdn\.jsdelivr\.net/i);
    expect(indexHtml).not.toMatch(/https?:\/\/unpkg\.com/i);
  });
});
