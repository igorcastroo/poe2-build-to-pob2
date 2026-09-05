import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from converter import (convert, ConversionError, decode, encode, passive_map,
                       stage_key, validate_roundtrip, write_outputs, DEFAULT_CATALOG)


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.catalog = json.loads(DEFAULT_CATALOG.read_text(encoding='utf-8'))
        self.passive = next(iter(self.catalog['passives']))
        self.gem = next(iter(self.catalog['gems']))

    def file(self, name, data):
        p = self.base / (name + '.build')
        p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return p

    def build(self, **kwargs):
        return dict(name='Test', ascendancy='Monk1', passives=[self.passive], **kwargs)

    def test_stages_and_roundtrip(self):
        files = [self.file(n, self.build(description='A & B <red>{ação}\nLinha 2')) for n in ['Mirror Tier', 'Act 2', 'Act 1']]
        xml, code, report = convert(files)
        root = validate_roundtrip(xml, code, 3)
        self.assertEqual([s.get('title') for s in root.findall('Tree/Spec')], ['Act 1', 'Act 2', 'Mirror Tier'])
        self.assertIn('ação', root.find('Notes').text)
        self.assertEqual(decode(code.rstrip('=')), xml)
        self.assertTrue(report['roundtrip_ok'])

    def test_order(self):
        names = ['Mirror Tier', 'Late Endgame', 'High Budget', 'Mid Endgame', 'Interlude 3', 'Act 4', 'Early Endgame', 'Act 1', 'Interlude 1']
        self.assertEqual(sorted(names, key=stage_key), ['Act 1', 'Act 4', 'Interlude 1', 'Interlude 3', 'Early Endgame', 'Mid Endgame', 'Late Endgame', 'High Budget', 'Mirror Tier'])

    def test_manual_order_and_duplicate_inputs(self):
        a, b = [self.file(n, self.build()) for n in ['Act 2', 'Act 1']]
        _, _, report = convert([a, b, a], manual_order=True)
        self.assertEqual([s['title'] for s in report['stages']], ['Act 2', 'Act 1'])

    def test_empty_corrupt_and_bad_schema(self):
        good = self.file('Act 1', self.build())
        empty = self.file('Empty', {})
        bad = self.file('Wrong', {'passives': 'bad'})
        corrupt = self.base / 'corrupt.build'
        corrupt.write_text('{', encoding='utf-8')
        _, _, report = convert([good, empty, bad, corrupt])
        self.assertEqual(len(report['stages']), 1)
        self.assertEqual(len(report['skipped']), 3)
        with self.assertRaises(ConversionError):
            convert([empty, corrupt])

    def test_unmapped_is_strict(self):
        path = self.file('Act 1', {'passives': ['invented'], 'ascendancy': 'Monk1'})
        with self.assertRaises(ConversionError) as cm:
            convert([path])
        self.assertEqual(cm.exception.report['stages'][0]['unmapped_passives'], ['invented'])
        xml, code, report = convert([path], allow_partial=True)
        self.assertEqual(validate_roundtrip(xml, code).find('Tree/Spec').get('nodes'), '')
        self.assertTrue(report['partial'])

    def test_weapons_notes_and_gems(self):
        path = self.file('Act 1', {'ascendancy': 'Monk1',
            'passives': [{'id': self.passive, 'weapon_set': 2, 'additional_text': 'hello\nworld'}],
            'skills': [{'id': self.gem, 'level_interval': [20, 50], 'additional_text': 'gem note',
                        'support_skills': [self.gem]}]})
        xml, code, _ = convert([path])
        root = validate_roundtrip(xml, code)
        self.assertEqual(root.find('Tree/Spec/WeaponSet2').get('nodes'), str(self.catalog['passives'][self.passive]))
        self.assertEqual(root.find('Tree/Spec/Notes/Note').text, 'hello\nworld')
        gems = root.findall('Skills/SkillSet/Skill/Gem')
        self.assertEqual(len(gems), 2)
        self.assertIsNone(gems[0].get('level'))
        self.assertEqual(gems[0].get('note'), 'gem note')

    def test_inventory_hints_and_raw(self):
        raw = 'Rarity: NORMAL\nQuarterstaff\n'
        path = self.file('Act 1', self.build(inventory_slots=[
            {'inventory_id': 'Weapon1', 'raw_text': raw},
            {'inventory_id': 'Ring1', 'unique_name': "Kalandra's Touch", 'additional_text': 'hint'},
            {'inventory_id': 'Flask1', 'slot_x': 1, 'additional_text': 'mana'}]))
        xml, code, report = convert([path])
        root = validate_roundtrip(xml, code)
        self.assertEqual(len(root.findall('Items/Item')), 1)
        self.assertEqual(root.find('Items/Item').text, raw)
        slots = {s.get('name'): s for s in root.findall('Items/ItemSet/Slot')}
        self.assertEqual(slots['Ring 1'].get('itemId'), '0')
        self.assertEqual(slots['Flask 2'].get('note'), 'mana')
        self.assertEqual(len(report['stages'][0]['warnings']), 2)

    def test_map_formats_and_conflicts(self):
        self.assertEqual(passive_map([{'Id': 'a', 'PassiveSkillsHash': 12}]), {'a': 12})
        self.assertEqual(passive_map({'a': {'PassiveSkillsHash': '12'}}), {'a': 12})
        for data in ({'a': True}, {'a': -1}, {'a': 65536}, {'a': 1.5}, {},
                     [{'Id': 'a', 'PassiveSkillsHash': 1}, {'Id': 'a', 'PassiveSkillsHash': 2}]):
            with self.assertRaises(ValueError):
                passive_map(data)

    def test_no_class_guess_and_mixed_classes(self):
        a = self.file('Act 1', {'passives': [self.passive]})
        with self.assertRaises(ConversionError):
            convert([a])
        b = self.file('Act 2', self.build())
        self.assertEqual(len(convert([a, b])[2]['stages']), 2)
        c = self.file('Act 3', {'passives': [self.passive], 'ascendancy': 'Warrior1'})
        with self.assertRaises(ConversionError):
            convert([b, c])

    def test_unknown_gem_and_slot(self):
        path = self.file('Act 1', self.build(skills=['unknown'], inventory_slots=[{'inventory_id': 'unknown'}]))
        with self.assertRaises(ConversionError):
            convert([path])
        xml, code, report = convert([path], allow_partial=True)
        self.assertIsNone(validate_roundtrip(xml, code).find('Skills/SkillSet/Skill'))
        self.assertEqual(report['stages'][0]['unmapped_slots'], ['unknown:0'])

    def test_xml_control_and_bom(self):
        bad = self.file('Bad', self.build(description='bad\x01'))
        with self.assertRaises(ConversionError):
            convert([bad])
        good = self.file('Good', self.build())
        good.write_bytes(b'\xef\xbb\xbf' + good.read_bytes())
        self.assertTrue(convert([good])[2]['roundtrip_ok'])

    def test_invalid_code_and_no_overwrite(self):
        with self.assertRaises(ValueError):
            decode('not-a-code!')
        result = convert([self.file('Act 1', self.build())])
        with self.assertRaises(ValueError):
            validate_roundtrip(result[0] + b' ', result[1])
        paths = write_outputs(self.base / 'merged', *result)
        self.assertTrue(all(p.exists() for p in paths))
        with self.assertRaises(ConversionError):
            write_outputs(self.base / 'merged', *result)

    def test_wrong_version(self):
        with self.assertRaises(ConversionError):
            convert([self.file('Act 1', self.build())], tree_version='0_4')


if __name__ == '__main__':
    unittest.main()
