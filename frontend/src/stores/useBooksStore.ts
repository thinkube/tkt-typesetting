/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { create } from 'zustand';
import api from '@/lib/axios';

export type BookStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface Book {
  id: string;
  filename: string;
  size_bytes: number;
  formats: string[];
  font: string;
  paper: string;
  lang: string;
  font_size: number;
  chapter_level: number;
  toc: boolean;
  status: BookStatus;
  error?: string | null;
  pages?: number | null;
  seconds?: number | null;
  workflow_name?: string | null;
  logs_url?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface OutputFormat {
  name: string;
  filename: string;
  description: string;
}

export interface FontInfo {
  name: string;
  family: string;
  description: string;
}

export interface PaperInfo {
  name: string;
  label: string;
  width_mm: number;
  height_mm: number;
}

export interface Layout {
  formats: string[];
  font: string;
  paper: string;
  lang: string;
  font_size: number;
  chapter_level: number;
  toc: boolean;
}

export interface Options {
  formats: OutputFormat[];
  fonts: FontInfo[];
  papers: PaperInfo[];
  languages: Record<string, string>;
  font_size_min: number;
  font_size_max: number;
  chapter_levels: number[];
  defaults: Layout;
  max_upload_mb: number;
}

export interface BookInput extends Layout {
  file: File;
}

export const isFinished = (b: Book) => b.status === 'succeeded' || b.status === 'failed';

/** The file name a download is saved under: filename* (RFC 6266) when the server sends it. */
export function downloadName(disposition: string, fallback: string): string {
  const extended = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (extended) return decodeURIComponent(extended[1]);
  const plain = /filename="([^"]+)"/.exec(disposition);
  return plain ? plain[1] : fallback;
}

interface BooksState {
  books: Book[];
  options: Options | null;
  loading: boolean;
  error: string | null;

  fetchOptions: () => Promise<void>;
  fetchBooks: () => Promise<void>;
  createBook: (input: BookInput) => Promise<Book>;
  deleteBook: (id: string) => Promise<void>;
  downloadOutput: (id: string, format: string) => Promise<void>;
}

export const useBooksStore = create<BooksState>((set, get) => ({
  books: [],
  options: null,
  loading: false,
  error: null,

  fetchOptions: async () => {
    const response = await api.get<Options>('/books/options');
    set({ options: response.data });
  },

  fetchBooks: async () => {
    set({ loading: true, error: null });
    try {
      const response = await api.get<Book[]>('/books');
      set({ books: response.data, loading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch books',
        loading: false,
      });
      throw err;
    }
  },

  createBook: async ({ file, formats, font, paper, lang, font_size, chapter_level, toc }) => {
    const body = new FormData();
    body.append('file', file);
    body.append('formats', formats.join(','));
    body.append('font', font);
    body.append('paper', paper);
    body.append('lang', lang);
    body.append('font_size', String(font_size));
    body.append('chapter_level', String(chapter_level));
    body.append('toc', String(toc));
    const response = await api.post<Book>('/books', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 0,
    });
    await get().fetchBooks();
    return response.data;
  },

  deleteBook: async (id) => {
    await api.delete(`/books/${id}`);
    await get().fetchBooks();
  },

  // The API needs the bearer token, so a plain link cannot fetch the file:
  // it is fetched here and handed to the browser as a local object URL.
  downloadOutput: async (id, format) => {
    const response = await api.get<Blob>(`/books/${id}/outputs/${format}`, {
      params: { download: true },
      responseType: 'blob',
    });
    const disposition = String(response.headers['content-disposition'] ?? '');
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = downloadName(disposition, `${id}.${format}`);
    link.click();
    URL.revokeObjectURL(url);
  },
}));
