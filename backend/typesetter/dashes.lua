-- Copyright Alejandro Martínez Corriá and the Thinkube contributors
-- SPDX-License-Identifier: MIT
--
-- An em dash stays with the word it touches. Line breaking allows a break
-- on either side of an em dash, so a closing dash ("—dice Marisa—.") could
-- start a line and an opening one ("—dice") end one. A word joiner (U+2060,
-- invisible) between the dash and the character it touches removes that
-- break; a dash with a space on one side still breaks at the space.

local DASH = "—"
local WORD_JOINER = "\u{2060}"

function Str(el)
  local text = el.text
  if not text:find(DASH, 1, true) then
    return nil
  end
  -- [^%s] is one byte: the joiner goes after the last byte of the character
  -- before the dash, or before the first byte of the one after it.
  text = text:gsub("([^%s])" .. DASH, "%1" .. WORD_JOINER .. DASH)
  text = text:gsub(DASH .. "([^%s])", DASH .. WORD_JOINER .. "%1")
  return pandoc.Str(text)
end
