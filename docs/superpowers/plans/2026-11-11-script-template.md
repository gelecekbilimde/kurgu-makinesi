# Script Template (A/V script) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Google Docs A/V script template (TÜR | GÖRÜNTÜ | SES | EKRAN SÜRESİ) with an in-doc duration checker, plus a repo-side reader that turns the exported .docx into `script.json`, the rough cutter's `script.txt`, and a teleprompter `.txt`.

**Architecture:** The duration and warning rules are written twice, once in Python (`rules.py`) and once in Apps Script (`rules.gs`). Both are pure functions, and one shared JSON file of test cases keeps them identical. `script_doc.py` parses the .docx (stdlib zip + XML) and handles two kinds of script:
- **A/V template docs:** produces structured rows.
- **Old-style scripts (no A/V tables):** reproduces today's `docx_to_text.py` output byte for byte.

`docx_build.py` writes minimal .docx files; it builds the template and the test fixtures. The Google master is assembled by hand from the repo, following a checklist.

**Tech Stack:**
- Python 3.12, stdlib only. Tests use `unittest`; pytest is not installed.
- Node 22 (`node --test`), to run `rules.gs` locally.
- Google Apps Script (V8).

**Spec:** `docs/superpowers/specs/2026-11-11-script-template-design.md`

## Amendment (2026-11-11, by the user's decisions during Task 6)
- **The template has three columns:** TÜR, GÖRÜNTÜ, SES. There is no EKRAN SÜRESİ column, no `rules.gs`, no `Code.gs`, no node tests and no total inside the doc.
- **Durations exist only in `script_doc.py`'s output,** at the speaker's pace:
  - `rules.check_row(tags, visual, ses, rate) -> {"seconds": int | None, "warnings": [...]}` and `rules.estimate_s(words, rate)`;
  - `templates/script/speakers.json` holds `{"default": 2.2, "speakers": {"Burak Cankaya": 2.2}}`;
  - the speaker is resolved from `episode.json` "speaker", then `--speaker`, then the header's *Sunucu*, then the default; heading names are never used;
  - `script.json` gains `speaker`, each row's `est_s` and `total_s`;
  - the CLI prints `Tahmini toplam (yazıldığı gibi): M:SS`.
- **Silent rows** have no estimate and no warning (`silent_no_duration` is dropped).
- **The ±10% acceptance check is dropped:** the as-written total is not meant to match the cut (COP31: 16:10 against 24:51).
- **Deviation report and pace measurement** move to the B-roll skill design.
- **Task 1** reduces to checking dropdown chips in the Google .docx export, folded into Task 7.
- **Task 7 Step 3** becomes a round trip: `episodes/cop31/script-av.docx` goes through Google Docs and back, and the reader must give the same rows.

- **Two columns, GÖRÜNTÜ | SES (third decision).** The type is a typed, bracketed tag at the start of GÖRÜNTÜ, parsed by `rules.split_visual(cell) -> (tags, unknown, visual)`; an empty GÖRÜNTÜ means KAMERA. There is no TÜR column and no dropdowns, and the master checklist loses its dropdown step. Future: LLM intent detection replaces the tags.

Sections below describe the original plan; where they conflict with this amendment, the amendment wins.

## Global Constraints
- All new code lives in `templates/script/`. Python is **stdlib only**. Files are written as **UTF-8**, with `ensure_ascii=False` for JSON.
- **Column headers:** `TÜR`, `GÖRÜNTÜ`, `SES`, `EKRAN SÜRESİ`. The reader also accepts `EKRAN SURESI`; headers are matched on a Turkish-folded, upper-cased form.
- **Tags:** `KAMERA`, `STOK`, `ARŞİV`, `GRAFİK`, `YAZI`, `KAYNAK`, `YZ`. A row may have two.
- **Rates and thresholds:**

  | Constant | Value |
  |---|---|
  | `RATE_WPS` | 2.2 |
  | `MIN_S` | 2 (warn when below) |
  | `SHOT_S` | 7 (STOK/ARŞİV/YZ: warn when above) |
  | `LONG_S` | 15 (any non-KAMERA row: warn when above) |
  | `YAZI_WPS` | 3 (on-screen text needs 1 s per 3 words) |
