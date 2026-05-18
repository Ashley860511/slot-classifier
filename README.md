# Slot Classifier + Figma Research Board Package

This package contains a portable version of the slot-video screenshot classifier and the Figma/FigJam research-board export workflow.

## Folder Structure

```text
slot_classifier_figma_share_package/
  app/
    main.py                         # main classifier
  project/
    input_videos/                   # put source videos here
    output/                         # classifier output appears here
  figma_tools/
    export_figma_board.py           # selects representative images and writes figma_export
    figma_plugin/
      manifest.json                 # import this in Figma Desktop
      code.js
      ui.html
  figma_export/
    figma_manifest.json             # generated board layout manifest
    images/                         # copied representative images
  requirements.txt
  run_classifier.ps1
  run_figma_export.ps1
```

## 1. Install Python Dependencies

Use Python 3.10 if possible.

```powershell
.\setup_venv.ps1
```

PaddleOCR may require extra setup depending on the target machine and GPU/CPU environment. If installation fails, follow PaddleOCR's official installation instructions for the target environment.

Before running the classifier, you can check the current Python environment:

```powershell
.\check_environment.ps1
```

The bundled scripts prefer `.venv\Scripts\python.exe` when it exists.

## 2. Run Classification

Put videos in:

```text
project/input_videos/
```

Then run:

```powershell
.\run_classifier.ps1
```

The classifier writes per-video folders to:

```text
project/output/
```

Each video output contains category folders such as `Basegame`, `Feature game`, `BigWin`, `Transition`, `loading`, `Result`, and `low_score`.

## 3. Export for Figma/FigJam

After classification, run:

```powershell
.\run_figma_export.ps1
```

This creates or refreshes:

```text
figma_export/
  figma_manifest.json
  images/
```

The export keeps one representative image for `loading`, `BaseGame`, `Transition`, `FreeGame`, and `Result` per video. BigWin keeps up to three representative win tiers.

## 4. Import Into Figma/FigJam

1. Open Figma Desktop.
2. Go to `Plugins` -> `Development` -> `Import plugin from manifest...`.
3. Select:

```text
figma_tools/figma_plugin/manifest.json
```

4. Open a Figma or FigJam file.
5. Run plugin `Slot Research Board Importer`.
6. When prompted, choose the whole `figma_export` folder.

The plugin places every screenshot as a separate editable image node, arranged as a research board.

## Notes

- `Other` is intentionally omitted from the Figma board.
- The package version of `app/main.py` uses relative paths, so the package can be moved to another folder.
- The Figma import does not use MCP calls; it runs locally inside Figma, so it avoids MCP tool call limits.
