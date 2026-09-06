# PoE2 Build to PoB2

Repository name: `poe2-build-to-pob2`

**Build → PoB2** merges multiple Mobalytics / PoE2 `.build` stages into one Path of Building 2 build.

It converts Mobalytics / PoE2 JSON `.build` files into **one PoB2 XML file**, an **import code**, and a **JSON report**. The GUI can also import every official `.build` variant from a public Mobalytics PoE2 guide URL. It requires Python 3.10 or newer. The source interface uses Tkinter, included with the standard Windows Python installation.

## Windows executable

Open `Build2PoB2.exe`. It is the ready-to-run Windows version and includes Python, Tkinter, and the 0_5 tree catalog. It does not require Python. Importing local `.build` files works offline; importing a Mobalytics URL requires internet access. The application opens in Portuguese (Brazil); use the flags at the top to switch at any time between **Portuguese (Brazil)** and **English (US)**.

Download the executable and ZIP package from the [latest release](https://github.com/igorcastroo/poe2-build-to-pob2/releases/latest).

## For developers: running the source version

1. Extract the ZIP to a folder.
2. Open **Abrir Conversor.bat**, or run `py converter.py --gui` from a terminal in that folder.
3. Add the `.build` files, or paste a public `https://mobalytics.gg/poe-2/builds/...` guide URL and select **Import guide**. The list is sorted automatically; use Move Up / Move Down to adjust it.
4. Choose a class only if the files' ascendancy does not identify it.
5. Select **Create PoB2**, choose a new output name, then select **Copy code**.
6. In PoB2, use **Import/Export Build → Import from Code**.

The tool creates `name.xml`, `name.txt`, and `name.report.json`. It never overwrites an existing output. The XML can also be placed in the PoB2 builds folder.

This development path requires Python with Tkinter. If Windows does not recognize `py` or `python`, install Python and enable the option to add it to PATH. End users should download `Build2PoB2.exe` from the latest release instead.

Install the runtime dependency before running the source version:

```powershell
python -m pip install -r requirements.txt
```

## Mobalytics guide URL import

Paste a public PoE2 guide URL in the GUI and select **Import guide**. The app opens that page and calls Mobalytics' own public **Build Planner Export** endpoint for each variant, then validates every returned `.build` before adding it to the list. No login, cookies, credentials, or Mobalytics account data are read or sent by the application.

Only successfully validated files are added. A malformed, empty, unavailable, or oversized variant is shown as rejected and never becomes an invented stage. The downloaded files live in a temporary application folder and are deleted when the program closes; the resulting XML, code, and report are saved only where you choose.

The public guide page can also state a selected **quest reward**. Those explicit selections are recorded in the temporary `.build` metadata and translated into PoB2's **Config → Quest Rewards** inputs only when the reward, area, act, and modifier text exactly match the bundled PoB2 0_5 catalog. Rewards that do not match stay in the preserved source JSON and report; they are never guessed. The Mobalytics Build Planner export does not expose combat, enemy, DPS, or general Config settings, so those fields remain at PoB2 defaults for you to adjust.

This integration depends on Mobalytics' public page and export format, so it can require maintenance if they change their site. The conversion after import remains local.

## CLI

Run the following commands from the extracted folder:

```powershell
python converter.py "C:\MyGuides\*.build" --class Monk -o "C:\MyGuides\GigaBonk"
python converter.py "Act 1.build" "Act 2.build" "Mirror Tier.build" --keep-order --class Monk -o result
python converter.py "C:\MyGuides" --map passives.json --class Monk -o result
python converter.py --validate result.txt
python converter.py --gui
```

Without `--keep-order`, ordering uses the **file name**: Act 1… → Interludes → Early → Mid → Late → High → Mirror. Unrecognized names appear afterward in natural order. Variants within the same phase are ordered by name. In the GUI, the final order shown in the list always wins.

Exit code `0` means success and `2` means failure. Corrupt, empty, wrong-version, or malformed files are skipped and listed in the report. If no valid build remains, no PoB is created. Blocking errors show diagnostics in the terminal; the Python API also exposes `ConversionError.report`.

## Passive map and versions

The bundled catalog contains **4,914 passive IDs**, **967 gems**, classes, ascendancies, and inventory slots extracted from the public PoB2 repository for tree **0_5**. Game version **0.5.5** uses this tree identifier, but the presence of an ID in the map does not prove that balance values are identical across patches.

The map follows the PoB2 association: GGG internal `stringId` → numeric `skill`, equivalent to the passive hash used by PoB. Unknown IDs are **not matched by similar names**. By default, they stop the conversion; `--allow-partial` omits them from active sets while retaining them in the notes and report. The GUI provides the same option and leaves it unchecked initially.

`--map` accepts the formats below. The supplied map replaces the passive section entirely; there is no silent fallback to the bundled catalog.

```json
{"internal_id": 12345}
```

```json
[{"Id": "internal_id", "PassiveSkillsHash": 12345}]
```

```json
{"internal_id": {"PassiveSkillsHash": 12345}}
```

```json
{"tree_version": "0_5", "passives": {"internal_id": 12345}}
```

The IDs above only illustrate the structure; **they are not a usable game map**. Use actual IDs from the catalog or your `passives.json`. Negative, non-16-bit, fractional, Boolean, and conflicting mappings are rejected. Versionless maps are treated as belonging to the selected catalog version, which is the responsibility of the map provider.

To refresh all data from a PoB2 folder containing `TreeData/<version>/tree.json`, `Data/Gems.lua`, and `Data/InventorySlots.lua`:

```powershell
python catalog_tools.py "C:\PoB2" --tree-version 0_5 -o current-catalog.json
python converter.py "C:\MyGuides\*.build" --catalog current-catalog.json --class Monk -o result
```

A clone of the official repository can be used as the source. The extractor **reads data without executing Lua**. If the upstream format changes or ambiguities exist, it stops. A catalog for another version must replace the entire catalog; changing only the `--tree-version` number is not sufficient.

## Preserved data

- One Tree Spec, Skill Set, and Item Set with the same title for every valid stage.
- Mapped passives, weapon sets 1/2, and per-node notes.
- Gems and supports matched by exact catalog IDs, including gem notes.
- Description, author, link, notes, intervals, and additional fields from the original JSON in the Notes section and report.
- Equipment guidance in inventory-slot notes, including unique names.

An official `.build` often carries **equipment guidance**, rather than complete items. A unique name does not include its rolls. The converter creates the Item Set and notes, leaving `itemId=0` when no complete item text is available; it does not invent a base item, affixes, or values. For sources that provide actual PoB item text, an `inventory_slots` entry may use `raw_text` beginning with `Rarity: ...`. The text is copied literally and receives its own item reference. PoB2 remains responsible for parsing that item's base and modifiers.

`level_interval` says when something is recommended for the character; it is **not a gem level**. When the input explicitly provides `level` and `quality`, they are preserved. Otherwise, the XML omits them and PoB applies its own defaults. The tool does not infer numbers from prose or equipment priorities.

The tool does not reconstruct DPS calculations, combat configuration, item modifiers described only in prose, attribute/mastery selections inferred from notes, tree links, or intervals as extra stages. The exception is an explicit Mobalytics quest-reward choice that exactly matches the bundled PoB2 catalog; it becomes a PoB2 Config input. Interval notes are preserved and each input file remains one stage. Inputs that do not follow the official JSON schema need a dedicated adapter.

## Validation and Giga Bonk reference

The implemented flow follows the established result: multiple `.build` files → one PoB2 → stage-specific sets → mapped internal IDs → XML → zlib → URL-safe Base64.

Automatic validation checks exact **XML → compression/code → decompressed XML** equality, set structure, and item references. Tests cover sorting, invalid files, unknown IDs, Unicode notes, weapon sets, gems, slots, versions, and overwrite protection.

```powershell
python -m unittest discover -s tests -v
```

**Validation limitation:** the original Giga Bonk `.build` files and final PoB were not available in the recovered attachments. Therefore, this project does not claim to reproduce its nine stages / 208 nodes or to have been imported interactively in PoB2. The XML was checked against PoB2's public loaders, and round-trip validation does not replace visual verification of the tree inside the application. The bundled examples are test data, not the Giga Bonk guide.

## Security and publishing

The repository intentionally ignores credentials, certificates, local `.build` files, generated XML/TXT/report files, and release binaries. Keep only synthetic examples under `examples/`. Publish `Build2PoB2.exe` and ZIP packages through GitHub Releases instead of committing them to the repository history.

## Sources

- [Official GGG `.build` schema](https://www.pathofexile.com/developer/docs/game#buildplanner)
- [PoB2 source code and data](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)
- Snapshot used: `3887ae68a6a6b8bb7b41d1b61998f1aa184201e4`.
- XML fields were checked against `PassiveSpec.lua`, `SkillsTab.lua`, `ItemsTab.lua`, `TreeTab.lua`, `Build.lua`, and `GameVersions.lua` in that snapshot.

The catalog contains game data © Grinding Gear Games, derived from PoB2. See `THIRD_PARTY_LICENSES.md` for notices from the source project.