- **Rounding:** `floor(x + 0.5)` in both languages. Never Python's `round()`, which rounds halves to even.
- **Warning texts,** verbatim from the spec:
  - `çok kısa: komşu satırla birleştir`
  - `birden fazla çekim gerekebilir`
  - `uzun: bölmeyi veya hareketli grafik kullanmayı düşün`
  - `yazı okunamayacak kadar kısa ekranda`
  - `kaynak eksik`
  - `TÜR seçilmedi`

  Plus one added in this plan: `sessiz satır: süreyi elle gir`.
- **Menu:** `Gelecek Bilimde` › `Süreleri hesapla`.
- **Total line:** `Tahmini toplam: M:SS` (H:MM:SS from one hour up), as the last paragraph of the document.
- **Rough cutter unchanged:** `sections.py` must stay unmodified. COP31 must produce an identical `sections.json`.
- **Commits:** only with the user's go-ahead (a standing rule in this repo). Never commit `*.rpm`, `wiki/.obsidian/workspace.json`, `demo/` or `episodes/`.
- **Tests:** `python3 -m unittest discover -s templates/script/tests -v` and `node --test templates/script/tests/`.

## Review Focus
1. **Google's .docx export may use different style IDs for headings** than the COP31 file (`Heading2`). The reader resolves a heading through `styles.xml` names (`heading 2`), not the ID. Test in Task 4.
2. **Cells with several paragraphs, `w:br` line breaks, or text wrapped in `w:sdt` content controls** (which is how dropdown chips may export). Text must not be lost, and words are counted across all of it. Test in Task 4.
3. **Empty trailing rows** that writers leave in tables. A fully empty row is skipped: no `TÜR seçilmedi`, no ID. Test in Task 4, and the same rule in `Code.gs` in Task 6.
4. **Paragraphs between tables** under a heading are notes, not SES, and the reader warns. A table directly under an H2, with no H3, belongs to the H2. Test in Task 4.
5. **A table in an old-style script** (COP31 has two timeline tables) must not switch the reader into template mode. Template mode needs a table whose first row has both `TÜR` and `SES`. Test in Task 4.

---

### Task 1: Spike: dropdown chips and the `/copy` link (manual, with the user)

This settles the spec's "Risks to check first". It needs the user's Google account. Nothing is committed.

**Files:**
- Create: `episodes/spike-chips/` (gitignored), which holds `test.docx` and `findings.md`.

**Interfaces:**
- Produces: two facts recorded in this plan's **Spike results** section below.
  - `CHIP_IN_DOCX`: either `text` (the chip value appears in `w:t`, possibly inside `w:sdt`) or `lost`.
  - `CHIP_IN_APPS_SCRIPT`: either `yes` (`TableCell.getText()` contains the chip value) or `no`.
  - Also: whether `/copy` carries the bound script and its menu.

- [ ] **Step 1: Ask the user to build a scratch Google Doc.**
  1. Create a 2×2 table with the header `TÜR | SES`.
  2. In row 2, insert a dropdown (Insert › Dropdown, new preset with the 7 tags) and choose `STOK`; type some words into SES.
  3. Add a 3rd row where `GRAFİK` is typed as plain text.
  4. Download it as .docx into `episodes/spike-chips/test.docx`.
- [ ] **Step 2: Inspect the export.** Run `python3 -c "import zipfile;print(zipfile.ZipFile('episodes/spike-chips/test.docx').read('word/document.xml').decode())" | grep -o 'STOK[^<]*\|<w:sdt[^>]*>' | head`. If `STOK` is printed, then `CHIP_IN_DOCX=text`. Note whether it sits inside `w:sdt`, and record the heading style IDs and names from `word/styles.xml`.
- [ ] **Step 3: Probe Apps Script.** The user opens Extensions › Apps Script and pastes this probe. Then they run `probe` and paste the log back, and reload the doc to check that the menu appears.

