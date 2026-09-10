import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from converter import (convert, ConversionError, decode, encode, passive_map,
                       stage_key, validate_roundtrip, write_outputs, DEFAULT_CATALOG)
from catalog_tools import extract_uniques


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
        self.assertEqual(root.tag, 'PathOfBuilding2')
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

    def test_active_path_selects_matching_stage_sets(self):
        act_1, act_2 = [self.file(name, self.build()) for name in ('Act 1', 'Act 2')]
        xml, code, _ = convert([act_1, act_2], active_path=act_2)
        root = validate_roundtrip(xml, code, 2)
        self.assertEqual(root.find('Tree').get('activeSpec'), '2')
        self.assertEqual(root.find('Skills').get('activeSkillSet'), '2')
        self.assertEqual(root.find('Items').get('activeItemSet'), '2')

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
        self.assertEqual(gems[0].get('level'), '1')
        self.assertEqual(gems[0].get('quality'), '0')
        self.assertEqual(gems[0].get('qualityId'), 'Default')
        self.assertEqual(gems[1].get('level'), '1')
        self.assertEqual(gems[0].get('note'), 'gem note')

    def test_passive_can_be_general_and_in_both_weapon_sets(self):
        path = self.file('Act 1', {'ascendancy': 'Monk1', 'passives': [
            {'id': self.passive},
            {'id': self.passive, 'weapon_set': 1},
            {'id': self.passive, 'weapon_set': 2},
        ]})
        xml, code, _ = convert([path])
        root = validate_roundtrip(xml, code)
        node = str(self.catalog['passives'][self.passive])
        spec = root.find('Tree/Spec')
        self.assertEqual(spec.get('nodes'), node)
        self.assertEqual(spec.find('WeaponSet1').get('nodes'), node)
        self.assertEqual(spec.find('WeaponSet2').get('nodes'), node)

    def test_flatten_weapon_sets_keeps_all_nodes_in_the_main_tree(self):
        other = next(key for key in self.catalog['passives'] if key != self.passive)
        path = self.file('Act 1', {'ascendancy': 'Monk1', 'passives': [
            {'id': self.passive}, {'id': other, 'weapon_set': 1},
        ]})
        xml, code, report = convert([path], flatten_weapon_sets=True)
        root = validate_roundtrip(xml, code)
        spec = root.find('Tree/Spec')
        expected = sorted((self.catalog['passives'][self.passive], self.catalog['passives'][other]))
        self.assertEqual(spec.get('nodes'), ','.join(map(str, expected)))
        self.assertIsNone(spec.find('WeaponSet1'))
        self.assertTrue(report['stages'][0]['warnings'])

    def test_inventory_hints_and_raw(self):
        raw = 'Rarity: NORMAL\nQuarterstaff\n'
        path = self.file('Act 1', self.build(inventory_slots=[
            {'inventory_id': 'Weapon1', 'raw_text': raw},
            {'inventory_id': 'Ring1', 'unique_name': 'Unknown Unique', 'additional_text': 'hint'},
            {'inventory_id': 'Flask1', 'slot_x': 1, 'additional_text': 'mana'}]))
        xml, code, report = convert([path])
        root = validate_roundtrip(xml, code)
        self.assertEqual(len(root.findall('Items/Item')), 1)
        self.assertEqual(root.find('Items/Item').text, raw)
        slots = {s.get('name'): s for s in root.findall('Items/ItemSet/Slot')}
        self.assertEqual(slots['Ring 1'].get('itemId'), '0')
        self.assertEqual(slots['Flask 2'].get('note'), 'mana')
        self.assertEqual(len(report['stages'][0]['warnings']), 2)

    def test_mobalytics_item_suggestions_create_editable_items(self):
        path = self.file('Act 1', self.build(inventory_slots=[
            {'inventory_id': 'Amulet1', 'additional_text': 'Gold Amulet\n1. +9% to all Elemental Resistances'},
            {'inventory_id': 'BodyArmour1', 'unique_name': 'Forgotten Warden'},
        ]))
        xml, code, _ = convert([path])
        root = validate_roundtrip(xml, code)
        items = root.findall('Items/Item')
        self.assertEqual(len(items), 2)
        self.assertIn('Rarity: RARE\nGold Amulet\nGold Amulet', items[0].text)
        self.assertIn('+9% to all Elemental Resistances', items[0].text)
        self.assertTrue(items[1].text.startswith('Rarity: UNIQUE\nForgotten Warden\nPrimal Markings\n'))
        self.assertIn('Spirit', items[1].text)
        self.assertTrue(all(slot.get('itemId') != '0' for slot in root.findall('Items/ItemSet/Slot')))

    def test_unique_name_equips_complete_current_template(self):
        path = self.file('Interludes', self.build(inventory_slots=[
            {'inventory_id': 'Gloves1', 'unique_name': 'Lochtonial Caress'}]))
        xml, code, report = convert([path])
        root = validate_roundtrip(xml, code)
        item = root.find('Items/Item')
        self.assertIsNotNone(item)
        self.assertEqual(root.find('Items/ItemSet/Slot').get('itemId'), item.get('id'))
        for text in ('Rarity: UNIQUE\nLochtonial Caress\nTempered Mitts',
                     'Selected Variant: 2', '{variant:2}+(15-25) to Armour',
                     '{range:0.5}+(40-60) to maximum Life',
                     'Share Charges with Allies in your Presence'):
            self.assertIn(text, item.text)
        self.assertIn('rolls médios', report['stages'][0]['warnings'][0])

    def test_unique_raw_text_takes_precedence(self):
        raw = 'Rarity: UNIQUE\nLochtonial Caress\nTempered Mitts\n+43 to maximum Life'
        path = self.file('Interludes', self.build(inventory_slots=[
            {'inventory_id': 'Gloves1', 'unique_name': 'Lochtonial Caress', 'raw_text': raw}]))
        xml, code, _ = convert([path])
        self.assertEqual(validate_roundtrip(xml, code).find('Items/Item').text, raw)

    def test_unique_extraction_ignores_comments_and_ambiguous_names(self):
        (self.base / 'items.lua').write_text(
            '--[[\nDisabled\nBase\n]]\nreturn {[[\nKnown\nBase\n+(10-20) to maximum Life\n]],'
            '[[\nAmbiguous\nBase A\n]],[[\nAmbiguous\nBase B\n]]}', encoding='utf-8')
        self.assertEqual(extract_uniques(self.base),
                         {'Known': 'Rarity: UNIQUE\nKnown\nBase\n+(10-20) to maximum Life'})

    def test_older_catalog_without_uniques_keeps_notes(self):
        self.catalog.pop('uniques', None)
        catalog = self.base / 'catalog.json'
        catalog.write_text(json.dumps(self.catalog), encoding='utf-8')
        path = self.file('Interludes', self.build(inventory_slots=[
            {'inventory_id': 'Gloves1', 'unique_name': 'Lochtonial Caress'}]))
        xml, code, _ = convert([path], catalog_path=catalog)
        self.assertEqual(validate_roundtrip(xml, code).find('Items/ItemSet/Slot').get('itemId'), '0')

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
        overwritten = write_outputs(self.base / 'merged', *result, overwrite=True)
        self.assertEqual(overwritten, paths)
        self.assertEqual(overwritten[0].read_bytes(), result[0])

    def test_wrong_version(self):
        with self.assertRaises(ConversionError):
            convert([self.file('Act 1', self.build())], tree_version='0_4')

    def test_explicit_mobalytics_quest_reward_becomes_config_input(self):
        rewards = [
            {'quest': {'slug': 'g1-2-mappincarrioncrone', 'name': 'Beira of the Rotten Pack',
                       'act': 'Act 1', 'area': 'Clearfell'},
             'reward': {'slug': 'g1-2-carrioncroneslain', 'name': 'Beira of the Rotten Pack',
                        'bakedDescription': '+10% to Cold Resistance',
                        'modifiers': ['+10% to Cold Resistance']}},
            {'quest': {'slug': 'g2-6-mappinmedallion', 'name': 'Medallion',
                       'act': 'Act 2', 'area': 'Valley of the Titans'},
             'reward': {'slug': 'g2-6-fragmentaltarrightactive', 'name': 'Medallion',
                        'bakedDescription': '30% increased Charm Effect Duration, +1 Charm Slot',
                        'modifiers': ['30% increased Charm Effect Duration', '+1 Charm Slot']}},
        ]
        path = self.file('Act 2', self.build(poe2_build_to_pob2={'quest_rewards': rewards}))
        xml, code, report = convert([path])
        root = validate_roundtrip(xml, code)
        inputs = {node.get('name'): node for node in root.findall('Config/Input')}
        self.assertEqual(inputs['questAct 1ClearfellBeira'].get('boolean'), 'true')
        self.assertEqual(inputs['questAct 2Valley of the TitansMedallion'].get('string'),
                         '30% increased Charm Effect Duration\n\t+1 Charm Slot')
        self.assertEqual(report['quest_rewards'][0]['mapped'], sorted(inputs))


if __name__ == '__main__':
    unittest.main()
