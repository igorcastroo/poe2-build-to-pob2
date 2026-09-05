import unittest

from mobalytics import (MobalyticsImportError, _document_id, _preloaded_state,
                        _variant_ids, _variant_names, validate_guide_url)


class MobalyticsTests(unittest.TestCase):
    def test_url_must_be_public_poe2_guide(self):
        url = 'https://mobalytics.gg/poe-2/builds/example-guide?foo=bar'
        self.assertEqual(validate_guide_url(url), url)
        for value in ('http://mobalytics.gg/poe-2/builds/a',
                      'https://example.com/poe-2/builds/a',
                      'https://mobalytics.gg/poe-2/guides/a',
                      'https://user@mobalytics.gg/poe-2/builds/a'):
            with self.assertRaises(MobalyticsImportError):
                validate_guide_url(value)

    def test_embedded_state_extracts_document_and_variants(self):
        state = {
            'guide': {
                'id': 'b1330f58-4226-4cd8-b374-b9e48285681b',
                'type': 'builds',
                'data': {'buildVariants': {'values': [{'id': 'act-1'}, {'id': 'endgame'}]}},
            },
        }
        html = '<script>window.__PRELOADED_STATE__=' + __import__('json').dumps(state) + ';</script>'
        parsed = _preloaded_state(html)
        self.assertEqual(_document_id(parsed), state['guide']['id'])
        self.assertEqual(_variant_ids(parsed), ['act-1', 'endgame'])

    def test_bad_state_is_rejected(self):
        with self.assertRaises(MobalyticsImportError):
            _preloaded_state('<script>window.__PRELOADED_STATE__={bad};</script>')

    def test_variant_names_come_from_tabs(self):
        html = '<div data-key="act-1"><span>Act 1</span></div>'
        self.assertEqual(_variant_names(html, {'act-1'}), {'act-1': 'Act 1'})


if __name__ == '__main__':
    unittest.main()
