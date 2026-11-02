/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BooksPage, { POLL_MS } from '../BooksPage';
import api from '@/lib/axios';
import { downloadName, useBooksStore, type Book, type Options } from '@/stores/useBooksStore';

vi.mock('@/lib/axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const options: Options = {
  formats: [
    { name: 'pdf', filename: 'book.pdf', description: 'Print-ready PDF, typeset with Typst' },
    { name: 'epub', filename: 'book.epub', description: 'EPUB 3 e-book with the face embedded' },
    { name: 'docx', filename: 'book.docx', description: 'Word document in the chosen face' },
  ],
  fonts: [
    { name: 'eb-garamond', family: 'EB Garamond', description: 'Classic Garamond' },
    { name: 'crimson-pro', family: 'Crimson Pro', description: 'Old-style book face' },
    { name: 'libertinus', family: 'Libertinus Serif', description: 'Clear and sober' },
  ],
  papers: [
    { name: '15x23cm', label: '15 × 23 cm, trade paperback', width_mm: 150, height_mm: 230 },
    { name: 'a5', label: 'A5, 14.8 × 21 cm', width_mm: 148, height_mm: 210 },
  ],
  languages: { es: 'Español', en: 'English' },
  font_size_min: 9,
  font_size_max: 14,
  chapter_levels: [1, 2, 3],
  defaults: {
    formats: ['pdf', 'epub', 'docx'],
    font: 'eb-garamond',
    paper: '15x23cm',
    lang: 'es',
    font_size: 11,
    chapter_level: 1,
    toc: false,
  },
  max_upload_mb: 20,
};

const done: Book = {
  id: 'b-1',
  filename: 'No me gusta tu jersey.md',
  size_bytes: 209800,
  formats: ['pdf', 'epub'],
  font: 'eb-garamond',
  paper: '15x23cm',
  lang: 'es',
  font_size: 11,
  chapter_level: 2,
  toc: false,
  status: 'succeeded',
  pages: 312,
  seconds: 6.4,
  workflow_name: 'typesetting-typeset-abcde',
  logs_url: 'https://argo.example.com/workflows/typesetting/typesetting-typeset-abcde',
  created_at: '2026-11-02T18:40:00',
  finished_at: '2026-11-02T18:40:10',
};

function serve(books: Book[] | (() => Book[])) {
  mockedApi.get.mockImplementation(async (url: string) => {
    if (url === '/books/options') return { data: options };
    if (url === '/books') return { data: typeof books === 'function' ? books() : books };
    if (url.startsWith('/books/b-1/outputs/')) {
      return {
        data: new Blob(['%PDF']),
        headers: { 'content-disposition': 'attachment; filename="No me gusta tu jersey.pdf"' },
      };
    }
    throw new Error(`unexpected GET ${url}`);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useBooksStore.setState({ books: [], options: null, loading: false, error: null });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('BooksPage', () => {
  it('shows the empty state and the form with its defaults', async () => {
    serve([]);
    render(<BooksPage />);

    expect(await screen.findByText('No books yet. Upload a manuscript above.')).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: /EB Garamond/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: /15 × 23 cm/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /EPUB/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Table of contents' })).not.toBeChecked();
    expect(screen.getByLabelText('Text size (pt)')).toHaveValue(11);
    expect(screen.getByRole('button', { name: 'Typeset' })).toBeDisabled();
  });

  it('uploads a manuscript with the chosen layout', async () => {
    const user = userEvent.setup();
    serve([]);
    mockedApi.post.mockResolvedValue({ data: { ...done, status: 'queued' } });
    const { container } = render(<BooksPage />);
    await screen.findByRole('radio', { name: /Crimson Pro/ });

    const manuscript = new File(['# Capítulo 1\n'], 'novela.md', { type: 'text/markdown' });
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, manuscript);
    await user.click(screen.getByRole('radio', { name: /Crimson Pro/ }));
    await user.click(screen.getByRole('radio', { name: /A5/ }));
    await user.click(screen.getByRole('checkbox', { name: /Word/ }));
    await user.click(screen.getByRole('radio', { name: '##' }));
    await user.click(screen.getByRole('checkbox', { name: 'Table of contents' }));
    const size = screen.getByLabelText('Text size (pt)');
    await user.clear(size);
    await user.type(size, '10.5');
    await user.click(screen.getByRole('button', { name: 'Typeset' }));

    await waitFor(() => expect(mockedApi.post).toHaveBeenCalledTimes(1));
    const [url, body] = mockedApi.post.mock.calls[0] as [string, FormData];
    expect(url).toBe('/books');
    expect(body.get('formats')).toBe('pdf,epub');
    expect(body.get('font')).toBe('crimson-pro');
    expect(body.get('paper')).toBe('a5');
    expect(body.get('lang')).toBe('es');
    expect(body.get('font_size')).toBe('10.5');
    expect(body.get('chapter_level')).toBe('2');
    expect(body.get('toc')).toBe('true');
    expect((body.get('file') as File).name).toBe('novela.md');
  });

  it('blocks a text size outside the range', async () => {
    const user = userEvent.setup();
    serve([]);
    const { container } = render(<BooksPage />);
    await screen.findByRole('radio', { name: /Crimson Pro/ });

    const manuscript = new File(['# Uno\n'], 'novela.md', { type: 'text/markdown' });
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, manuscript);
    const size = screen.getByLabelText('Text size (pt)');
    await user.clear(size);
    await user.type(size, '30');

    expect(screen.getByText('Between 9 and 14 points.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Typeset' })).toBeDisabled();
  });

  it('lists books with their layout and status and downloads an output', async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => 'blob:book');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    serve([done, { ...done, id: 'b-2', filename: 'roto.md', status: 'failed', error: 'typst failed (exit 1)' }]);
    render(<BooksPage />);

    const rows = await screen.findAllByTestId('book-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Done')).toBeInTheDocument();
    expect(within(rows[0]).getByText('312 pages in 6.4 s')).toBeInTheDocument();
    expect(within(rows[0]).getByText('EB Garamond')).toBeInTheDocument();
    expect(within(rows[1]).getByText('typst failed (exit 1)')).toBeInTheDocument();
    expect(within(rows[1]).getByRole('button', { name: 'PDF' })).toBeDisabled();

    await user.click(within(rows[0]).getByRole('button', { name: 'PDF' }));
    await waitFor(() =>
      expect(mockedApi.get).toHaveBeenCalledWith('/books/b-1/outputs/pdf', {
        params: { download: true },
        responseType: 'blob',
      }),
    );
    expect(createObjectURL).toHaveBeenCalled();
  });

  it('reads the list again while a book is being typeset', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let status: Book['status'] = 'running';
    serve(() => [{ ...done, status }]);
    render(<BooksPage />);

    expect(await screen.findByText('Typesetting')).toBeInTheDocument();
    status = 'succeeded';
    await act(async () => {
      vi.advanceTimersByTime(POLL_MS);
    });
    expect(await screen.findByText('Done')).toBeInTheDocument();
  });
});

describe('downloadName', () => {
  it('prefers the UTF-8 name and falls back to the plain one', () => {
    expect(downloadName("attachment; filename=\"Se?ora.pdf\"; filename*=UTF-8''Se%C3%B1ora.pdf", 'x')).toBe(
      'Señora.pdf',
    );
    expect(downloadName('attachment; filename="novela.epub"', 'x')).toBe('novela.epub');
    expect(downloadName('', 'b-1.pdf')).toBe('b-1.pdf');
  });
});
