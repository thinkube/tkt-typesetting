-- Copyright Alejandro Martínez Corriá and the Thinkube contributors
-- SPDX-License-Identifier: MIT
--
-- Scene breaks marked by blank lines. typesetter/run.py turns two or more
-- blank lines in a row in the manuscript into an empty div with the class
-- "scene-space"; this filter sets it for each output: #scene-space in Typst
-- (book.typst), an empty div the stylesheet sizes in EPUB, an empty
-- paragraph in Word. A space next to a heading, at the start or at the end
-- says nothing the heading or the page does not, and is dropped; dropping it
-- after a heading also keeps the chapter's first paragraph first, for
-- dropcap.lua, which runs after this filter.

local function is_space(block)
  return block and block.t == "Div" and block.classes:includes("scene-space")
end

function Pandoc(doc)
  local blocks = pandoc.Blocks({})
  for i, block in ipairs(doc.blocks) do
    if is_space(block) then
      local next_block = doc.blocks[i + 1]
      local previous = blocks[#blocks]
      if next_block and next_block.t ~= "Header" and not is_space(next_block)
          and previous and previous.t ~= "Header" then
        if FORMAT:match("typst") then
          blocks:insert(pandoc.RawBlock("typst", "#scene-space"))
        elseif FORMAT:match("docx") then
          blocks:insert(pandoc.RawBlock("openxml", "<w:p/>"))
        else
          blocks:insert(block)
        end
      end
    else
      blocks:insert(block)
    end
  end
  doc.blocks = blocks
  return doc
end
