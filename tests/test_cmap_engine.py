import unittest

from cmap_engine import parse_mappings, patch_cmap


def consume_mapping_budget(total_entries, span):
    if span <= 0:
        raise ValueError('invalid span')
    return total_entries + span


class CMapEngineTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
