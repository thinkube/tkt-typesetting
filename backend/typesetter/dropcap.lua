-- Copyright Alejandro Martínez Corriá and the Thinkube contributors
-- SPDX-License-Identifier: MIT
--
-- Opens each chapter with a dropped capital: the first paragraph after a
-- heading at the chapter level (metadata chapter-level). For Typst it is
-- wrapped in #dropcap(...)[...], which book.typst imports from droplet; for
-- EPUB it goes in a div with the class "opening", which the stylesheet sets.
--
-- A paragraph that starts with anything but a letter or a digit (a dialogue
-- dash, quotation marks, an opening question mark) is left as it is: a
-- dropped dash or quote is not a capital.

local DROPCAP = "#dropcap(height: 3, gap: 0.25em)["
-- book.typst's paragraph indent, for the paragraph after the dropped capital.
local INDENT = "#h(paragraph-indent)"

-- The first character of the text, as UTF-8.
local function first_character(text)
  return text:match("^[\1-\127\194-\244][\128-\191]*")
end

local function starts_with_letter(para)
  local c = first_character(pandoc.utils.stringify(para))
  if not c then
    return false
  end
  if #c == 1 then
    return c:match("%w") ~= nil
  end
  -- Two-byte UTF-8 from U+00C0 on: the accented Latin letters (Á, É, Ñ, Ç…).
  local b1, b2 = c:byte(1, 2)
  return #c == 2 and (b1 > 0xC3 or (b1 == 0xC3 and b2 ~= 0x97 and b2 ~= 0xB7))
end

function Pandoc(doc)
  local level = tonumber(pandoc.utils.stringify(doc.meta["chapter-level"] or "1"))
  local typst = FORMAT:match("typst") ~= nil
  local after_chapter = false
  for i, block in ipairs(doc.blocks) do
    if block.t == "Header" then
      after_chapter = block.level == level
    elseif after_chapter then
      if block.t == "Para" and starts_with_letter(block) then
        if typst then
          block.content:insert(1, pandoc.RawInline("typst", DROPCAP))
          block.content:insert(pandoc.RawInline("typst", "]"))
          local next_block = doc.blocks[i + 1]
          if next_block and next_block.t == "Para" then
            next_block.content:insert(1, pandoc.RawInline("typst", INDENT))
          end
        else
          -- HTML-based output (EPUB): the stylesheet sets div.opening's first letter.
          doc.blocks[i] = pandoc.Div({ block }, pandoc.Attr("", { "opening" }))
        end
      end
      after_chapter = false
    end
  end
  return doc
end
