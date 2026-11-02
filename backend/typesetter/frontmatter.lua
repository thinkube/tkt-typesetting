-- Copyright Alejandro Martínez Corriá and the Thinkube contributors
-- SPDX-License-Identifier: MIT
--
-- The place and date of the front matter (place:, date:) on a page of their
-- own after the title page, in italics and set right, as book.typst sets
-- them in the PDF; the title page then shows no date.
--
-- Word: three paragraphs, each starting a page. The first and the third are
-- empty, so the place and date fall on a recto with blank pages around it and
-- what follows starts on a recto; the second has space before it so the line
-- sits at a fifth of the page's height (metadata place-space-before, in
-- twentieths of a point, from typesetter/run.py).
-- EPUB: a div with the class "place-date", which the stylesheet sets on a
-- page of its own.

local function escape_xml(text)
  return (text:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"))
end

local function page_break(content)
  return pandoc.RawBlock("openxml", "<w:p><w:pPr><w:pageBreakBefore/></w:pPr>" .. (content or "") .. "</w:p>")
end

function Pandoc(doc)
  local place = doc.meta.place and pandoc.utils.stringify(doc.meta.place) or nil
  local date = doc.meta.date and pandoc.utils.stringify(doc.meta.date) or nil
  if not place and not date then
    return nil
  end
  local line = (place and date) and (place .. ", " .. date) or place or date

  local front
  if FORMAT:match("docx") then
    local before = pandoc.utils.stringify(doc.meta["place-space-before"])
    front = {
      page_break(),
      pandoc.RawBlock("openxml",
        "<w:p><w:pPr><w:pageBreakBefore/><w:spacing w:before=\"" .. before .. "\"/>"
        .. "<w:jc w:val=\"right\"/></w:pPr><w:r><w:rPr><w:i/></w:rPr><w:t xml:space=\"preserve\">"
        .. escape_xml(line) .. "</w:t></w:r></w:p>"),
      page_break(),
    }
  else
    front = { pandoc.Div({ pandoc.Para({ pandoc.Emph({ pandoc.Str(line) }) }) }, pandoc.Attr("", { "place-date" })) }
  end
  for i = #front, 1, -1 do
    doc.blocks:insert(1, front[i])
  end
  doc.meta.date = nil
  doc.meta.place = nil
  return doc
end
