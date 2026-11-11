# Script template (A/V script): design

**Date:** 2026-11-11 (amended the same day: on-screen duration moved to the editor side, at the speaker's pace)
**Status:** approved; in implementation
**Scope:** project 1 of 4. The others are the B-roll skill, the graphics design language and archive indexing; each gets its own design later.

## Why
The B-roll skill can only find or build the right visual if it knows **what** the writer wants on screen and **under which words**. Today that information lives in loose `[EKRAN: …]` lines; COP31 has 9 of them in its spoken part, nearly all graphics, with no sources. Editors also lose time finding the data behind a graphic.

## Goals
- A Google Docs template in the **A/V script** format (the documentary industry standard), adapted for Gelecek Bilimde.
- A row structure precise enough for tools: every visual is anchored to the words it covers.
- A deterministic **reader** that turns the exported doc into structured data for the rough cutter (today) and the B-roll skill (next).
- An **as-written duration** per row and in total, at the speaker's own pace, so the editor (and later the deviation report) knows what the script should run to.
- A **teleprompter export** containing only what the presenter reads.

## Non-goals
- **Duration inside the Google Doc.** There is no duration column; the reader computes durations (see below).
- Finding, building or placing any visual. That is the B-roll skill.
- The graphics design language (styles, templates). That is project 3.
- Editing the Google Doc with an LLM, or any script or automation inside Google Docs.
- Converting old episodes, other than COP31 as the reference example.

## Anti-goals (a failure even if it works)
- **Writers have to time rows themselves.** The reader times them.
- **The template is so rigid that writers give up.** Prose in the cells stays free text. Only the bracketed tag is a fixed vocabulary, and only GRAFİK/KAYNAK must carry a source.
- **The rough cutter breaks.** Section detection must keep producing the same chapters.

## The template (decided)

### Document structure, top to bottom
1. **Header table:** two columns, one field per row: Başlık, Sunucu, Yazar, Tarih, Durum. The reader takes the header fields from the first two-column table before any heading. Fact-check notes are **not** in the document: writers use Google Docs comments (decided 2026-11-11).
2. **Front matter:** everything before the first chapter heading other than the header table, such as the tag reminder line or COP31's corrections table. It is free-form; the reader keeps it as text and never treats it as script.
3. **Chapters.** Each chapter heading is a normal **Heading 2** paragraph and each subsection heading a **Heading 3**, both **outside** the tables. Numbering ("1.", "3.1") and the presenter in brackets stay as in COP31: `1. Açılış: Zirve neden bu kadar önemli? (Begüm Dursun)`.
4. **Under each heading, one table** with two columns, in this order:

| Column | Contents |
|---|---|
| **GÖRÜNTÜ** | starts with the visual type as a bracketed tag, `[STOK] …`, then what the viewer should see, in the writer's words, plus data or a link where required. An empty cell means the presenter (KAMERA). |
| **SES** | exactly what the presenter reads. Pronunciation hints stay in parentheses, as today: `COP (kap)` |

5. **Kaynakça** as the last Heading 2, unchanged from today. Entries are numbered so that cells can cite them as `K3`.

### Rows
- **A new row starts when the picture changes.** A row means "while these words are spoken, show this". It can be one sentence or a paragraph.
- A row whose visual is just the presenter has an **empty GÖRÜNTÜ** (or `[KAMERA]`).
- A row with **no SES** is a silent visual, such as a title card or a music break.
- Lists the presenter reads (COP31's three questions) are ordinary paragraphs or bullets inside one SES cell.

### Type tags (leading GÖRÜNTÜ, in square brackets)
| Tag | Meaning | GÖRÜNTÜ must contain |
|---|---|---|
| **KAMERA** | presenter on screen (the default) | nothing |
| **STOK** | any outside footage: Pexels, Pixabay, NASA, ESA, other agencies and institutions | a description of the shot |
| **ARŞİV** | Gelecek Bilimde's **own** past footage (Dropbox; not indexed yet) | what the writer remembers ("2024 laboratuvar çekimi, mikroskop yakın plan") |
| **GRAFİK** | built with HyperFrames | what the graphic shows, **and** the data or a source: numbers in the cell, a link, or `K3, s. 12` |
| **YAZI** | on-screen text or a lower third | the exact text |
| **KAYNAK** | screenshot of an article, paper or report | **a link** |
| **YZ** | generated with Adobe Firefly | a description (it becomes the prompt) |

**Tags are typed, not picked from a dropdown** (decided 2026-11-11). Google Docs dropdowns had to be inserted by hand in every row, and a dropdown left unset silently exports its first option (KAMERA), which hides the writer's intent. A typed tag is case- and Turkish-letter-insensitive (`[grafik]`, `[GRAFIK]`, `[graphic]` → GRAFİK). A missing tag is reported as "TÜR seçilmedi", and an unknown one as "bilinmeyen TÜR". A row may carry **two tags**, `[STOK, YAZI] …` or `[STOK][YAZI] …`, and GÖRÜNTÜ then describes both.

**Future:** drop the tag requirement and detect the type from the GÖRÜNTÜ description with an LLM intent-detection call. The tags then become optional overrides.

### Checks (done by the reader, not inside the doc)
| Condition | Warning |
|---|---|
| GRAFİK without numbers, a link or a `K` reference; KAYNAK without a link | "kaynak eksik" (source missing) |
| GÖRÜNTÜ has text but no tag | "TÜR seçilmedi" (no type given) |

## On-screen duration: editor side only, at the speaker's pace (decided 2026-11-11)
**The first attempt.** A fourth column, EKRAN SÜRESİ, filled by an Apps Script checker at 2.2 words/s. COP31 showed it predicting the wrong thing:
- The spoken part of the script is **2,140 words**.
- The host spoke about **3,050**, with ad-libs, a second welcome and connecting phrases.
- The script estimated **16:10**; the real A-roll is **24:51**.

**The decision.** The speaker reads the script at their own pace, so the estimate answers "how long is this script **as written**". Deviations from the script are to be kept as small as possible. The gap between as-written and the real cut is a measurement, not an estimation error.
- **No duration column and no script inside the Google Doc.** Durations exist only in the reader's output, for the editor.
- **Per row:** `est_s = floor(SES words / pace + 0.5)`. Text in parentheses doesn't count. A silent row (no SES) has no estimate.
- **Pace:** per speaker, in `templates/script/speakers.json` (script words per second). It starts with Burak Cankaya at 2.2, measured on COP31, and a default of 2.2.
- **Speaker, strongest first:**
  1. `"speaker"` in the episode's `episode.json` (who is actually on camera);
  2. the reader's `--speaker` option;
  3. the script header's *Sunucu*;
  4. unknown, which uses the default pace.

  Names in chapter headings are **not** used: COP31's chapter 1 says "(Begüm Dursun)", but Burak Cankaya presented it.
- **Warnings** for the editor, in addition to "kaynak eksik" and "TÜR seçilmedi":

| Condition | Warning |
|---|---|
| < 2 s | çok kısa: komşu satırla birleştir |
| STOK/ARŞİV/YZ row > 7 s | birden fazla çekim gerekebilir |
| any non-KAMERA row > 15 s | uzun: bölmeyi veya hareketli grafik kullanmayı düşün |
| YAZI text needs longer than the row (1 s per 3 words) | yazı okunamayacak kadar kısa ekranda |

- **Total:** the reader prints "Tahmini toplam (yazıldığı gibi): M:SS".

**Next, with the B-roll skill design:**
- **Deviation report:** match the rough cut to the script row by row. It finds:
  - **off-script spans**, which default to KAMERA (speaker view; the B-roll skill never covers them);
  - **script phrases spoken twice** and still in the cut, which are likely missed retakes;
  - rows much longer than estimated.
- **Speaker pace measured** from matched rows only, updating `speakers.json`.

## Distribution (decided)
The team uses **personal Google accounts**; there is no Workspace and no admin.
- **Master template:** one Google Doc owned by the maintainer's account, with the *Kılavuz* tab built in. It is shared as **"anyone with the link: Viewer"**, so nobody can change it by mistake.
- **Writers start from a copy link:** `https://docs.google.com/document/d/<ID>/copy`. It opens Google's "Make a copy" dialog directly. The link goes into the repo's README for writers and into the setup checklist.
- **Hand-off to editing:** the writer shares their copy with the editor (view or comment), and the editor downloads the .docx into `episodes/<slug>/`.
- **Redundancy in the repo:** `templates/script/` holds everything needed to rebuild the master from scratch:
  - the Turkish guide text;
  - a generated `script-template.docx` (built by a script, so changes are reviewable);
  - a step-by-step rebuild checklist (import the .docx, add the *Kılavuz* tab, set the sharing).

  Changing the master means changing the repo first, then following the checklist.

## The tools (decided at this level; internals left to the builder)
1. **Reader** (`script_doc.py`, Python, no dependencies, in the repo). Input: the doc exported as **.docx** (File › Download › .docx) and saved as `episodes/<slug>/script.docx`. Output:
   - `script.json`: header fields; headings; the speaker and pace; rows with `{id, key, heading, tags[], visual, links[], refs[], ses, est_s, warnings[]}`; notes; the Kaynakça entries; `total_s`.
   - `script.txt` in the **current** `[Heading2] …` / `[EKRAN: …]` shape, so `sections.py` works unchanged. Each SES cell becomes body text and each non-KAMERA GÖRÜNTÜ an `[EKRAN: TAG: …]` line.
   - It prints the speaker, the warnings from the checks above and the as-written total for the editor.
   - It finds columns by their header text. Columns it doesn't know, such as an old EKRAN SÜRESİ, are ignored. Several tables under one heading are fine. A paragraph between tables, under a heading, is a note: it is not part of SES.
   - It still accepts old-style scripts (no tables). In that case it behaves like today's `docx_to_text.py`, which it replaces.
2. **Teleprompter export:** `script_doc.py --prompter` writes the headings and SES text only, with the parentheses kept, as a `.txt` file.
3. **Template source in the repo:** `templates/script/`, described under Distribution.
4. **Rough-cutting skill:** update step 6 to use `script_doc.py`. Nothing else changes.

## Acceptance
- **COP31 conversion:** COP31 rewritten in the template (the reference example; its `[EKRAN]` notes become tagged rows) gives the **same `sections.json`** through the reader as the current script.txt does.
- **Google export round trip:** the COP31 reference doc imported into Google Docs and downloaded again as .docx gives the same rows through the reader.
- **A writer can follow the guide:** a writer who has never seen the format can write a two-chapter test script from the guide alone.

## Risks checked
- **Google round trip** (2026-11-11): COP31 went through Google Docs and back as .docx with identical rows, headings and Kaynakça. Heading styles export as `Heading2`/`Heading3`/`Title`. A dropdown chip exports as a content control holding its displayed value; this is moot now that tags are typed.
- **Every tab is exported** (master check, 2026-11-11): the *Kılavuz* tab comes out after the Kaynakça, starting with a Heading 1. So the script ends at the Kaynakça, or at a Heading 1 once chapter 1 has started, and anything after that is ignored.

## Left to the builder
- **Row IDs:** the format and how stable they are across edits. The B-roll skill needs to recognise a row after small edits; matching on the SES text is a reasonable basis.
- The exact JSON field names and the warning wording.

- Layout details of the template: column widths, fonts, header block style.

## Calls made in brainstorming without explicit discussion
- .docx export as the hand-off to the tools, rather than the Google Docs API.
- `/copy` link and view-only sharing for the master; editors get access because the writer shares their copy.
- Kaynakça entries numbered as `K1…` for citing in cells.
- The reader emits the old `script.txt` shape so the rough cutter is untouched.
- Paragraphs between tables are notes, not SES.
- The writer's guide lives in a *Kılavuz* tab of the template.
