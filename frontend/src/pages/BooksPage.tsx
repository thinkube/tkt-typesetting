/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { useEffect, useState } from 'react';
import { Download, ExternalLink, Loader2, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { TkBadge, TkButton } from 'thinkube-style/components/buttons-badges';
import { TkErrorAlert, TkInfoAlert } from 'thinkube-style/components/feedback';
import { TkControlledConfirmDialog } from 'thinkube-style/components/modals-overlays';
import {
  TkTable,
  TkTableBody,
  TkTableCell,
  TkTableHead,
  TkTableHeader,
  TkTableRow,
} from 'thinkube-style/components/tables';
import { TkPageWrapper } from 'thinkube-style/components/utilities';
import { NewBookCard } from '@/components/NewBookCard';
import { isFinished, useBooksStore, type Book } from '@/stores/useBooksStore';

// While a book is being typeset, the list is read again at this interval.
export const POLL_MS = 5000;

const STATUS_BADGE = {
  queued: 'pending',
  running: 'active',
  succeeded: 'healthy',
  failed: 'unhealthy',
} as const;

export default function BooksPage() {
  const { t, i18n } = useTranslation();
  const { books, options, loading, fetchOptions, fetchBooks, deleteBook, downloadOutput } = useBooksStore();
  const [toDelete, setToDelete] = useState<Book | null>(null);

  useEffect(() => {
    fetchOptions().catch(() => toast.error(t('books.optionsFailed')));
    fetchBooks().catch(() => toast.error(t('books.loadFailed')));
  }, [fetchOptions, fetchBooks, t]);

  const anyRunning = books.some((b) => !isFinished(b));
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => {
      fetchBooks().catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [anyRunning, fetchBooks]);

  const confirmDelete = async () => {
    if (!toDelete) return;
    try {
      await deleteBook(toDelete.id);
      toast.success(t('books.deleted'));
    } catch {
      toast.error(t('books.deleteFailed'));
    } finally {
      setToDelete(null);
    }
  };

  const download = (book: Book, format: string) =>
    downloadOutput(book.id, format).catch(() => toast.error(t('books.downloadFailed')));

  const formatDate = (value: string) => new Date(value + 'Z').toLocaleString(i18n.resolvedLanguage);
  const fontFamily = (name: string) => options?.fonts.find((f) => f.name === name)?.family ?? name;
  const paperLabel = (name: string) => options?.papers.find((p) => p.name === name)?.label ?? name;

  return (
    <TkPageWrapper>
      <div>
        <h1 className="text-2xl font-bold">{t('books.title')}</h1>
        <p className="text-muted-foreground mt-1">{t('books.subtitle')}</p>
      </div>

      {options && <NewBookCard options={options} />}

      <h2 className="text-xl font-semibold">{t('books.listTitle')}</h2>
      {loading && books.length === 0 ? (
        <div className="flex justify-center py-12">
          <Loader2 className="text-primary h-8 w-8 animate-spin" />
        </div>
      ) : books.length === 0 ? (
        <TkInfoAlert>{t('books.empty')}</TkInfoAlert>
      ) : (
        <TkTable>
          <TkTableHeader>
            <TkTableRow>
              <TkTableHead>{t('books.table.manuscript')}</TkTableHead>
              <TkTableHead>{t('books.table.layout')}</TkTableHead>
              <TkTableHead>{t('books.table.status')}</TkTableHead>
              <TkTableHead>{t('books.table.outputs')}</TkTableHead>
              <TkTableHead />
            </TkTableRow>
          </TkTableHeader>
          <TkTableBody>
            {books.map((b) => (
              <TkTableRow key={b.id} data-testid="book-row">
                <TkTableCell>
                  <div className="font-medium">{b.filename}</div>
                  <div className="text-muted-foreground text-xs">{formatDate(b.created_at)}</div>
                </TkTableCell>
                <TkTableCell>
                  <div>{fontFamily(b.font)}</div>
                  <div className="text-muted-foreground text-xs">
                    {paperLabel(b.paper)} · {b.font_size} pt · {b.lang}
                  </div>
                </TkTableCell>
                <TkTableCell>
                  <TkBadge status={STATUS_BADGE[b.status]}>{t(`books.status.${b.status}`)}</TkBadge>
                  {b.status === 'succeeded' && (
                    <div className="text-muted-foreground mt-1 text-xs">
                      {b.pages != null
                        ? t('books.pagesIn', { pages: b.pages, seconds: b.seconds })
                        : t('books.doneIn', { seconds: b.seconds })}
                    </div>
                  )}
                  {b.status === 'failed' && b.error && <TkErrorAlert className="mt-2">{b.error}</TkErrorAlert>}
                </TkTableCell>
                <TkTableCell>
                  <div className="flex flex-wrap gap-1">
                    {b.formats.map((format) => (
                      <TkButton
                        key={format}
                        size="sm"
                        intent="secondary"
                        disabled={b.status !== 'succeeded'}
                        onClick={() => download(b, format)}
                      >
                        <Download className="h-3 w-3" />
                        {t(`books.formatNames.${format}`)}
                      </TkButton>
                    ))}
                  </div>
                </TkTableCell>
                <TkTableCell>
                  <div className="flex justify-end gap-1">
                    {b.logs_url && (
                      <TkButton asChild size="icon" intent="ghost" title={t('books.logs')}>
                        <a href={b.logs_url} target="_blank" rel="noreferrer" aria-label={t('books.logs')}>
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </TkButton>
                    )}
                    <TkButton size="icon" intent="ghost" aria-label={t('common.delete')} onClick={() => setToDelete(b)}>
                      <Trash2 className="h-4 w-4" />
                    </TkButton>
                  </div>
                </TkTableCell>
              </TkTableRow>
            ))}
          </TkTableBody>
        </TkTable>
      )}

      <TkControlledConfirmDialog
        open={!!toDelete}
        onOpenChange={(open) => !open && setToDelete(null)}
        title={t('books.confirmDeleteTitle')}
        description={t('books.confirmDelete', { name: toDelete?.filename })}
        confirmText={t('common.delete')}
        cancelText={t('common.cancel')}
        variant="destructive"
        onConfirm={confirmDelete}
      />
    </TkPageWrapper>
  );
}
