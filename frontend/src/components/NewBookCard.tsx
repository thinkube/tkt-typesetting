/*
 * Copyright Alejandro Martínez Corriá and the Thinkube contributors
 * SPDX-License-Identifier: MIT
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { isAxiosError } from 'axios';
import { TkLoadingButton } from 'thinkube-style/components/buttons-badges';
import {
  TkCard,
  TkCardContent,
  TkCardDescription,
  TkCardHeader,
  TkCardTitle,
} from 'thinkube-style/components/cards-data';
import {
  TkCheckbox,
  TkDropZone,
  TkInput,
  TkLabel,
  TkRadioGroup,
  TkRadioGroupItem,
  TkSelect,
  TkSelectContent,
  TkSelectItem,
  TkSelectTrigger,
  TkSelectValue,
} from 'thinkube-style/components/forms-inputs';
import { TkWarningAlert } from 'thinkube-style/components/feedback';
import { useBooksStore, type Layout, type Options } from '@/stores/useBooksStore';

const MANUSCRIPT_TYPES = '.md,.markdown,.txt';

export function NewBookCard({ options }: { options: Options }) {
  const { t } = useTranslation();
  const createBook = useBooksStore((s) => s.createBook);
  const [files, setFiles] = useState<File[]>([]);
  const [layout, setLayout] = useState<Layout>(options.defaults);
  const [submitting, setSubmitting] = useState(false);

  const update = (change: Partial<Layout>) => setLayout((current) => ({ ...current, ...change }));

  const toggleFormat = (name: string, checked: boolean) =>
    update({
      formats: checked ? [...layout.formats, name] : layout.formats.filter((f) => f !== name),
    });

  const tooLarge = files.length > 0 && files[0].size > options.max_upload_mb * 1024 * 1024;
  const sizeOk =
    Number.isFinite(layout.font_size) &&
    layout.font_size >= options.font_size_min &&
    layout.font_size <= options.font_size_max;
  const canSubmit = files.length === 1 && layout.formats.length > 0 && !tooLarge && sizeOk;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      // Formats in the order the API lists them.
      const formats = options.formats.map((f) => f.name).filter((n) => layout.formats.includes(n));
      await createBook({ ...layout, formats, file: files[0] });
      toast.success(t('books.started', { name: files[0].name }));
      setFiles([]);
    } catch (err) {
      const detail = isAxiosError(err) ? err.response?.data?.detail : null;
      toast.error(typeof detail === 'string' ? detail : t('books.startFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <TkCard>
      <TkCardHeader>
        <TkCardTitle>{t('books.newTitle')}</TkCardTitle>
        <TkCardDescription>{t('books.newSubtitle', { mb: options.max_upload_mb })}</TkCardDescription>
      </TkCardHeader>
      <TkCardContent className="space-y-6">
        <TkDropZone
          label={t('books.manuscript')}
          accept={MANUSCRIPT_TYPES}
          files={files}
          onFilesChange={setFiles}
          required
        />
        {tooLarge && <TkWarningAlert>{t('books.tooLarge', { mb: options.max_upload_mb })}</TkWarningAlert>}

        <div className="grid gap-6 md:grid-cols-3">
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">{t('books.formats')}</legend>
            {options.formats.map((f) => (
              <div key={f.name} className="flex items-start gap-2">
                <TkCheckbox
                  id={`format-${f.name}`}
                  checked={layout.formats.includes(f.name)}
                  onCheckedChange={(checked) => toggleFormat(f.name, checked === true)}
                />
                <TkLabel htmlFor={`format-${f.name}`} className="grid gap-1 font-normal">
                  <span className="font-medium">{t(`books.formatNames.${f.name}`)}</span>
                  <span className="text-muted-foreground text-xs">{f.description}</span>
                </TkLabel>
              </div>
            ))}
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">{t('books.font')}</legend>
            <TkRadioGroup value={layout.font} onValueChange={(font) => update({ font })}>
              {options.fonts.map((f) => (
                <div key={f.name} className="flex items-start gap-2">
                  <TkRadioGroupItem id={`font-${f.name}`} value={f.name} />
                  <TkLabel htmlFor={`font-${f.name}`} className="grid gap-1 font-normal">
                    <span className="font-medium">{f.family}</span>
                    <span className="text-muted-foreground text-xs">{f.description}</span>
                  </TkLabel>
                </div>
              ))}
            </TkRadioGroup>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">{t('books.paper')}</legend>
            <TkRadioGroup value={layout.paper} onValueChange={(paper) => update({ paper })}>
              {options.papers.map((p) => (
                <div key={p.name} className="flex items-center gap-2">
                  <TkRadioGroupItem id={`paper-${p.name}`} value={p.name} />
                  <TkLabel htmlFor={`paper-${p.name}`} className="font-normal">
                    {p.label}
                  </TkLabel>
                </div>
              ))}
            </TkRadioGroup>
          </fieldset>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <div className="space-y-2">
            <TkLabel htmlFor="book-lang">{t('books.language')}</TkLabel>
            <TkSelect value={layout.lang} onValueChange={(lang) => update({ lang })}>
              <TkSelectTrigger id="book-lang" aria-label={t('books.language')}>
                <TkSelectValue />
              </TkSelectTrigger>
              <TkSelectContent>
                {Object.entries(options.languages).map(([code, name]) => (
                  <TkSelectItem key={code} value={code}>
                    {name}
                  </TkSelectItem>
                ))}
              </TkSelectContent>
            </TkSelect>
            <p className="text-muted-foreground text-xs">{t('books.languageHelp')}</p>
          </div>

          <div className="space-y-2">
            <TkLabel htmlFor="book-font-size">{t('books.fontSize')}</TkLabel>
            <TkInput
              id="book-font-size"
              type="number"
              step={0.5}
              min={options.font_size_min}
              max={options.font_size_max}
              value={Number.isFinite(layout.font_size) ? layout.font_size : ''}
              onChange={(e) => update({ font_size: e.target.valueAsNumber })}
            />
            {!sizeOk && (
              <TkWarningAlert>
                {t('books.fontSizeRange', { min: options.font_size_min, max: options.font_size_max })}
              </TkWarningAlert>
            )}
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">{t('books.chapterLevel')}</legend>
            <TkRadioGroup
              value={String(layout.chapter_level)}
              onValueChange={(value) => update({ chapter_level: Number(value) })}
              className="flex gap-4"
            >
              {options.chapter_levels.map((level) => (
                <div key={level} className="flex items-center gap-2">
                  <TkRadioGroupItem id={`chapter-level-${level}`} value={String(level)} />
                  <TkLabel htmlFor={`chapter-level-${level}`} className="font-mono font-normal">
                    {'#'.repeat(level)}
                  </TkLabel>
                </div>
              ))}
            </TkRadioGroup>
            <p className="text-muted-foreground text-xs">{t('books.chapterLevelHelp')}</p>
            <div className="flex items-center gap-2">
              <TkCheckbox
                id="book-toc"
                checked={layout.toc}
                onCheckedChange={(checked) => update({ toc: checked === true })}
              />
              <TkLabel htmlFor="book-toc" className="font-normal">
                {t('books.toc')}
              </TkLabel>
            </div>
          </fieldset>
        </div>

        <TkLoadingButton onClick={submit} disabled={!canSubmit} loading={submitting}>
          {t('books.typeset')}
        </TkLoadingButton>
      </TkCardContent>
    </TkCard>
  );
}