```javascript
function onOpen() { DocumentApp.getUi().createMenu('Gelecek Bilimde').addItem('Probe', 'probe').addToUi(); }
function probe() {
  const t = DocumentApp.getActiveDocument().getBody().getTables()[0];
  for (let r = 0; r < t.getNumRows(); r++) for (let c = 0; c < t.getRow(r).getNumCells(); c++) {
    const cell = t.getRow(r).getCell(c), kinds = [];
    for (let i = 0; i < cell.getNumChildren(); i++) {
      const p = cell.getChild(i); kinds.push(String(p.getType()));
      if (p.getNumChildren) for (let j = 0; j < p.getNumChildren(); j++) kinds.push('  ' + p.getChild(j).getType());
    }
    Logger.log(`${r},${c} text=${JSON.stringify(cell.getText())} ${kinds.join(' ')}`);
  }
}
```
  If row 2's TÜR text contains `STOK`, then `CHIP_IN_APPS_SCRIPT=yes`.
- [ ] **Step 4: Test the `/copy` link.** The user shares the doc as "anyone with the link: Viewer", then opens `https://docs.google.com/document/d/<ID>/copy` and makes a copy. In the copy, Extensions › Apps Script must show the probe, and the `Gelecek Bilimde` menu must appear after a reload; record whether the unverified-app screen let them continue.
- [ ] **Step 5: Record the results** in **Spike results** below. If `CHIP_IN_DOCX=lost`, the template's TÜR column becomes typed text, and Task 5's checklist drops the dropdown step. Tell the user before continuing.

**Spike results:** *(filled in by Step 5)*

---

### Task 2: Shared rules in Python and Apps Script

**Files:**
- Create: `templates/script/rules.py`, `templates/script/rules.gs`
- Test: `templates/script/tests/rules_cases.json`, `templates/script/tests/test_rules.py`, `templates/script/tests/rules.test.mjs`

**Interfaces:**
- Produces, with the same names and behaviour in both languages (`snake_case` in Python, `camelCase` in JS):
  - Constants `RATE_WPS`, `MIN_S`, `SHOT_S`, `LONG_S`, `YAZI_WPS`; `TAGS` (a tuple or array in the order of the Global Constraints).
  - `WARN`: a dict or object mapping a code to `{"text": <Turkish>, "colour": "red"|"amber"}`. The codes are:

    | Code | Colour |
    |---|---|
    | `too_short` | red |
    | `many_shots` | amber |
    | `long` | amber |
    | `yazi_short` | amber |
    | `source_missing` | red |
    | `no_tag` | red |
    | `silent_no_duration` | red |
  - `fold(s: str) -> str`: Turkish-aware upper-casing with the diacritics folded (`ç→C ğ→G ı/i/İ→I ö→O ş→S ü→U`), whitespace collapsed and stripped.
  - `normalize_tag(s: str) -> str | None`: matches on `fold`. It accepts each tag and these aliases: `STOCK→STOK`, `ARCHIVE→ARŞİV`, `GRAPHIC→GRAFİK`, `TEXT→YAZI`, `SOURCE→KAYNAK`, `AI→YZ`, `CAMERA→KAMERA`. Unknown input returns `None`.
  - `count_words(ses: str) -> int`: drop `\([^)]*\)`, split on whitespace, and count the tokens that contain a letter or digit. Python uses `str.isalnum` per character; JS uses `/[\p{L}\p{N}]/u`.
  - `estimate_s(words: int) -> int`: `floor(words / RATE_WPS + 0.5)`.
  - `check_row(tags: list[str] | None, visual: str, ses: str, manual_s: int | None) -> {"seconds": int | None, "warnings": list[str]}`.
    - The codes are returned in the order of the `WARN` table.
    - `tags=None` means the tags can't be read. Every tag-dependent rule is then skipped (`no_tag`, `many_shots`, `long`, `yazi_short`, `source_missing`), and only `too_short` and `silent_no_duration` apply.
  - `format_total(seconds: int) -> str`: `"24:40"`, or `"1:02:05"` from one hour up.

The rules inside `check_row`:
- **seconds:**
  - When SES has words: `estimate_s(count_words(ses))`.
  - Otherwise: `manual_s`.
  - Otherwise: `None`, with `silent_no_duration`.
