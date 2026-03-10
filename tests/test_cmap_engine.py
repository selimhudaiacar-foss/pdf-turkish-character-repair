import unittest

from cmap_engine import (
    _apply_encoding_differences,
    build_cid_to_unicode_map,
    build_simple_font_code_to_unicode_map,
    find_fixes,
    find_font_cmap_fixes,
    parse_mappings,
    patch_cmap,
)


def consume_mapping_budget(total_entries, span):
    if span <= 0:
        raise ValueError('invalid span')
    return total_entries + span


class CMapEngineTests(unittest.TestCase):
    def test_build_cid_to_unicode_map_prefers_semantic_letters(self):
        unicode_to_gid = {
            0x005F: 5,
            0x015F: 5,
            0x0031: 6,
            0x0131: 6,
            0x001F: 7,
            0x011F: 7,
        }
        cid_to_gid = {
            0x0010: 5,
            0x0011: 6,
            0x0012: 7,
        }

        cid_to_unicode = build_cid_to_unicode_map(unicode_to_gid, cid_to_gid)

        self.assertEqual(cid_to_unicode[0x0010], 0x015F)
        self.assertEqual(cid_to_unicode[0x0011], 0x0131)
        self.assertEqual(cid_to_unicode[0x0012], 0x011F)

    def test_build_simple_font_code_to_unicode_map_prefers_font_cmap_result(self):
        unicode_to_gid = {
            0x005F: 12,
            0x015F: 12,
            0x0031: 18,
            0x0131: 18,
        }
        code_to_unicode = {
            95: 0x005F,
            49: 0x0031,
        }
        code_to_glyph_name = {
            95: 'underscore',
            49: 'one',
        }
        glyph_name_to_gid = {
            'underscore': 12,
            'one': 18,
        }

        code_to_unicode_map = build_simple_font_code_to_unicode_map(
            unicode_to_gid,
            code_to_unicode=code_to_unicode,
            code_to_glyph_name=code_to_glyph_name,
            glyph_name_to_gid=glyph_name_to_gid,
        )

        self.assertEqual(code_to_unicode_map[95], 0x015F)
        self.assertEqual(code_to_unicode_map[49], 0x0131)

    def test_apply_encoding_differences_overrides_previous_entries(self):
        code_to_unicode = {65: ord('A')}
        code_to_glyph_name = {65: 'A'}

        _apply_encoding_differences(code_to_unicode, code_to_glyph_name, [65, '/Gbreve', '/dotlessi'])

        self.assertEqual(code_to_glyph_name[65], 'Gbreve')
        self.assertEqual(code_to_unicode[65], 0x011E)
        self.assertEqual(code_to_glyph_name[66], 'dotlessi')
        self.assertEqual(code_to_unicode[66], 0x0131)

    def test_find_font_cmap_fixes_only_replaces_lower_ranked_unicode(self):
        mappings = {
            0x0010: 0x005F,
            0x0011: 0x0031,
            0x0012: 0x001F,
            0x0013: 0x0041,
        }
        cid_to_unicode = {
            0x0010: 0x015F,
            0x0011: 0x0131,
            0x0012: 0x011F,
            0x0013: 0x0391,
        }

        fixes = find_font_cmap_fixes(mappings, cid_to_unicode)

        self.assertEqual(fixes[0x0010], (0x005F, 0x015F))
        self.assertEqual(fixes[0x0011], (0x0031, 0x0131))
        self.assertEqual(fixes[0x0012], (0x001F, 0x011F))
        self.assertNotIn(0x0013, fixes)

    def test_parse_mappings_accepts_whitespace_and_array_ranges(self):
        cmap = '''
        2 beginbfrange
        <0001> <0003>
        <00A0>
        <0010> <0012> [ <00B0> <00B1>
        <00B2> ]
        endbfrange
        1 beginbfchar
        <0020>
        <00C0>
        endbfchar
        '''

        mappings = parse_mappings(cmap, consume_mapping_budget)

        self.assertEqual(mappings[0x0001], 0x00A0)
        self.assertEqual(mappings[0x0003], 0x00A2)
        self.assertEqual(mappings[0x0010], 0x00B0)
        self.assertEqual(mappings[0x0012], 0x00B2)
        self.assertEqual(mappings[0x0020], 0x00C0)

    def test_parse_mappings_respects_block_order(self):
        cmap = '''
        1 beginbfrange
        <0001> <0001> <0031>
        endbfrange
        1 beginbfchar
        <0001> <0131>
        endbfchar
        '''

        mappings = parse_mappings(cmap, consume_mapping_budget)

        self.assertEqual(mappings[0x0001], 0x0131)

    def test_parse_mappings_skips_unterminated_blocks(self):
        cmap = '''
        1 beginbfrange
        <0001> <0002> <0030>
        1 beginbfchar
        <0005> <0041>
        endbfchar
        '''

        mappings = parse_mappings(cmap, consume_mapping_budget)

        self.assertNotIn(0x0001, mappings)
        self.assertEqual(mappings[0x0005], 0x0041)

    def test_patch_cmap_updates_bfchar_entries(self):
        cmap = '''
        1 beginbfchar
        <0041> <0031>
        endbfchar
        '''

        patched, count = patch_cmap(cmap, {0x0041: (0x0031, 0x0131)})

        self.assertEqual(count, 1)
        self.assertIn('<0041> <0131>', patched)

    def test_patch_cmap_splits_sequential_ranges_when_needed(self):
        cmap = '''
        1 beginbfrange
        <0010> <0012> <0030>
        endbfrange
        '''

        patched, count = patch_cmap(cmap, {0x0011: (0x0031, 0x0131)})

        self.assertEqual(count, 1)
        self.assertIn('<0010> <0012> [<0030> <0131> <0032>]', patched)

    def test_find_fixes_keeps_heuristic_fallback_without_font_data(self):
        fixes = find_fixes({0x0001: 0x001F})

        self.assertEqual(fixes[0x0001], (0x001F, 0x011F))


if __name__ == '__main__':
    unittest.main()
