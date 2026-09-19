# GlyphFuck - IsyMotron CLI banner
#
# Renders the ISYMOTRON wordmark rendered into isymotron.ps1 (tools\isymotron.ps1
# embeds the static output; the CLI never imports glyphfuck at runtime).
#
# Provenance: glyph definitions for O, S, Y, I, N are copied from
# GlyphFuck's examples/openisy.gf (MIT, same author, repository
# "C:\Development\ISyCo Git\GlyphFuck"). M, T, R are new, same 5-row style.
#
# Regenerate:
#   cd "C:\Development\ISyCo Git\GlyphFuck"
#   $env:PYTHONPATH = "src"
#   py -m glyphfuck render "C:\Development\ISyCo Git\IsyMotron\tools\cli-banner.gf"

canvas 53 7 fill " "

glyph I 3 5
  line 0 0 2 0 "#"
  line 1 0 1 4 "#"
  line 0 4 2 4 "#"
end

glyph S 5 5
  line 4 0 0 0 "#"
  line 0 0 0 2 "#"
  line 0 2 4 2 "#"
  line 4 2 4 4 "#"
  line 4 4 0 4 "#"
end

glyph Y 5 5
  line 0 0 2 2 "#"
  line 4 0 2 2 "#"
  line 2 2 2 4 "#"
end

glyph M 5 5
  line 0 0 0 4 "#"
  line 4 0 4 4 "#"
  line 0 0 2 2 "#"
  line 4 0 2 2 "#"
end

glyph O 6 5
  box 0 0 6 5 "#"
  fill 1 1 4 3 " "
end

glyph T 5 5
  line 0 0 4 0 "#"
  line 2 0 2 4 "#"
end

glyph R 5 5
  line 0 0 0 4 "#"
  line 0 0 3 0 "#"
  line 3 0 3 2 "#"
  line 0 2 3 2 "#"
  line 3 2 4 4 "#"
end

glyph N 5 5
  line 0 0 0 4 "#"
  line 0 4 4 0 "#"
  line 4 0 4 4 "#"
end

# Compose ISYMOTRON: I(3)+S(5)+Y(5)+M(5)+O(6)+T(5)+R(5)+O(6)+N(5) + 8 spacing
text "ISYMOTRON" at 0 1 anchor top_left spacing 1

expect width 53
expect height 7
expect text "ISYMOTRON"
expect no_overlap
expect glyphs_distinct I S Y M O T R N

render