- **too_short:** seconds is not `None` and `< MIN_S`.
- **many_shots:** a tag in {STOK, ARŞİV, YZ} and seconds `> SHOT_S`.
- **long:** a tag other than KAMERA and seconds `> LONG_S`.
- **yazi_short:**
  - The YAZI text is the text inside quotes in `visual` (“…”, "…" or ‘…’). If there are none and tags == `["YAZI"]`, it is the whole `visual`.
  - Warn when `count_words(yazi) / YAZI_WPS > seconds`.
- **source_missing:**
  - GRAFİK needs a digit, `http`, or `\bK\d+\b` in `visual`.
  - KAYNAK needs `http` in `visual`.
- **no_tag:** tags is an empty list.

- [ ] **Step 1: Write `rules_cases.json`.** It is a list of `{"name", "fn", "args", "expected"}` entries, with at least these cases:
  - `count_words("COP (kap), \"Conference of the Parties\" demek.")` → 6 (the `,` token has no letter)
  - `count_words("yüzde 55–60 düşmesi — gerekiyor")` → 4
  - `estimate_s(38)` → 17; `estimate_s(1)` → 0; `estimate_s(11)` → 5; `estimate_s(12)` → 5; `estimate_s(13)` → 6
  - `normalize_tag` of `"stok"`, `"Stok "`, `"STOCK"`, `"arşiv"`, `"ARSIV"`, `"Grafik"`, `"GRAFIK"`, `"yz"`, `"AI"` → the canonical tag; `"film"` → `null`.
  - `check_row(["GRAFİK"], "İki çubuk", <38 words>, null)` → `{"seconds":17,"warnings":["long","source_missing"]}`
  - The same with `"İki çubuk: %55–60 ve ~%15"` → `{"seconds":17,"warnings":["long"]}`
  - `check_row(["STOK"], "roket", <20 words>, null)` → `{"seconds":9,"warnings":["many_shots"]}`
  - `check_row(["KAMERA"], "", "Peki.", null)` → `{"seconds":0,"warnings":["too_short"]}`
  - `check_row(["YAZI"], "“<a 10-word quote>”", <6 words>, null)` → `{"seconds":3,"warnings":["yazi_short"]}` (10/3 > 3). The same with an 8-word quote → `"warnings":[]`
  - `check_row(["KAYNAK"], "makale ekran görüntüsü", <10 words>, null)` → `["source_missing"]`
  - `check_row([], "", <10 words>, null)` → `["no_tag"]`
  - `check_row(["GRAFİK"], "başlık kartı", "", 3)` → `{"seconds":3,"warnings":["source_missing"]}`
  - `check_row(["KAMERA"], "", "", null)` → `{"seconds":null,"warnings":["silent_no_duration"]}`
  - `check_row(null, "", "Peki.", null)` → `["too_short"]`
  - `format_total(1480)` → `"24:40"`; `format_total(3725)` → `"1:02:05"`
- [ ] **Step 2: Write `test_rules.py`,** which runs every case through `rules.py` (a `subTest` per case), and **`rules.test.mjs`,** which loads `rules.gs` with `vm.runInNewContext` and runs every case through the camelCase names. Run both test commands. Expected: FAIL, because the modules are missing.
- [ ] **Step 3: Implement `rules.py` and `rules.gs`** to the interfaces above. `rules.gs` must hold only top-level `const` and `function` declarations, with no `module`, `require` or `export`, so it runs unchanged in Apps Script.
- [ ] **Step 4: Run both test commands.** Expected: every case passes in both languages.
- [ ] **Step 5: Commit** (with the user's go-ahead): `git add templates/script/rules.* templates/script/tests/` and commit with `feat(script): shared duration and warning rules (py + apps script)`.

---

### Task 3: Minimal .docx writer

**Files:**
- Create: `templates/script/docx_build.py`
- Test: `templates/script/tests/test_docx_build.py`

**Interfaces:**
- Produces: `build_docx(blocks: list, path: str) -> None`. Each block is one of:
  - `("p", style_id: str | None, text: str)`;
  - `("li", text)`: a list item, written with the `ListParagraph` style and `w:numPr`;
  - `("tbl", rows: list[list[str]], widths_twips: list[int])`. Cell text with `\n` becomes separate paragraphs. A cell string that starts with `"\x00sdt:"` is wrapped in a `w:sdt` content control (used only by the test fixtures).

  The package contains `[Content_Types].xml`, `_rels/.rels`, `word/document.xml`, `word/_rels/document.xml.rels`, `word/styles.xml` and `word/numbering.xml`. `styles.xml` defines `Title`, `Heading1`–`Heading3` (named `heading 1`–`heading 3`) and `ListParagraph` (named `List Paragraph`), plus an optional extra style passed in as `extra_styles: dict[str, str]` (id → name) for the Review Focus test. Every `ZipInfo` gets `date_time=(2026,1,1,0,0,0)`, so the output is byte-reproducible.

- [ ] **Step 1: Write the failing test.**
  - Build a doc with a `Heading2` paragraph, an `li` and a 2×2 table; reopen it with `zipfile`; assert that `word/document.xml` parses and contains one `w:tbl`, four `w:tc` and the `Heading2` `pStyle`.
  - Building twice gives identical bytes.
  - Run `python3 -m unittest templates/script/tests/test_docx_build.py`. Expected: FAIL.
- [ ] **Step 2: Implement `build_docx`.**
- [ ] **Step 3: Run the test.** Expected: PASS. Also open one generated file in LibreOffice if available (`soffice --headless --convert-to pdf`), or leave it for Task 5's Google import.
- [ ] **Step 4: Commit** (with the user's go-ahead) with `feat(script): minimal docx writer for template and fixtures`.

---

### Task 4: Reader: `script_doc.py`

**Files:**
- Create: `templates/script/script_doc.py`
- Test: `templates/script/tests/test_script_doc.py`, with fixtures built at test time through `docx_build`.

**Interfaces:**
- Consumes: `rules.check_row`, `rules.normalize_tag`, `rules.count_words`, `rules.fold`, `rules.format_total`; `docx_build.build_docx` (tests only).
- Produces:
  - `read_blocks(path) -> list`: the body in document order.
    - Each block is `("p", style, text, is_list)` or `("tbl", rows)`, where `rows` is `list[list[str]]` and cell paragraphs are joined by `\n`.
    - All `w:t` text is taken, including inside `w:sdt`. `w:br` and `w:tab` become `\n` and a space.
    - `style` is `"Heading<n>"` when the style's `styles.xml` name matches `heading <n>` (case-insensitive), otherwise the style ID or `None`.
    - `is_list` means the paragraph has `w:numPr` or the `ListParagraph` style.
  - `legacy_text(path) -> str`: **byte-identical to `docx_to_text.py`**. Every `w:p` in document order (table paragraphs included), each prefixed with `"[<styleId>] "` when styled, joined by `\n`.
  - `parse(path, stop=("Kaynakça","Kaynaklar")) -> dict | None`. It returns `None` unless some table's first row, once folded, contains both `TUR` and `SES`. Otherwise it returns:
    ```
    {"format": "av-1", "title": str, "header": {key: value},
     "headings": [{"level": 2|3, "title": str}],
     "rows": [{"id": "R001", "key": <8 hex of sha1(fold(ses) or fold(visual))>, "heading": <index into headings>,
               "tags": [..], "visual": str, "links": [..http..], "refs": ["K3", ..], "ses": str,
               "manual_s": int|None, "est_s": int|None, "warnings": [codes]}],
     "notes": [{"heading": int, "text": str}],
     "kaynakca": [{"k": 1, "text": str}],
     "total_s": int}
    ```
    - **Title:** the `Title` or `Heading1` paragraph.
    - **Header:** `Key: value` paragraphs before the first Heading2.
    - **Rows:** table rows after the header row. A fully empty row is skipped.
    - **Tags:** the TÜR cell is split on newlines and commas, then put through `normalize_tag`; unknown tags are dropped and recorded as a note.
    - **manual_s:** the leading integer of the EKRAN SÜRESİ cell.
    - **Notes:** non-empty paragraphs between headings that are not inside a table.
    - **Kaynakça:** the list paragraphs under the stop heading, numbered from 1.
    - **total_s:** the sum of the rows' `est_s` (ignoring `None`).
  - `to_legacy_txt(script: dict) -> str`: the shape `sections.py` reads, one line per item.
    - Each heading becomes `[Heading<level>] <title>`.
    - For each row: when the tags are not just `["KAMERA"]`, a line `[EKRAN: <TAG>[+<TAG>]: <visual on one line>]` comes first. Then every SES paragraph is a line.
    - At the end: `[Heading2] Kaynakça`, then each entry as `[ListParagraph] <text>`.
  - `prompter_txt(script: dict) -> str`: heading titles and SES paragraphs only, separated by blank lines, with parentheses kept.
  - CLI: `python3 templates/script/script_doc.py <script.docx> <outdir> [--prompter]`.
    - Always writes `outdir/script.txt`.
    - In template mode, also writes `outdir/script.json`, and prints one line per warned row (`R012 3.1 Emisyon…: çok kısa: komşu satırla birleştir (1 sn)`) and `Tahmini toplam: M:SS`.
    - In legacy mode, prints `legacy script (no A/V tables)`, and `--prompter` exits with an error.

- [ ] **Step 1: Write the failing tests.** Each builds a fixture with `build_docx`:
  - `test_template_rows`: a header block, H2 "1. Açılış", H3 "COP nedir?", a table (header plus 3 rows: GRAFİK with `K2`, KAMERA, STOK+YAZI on two lines), and a Kaynakça with 2 `li`. Assert:
    - the headings;
    - the row count is 3, with IDs `R001`–`R003`;
    - `tags == ["STOK", "YAZI"]` on row 3;
    - `refs == ["K2"]`;
    - `est_s` matches `rules.estimate_s`;
    - `kaynakca[1]["k"] == 2`.
  - `test_heading_by_style_name` (Review Focus 1): a style ID `Balk2` named `heading 2` is read as a level-2 heading.
  - `test_multi_paragraph_br_sdt` (Review Focus 2): a SES cell with two paragraphs and a `w:br`, plus a TÜR cell wrapped in `w:sdt`. The words are all counted and the tag is read.
  - `test_empty_rows_skipped` (Review Focus 3): a trailing empty row adds no row and no warning.
  - `test_notes_and_h2_table` (Review Focus 4): a paragraph between two tables lands in `notes`, not in SES. A table directly under the H2 has `heading` pointing at the H2.
  - `test_legacy_table_not_template` (Review Focus 5): a doc whose only table has the header `Yıl | Zirve` makes `parse()` return `None`, and `legacy_text` includes the table paragraphs.
  - `test_legacy_identical_cop31`: skipped unless `demo/cop/raw/COP31_YouTube_Senaryosu.docx` and `episodes/cop31/script.txt` exist. Asserts that `legacy_text(docx) == open(script.txt).read()`.
  - `test_legacy_txt_shape`: `to_legacy_txt(parse(fixture))` has `[EKRAN: GRAFİK: …]` before the row's SES and `[Heading2] Kaynakça` near the end.
  - `test_cli_writes_files`: run the CLI on the fixture in a temp dir; `script.json`, `script.txt` and (with `--prompter`) `prompter.txt` exist, and `prompter.txt` contains no `[`.
- [ ] **Step 2: Run the tests.** Run `python3 -m unittest templates/script/tests/test_script_doc.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `script_doc.py`** to the interfaces above.
- [ ] **Step 4: Run the whole Python suite.** Expected: PASS, with `test_legacy_identical_cop31` passing (not skipped) on this machine.
- [ ] **Step 5: Commit** (with the user's go-ahead) with `feat(script): A/V script reader with legacy compatibility`.

---

### Task 5: Template file, in-doc checker and writer's guide

**Files:**
- Create:
  - `templates/script/build_template.py`;
  - `templates/script/script-template.docx` (generated, committed);
  - `templates/script/Code.gs`;
  - `templates/script/kilavuz.md` (Turkish writer's guide);
  - `templates/script/README.md` (purpose, the `/copy` link placeholder, the rebuild checklist).
- Test: `templates/script/tests/test_template.py`

**Interfaces:**
- Consumes: `docx_build.build_docx`, `script_doc.parse`, `rules.gs`.
- Produces:
  - `build_template.py`: no arguments; writes `script-template.docx` next to itself. Contents:
    - Title `Bölüm başlığı`;
    - header paragraphs `Sunucu:`, `Yazar:`, `Tarih:`, `Durum: taslak`, `Doğrulama notları:`;
    - H2 `1. Açılış (Sunucu adı)` with a table: header row plus two example rows, GRAFİK with `K1, s. 3` and KAMERA;
    - H3 `1.1 Alt başlık` with a table: header row plus one empty row;
    - H2 `Kaynakça` with one `li` example;
    - the final paragraph `Tahmini toplam: –`.
    - Column widths: 14 / 32 / 44 / 10 % of 9,000 twips.
  - `Code.gs`, with `rules.gs` pasted as a second file in the same Apps Script project:
    - **`onOpen()`** adds the menu `Gelecek Bilimde › Süreleri hesapla` → `hesapla()`.
    - **`hesapla()`**, for every body table whose first row folds to contain `TUR` and `SES`, goes through each non-empty data row:
      1. Read the TÜR, GÖRÜNTÜ and SES cells, and `manual_s` from the EKRAN SÜRESİ cell.
      2. Run `checkRow`.
      3. Write `"<s> sn"` and one `"⚠ <WARN text>"` line per warning into EKRAN SÜRESİ.
      4. Set that cell's background to `#f4c7c3` (red), `#fce8b2` (amber, used only when there is no red) or `null`.

      Finally it sets the last paragraph starting with `Tahmini toplam:` to `Tahmini toplam: <formatTotal(sum)>`, appending that paragraph if it is missing.
    - **If `CHIP_IN_APPS_SCRIPT=no`** (from Task 1), pass `tags=null`.

- [ ] **Step 1: Write the failing test** `test_template.py`:
  - `parse("templates/script/script-template.docx")` returns a script with 2 headings of level 2 and 1 of level 3, and 2 data rows; the empty row is skipped;
  - row 1 has `refs == ["K1"]` and no `source_missing`;
  - running `build_template.py` again leaves the file byte-identical.

  Run it. Expected: FAIL.
- [ ] **Step 2: Implement `build_template.py`** and generate the .docx. Run the test. Expected: PASS.
- [ ] **Step 3: Write `Code.gs`.** It is checked by hand in Task 7, because Apps Script can't run locally. Keep every rule in `rules.gs`; `Code.gs` only reads and writes the document.
- [ ] **Step 4: Write `kilavuz.md` in Turkish,** at most about one page:
  - "one row = one picture idea";
  - what each TÜR means, and what GÖRÜNTÜ must contain (the table from the spec);
  - silent rows;
  - the `K3` references;
  - how to run *Süreleri hesapla*, and what each warning means;
  - the first-run "Google hasn't verified this app" screen and the clicks *Gelişmiş › … sayfasına git (güvenli değil)*;
  - sharing the copy with the editor.
- [ ] **Step 5: Write `README.md`.** It covers what the folder is, the `/copy` link (`<to be filled in Task 7>`), and the **rebuild checklist**:
  1. Run `python3 templates/script/build_template.py`.
  2. Upload it to Drive and open it with Google Docs, then save it as a Google Doc.
  3. Add a *Kılavuz* tab and paste `kilavuz.md` into it.
  4. In the TÜR column, insert a dropdown preset with the 7 tags (skip this if `CHIP_IN_DOCX=lost`).
  5. In Extensions › Apps Script, add `rules.gs` and `Code.gs`, then run `hesapla` once to authorise.
  6. Share it as "anyone with the link: Viewer".
  7. Put the `/copy` link into this README.

  The rule: **change the repo first, then the master.**
- [ ] **Step 6: Run both test suites.** Expected: PASS.
- [ ] **Step 7: Commit** (with the user's go-ahead) with `feat(script): template, in-doc checker, writer's guide`.

---

### Task 6: COP31 acceptance (local only)

**Files:**
- Create: `templates/script/tools/legacy_to_av.py`, `templates/script/tests/test_acceptance_cop31.py` (skipped unless `episodes/cop31/` exists).

**Interfaces:**
- Consumes: `build_docx`, `script_doc.parse`, `script_doc.to_legacy_txt`, `rules.format_total`; the rough cutter's unmodified `.claude/skills/rough-cutting-a-roll/scripts/sections.py`.
- Produces: `legacy_to_av(txt_path: str, docx_out: str, tags: dict[int, list[str]] | None = None) -> None`. This converts an old-style `script.txt` into the template layout.
  - **Header block:** lines before the first `[Heading2] 1.` become header paragraphs.
  - **Headings:** stay H2/H3.
  - **`[EKRAN: x]` lines:** each starts a row. Its tags are `tags.get(line_no, ["GRAFİK"])`, its visual is `x`, and its SES is the next body line.
  - **Other body lines:** consecutive ones up to the next `[EKRAN`/heading merge into one KAMERA row, keeping their `[ListParagraph]` lines as separate paragraphs without the prefix.
  - **Kaynakça:** the `[Heading2] Kaynakça` section becomes H2 plus `li` entries.

- [ ] **Step 1: Write the failing test.** It:
  1. converts `episodes/cop31/script.txt` to a temp `cop31-av.docx`, then runs `parse` and `to_legacy_txt` into a temp episode dir. That dir holds a copy of `episode.json` with `"script": "script.txt"`, plus symlinks to the real `plans/` and `transcripts/`;
  2. runs `sections.py` on it.

  It asserts:
  - the resulting `sections.json` equals `episodes/cop31/sections.json` (the `chapters`, `headings` and `pieces` keys);
  - `abs(script["total_s"] - 1491) / 1491 <= 0.10`. On failure, it prints the total, so a miss is a finding to report rather than to tune away.

  Run it. Expected: FAIL.
- [ ] **Step 2: Implement `legacy_to_av.py`.** Run the test. Expected: PASS on `sections.json`. If the ±10% check fails, stop and report the total to the user; do not change `RATE_WPS` without their decision.
- [ ] **Step 3: Write `episodes/cop31/script-av.docx`** (gitignored), so the user can import it to Google Docs as the reference example in Task 7.
- [ ] **Step 4: Commit** (with the user's go-ahead) the converter and the test only, with `test(script): COP31 acceptance through the A/V template`.

---

### Task 7: Google master, checker parity, rough-cutter wiring (with the user)

**Files:**
- Modify:
  - `.claude/skills/rough-cutting-a-roll/SKILL.md`: step 6 and Requirements;
  - `.claude/skills/rough-cutting-a-roll/reference.md`: the tools table row for `docx_to_text.py`, and "Script conventions";
  - `templates/script/README.md`: the `/copy` link;
  - `.gitignore`: add `/.superpowers/`.
- Delete: `.claude/skills/rough-cutting-a-roll/scripts/docx_to_text.py`, now replaced by `legacy_text`.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Wire up the skill.**
  - SKILL.md step 6 becomes: `python3 templates/script/script_doc.py script.docx EP` (writes `EP/script.txt`, plus `EP/script.json` and warnings for A/V scripts; `--prompter` for the teleprompter `.txt`).
  - Update reference.md the same way. Add: "A/V scripts: per-heading tables TÜR | GÖRÜNTÜ | SES | EKRAN SÜRESİ; see `templates/script/README.md`".
  - Then `grep -rn docx_to_text .claude docs/superpowers templates`. Expected: no hits outside the spike log.
- [ ] **Step 2: Build the master with the user,** following the README checklist. The user does the Google steps; I prepare files and read back results.
- [ ] **Step 3: Check parity.** The user imports `episodes/cop31/script-av.docx` as a Google Doc, adds the checker, runs *Süreleri hesapla* and downloads it as .docx. Then run `script_doc.py` on that download, and compare every row's EKRAN SÜRESİ cell text (read with `read_blocks`: the `<s> sn` line and the ⚠ lines) with `est_s` and the `WARN` texts of `warnings` in `script.json`. Expected: identical, and the doc's `Tahmini toplam` equals `format_total(total_s)`. This also re-checks Task 1's chip and heading findings on a real Google export.
- [ ] **Step 4: Writer test (spec acceptance).** The user, or a writer they choose, makes a copy through the `/copy` link and writes a two-chapter test script using only the *Kılavuz* tab. Note every question they had to ask, fix the guide, and update `kilavuz.md` first, following the repo-first rule.
- [ ] **Step 5: Record the `/copy` link** in the README. Run both test suites one last time. Expected: PASS.
- [ ] **Step 6: Commit** (with the user's go-ahead) with `feat(script): A/V script template wired into the rough cutter`, including the spec and this plan.
