figma.showUI(__html__, { width: 420, height: 420 });

const COLUMN_KEY_TO_ITEM = {
  loading: "loading",
  basegame: "basegame",
  transition: "transition",
  featuregame: "featuregame",
  featurebuy: "featurebuy",
  help: "help",
  result: "result",
};

async function ensureFonts() {
  await figma.loadFontAsync({ family: "Inter", style: "Regular" });
  await figma.loadFontAsync({ family: "Inter", style: "Medium" });
  await figma.loadFontAsync({ family: "Inter", style: "Bold" });
}

function color(hex) {
  const clean = hex.replace("#", "");
  return {
    r: parseInt(clean.slice(0, 2), 16) / 255,
    g: parseInt(clean.slice(2, 4), 16) / 255,
    b: parseInt(clean.slice(4, 6), 16) / 255,
  };
}

function createText(name, text, x, y, size, weight = "Regular", fill = "#222222") {
  const node = figma.createText();
  node.name = name;
  node.fontName = { family: "Inter", style: weight };
  node.characters = text;
  node.fontSize = size;
  node.fills = [{ type: "SOLID", color: color(fill) }];
  node.x = x;
  node.y = y;
  return node;
}

function findImagePayload(images, src) {
  if (!src) return null;
  const normalized = src.replace(/\\/g, "/");
  return images[normalized] || images[normalized.replace(/^\.?\//, "")] || null;
}

function safeVideoName(video) {
  return String(video.id || "")
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function findFeatureBuyFallback(video, images) {
  const safeVideo = safeVideoName(video);
  if (!safeVideo) return null;
  const prefix = `images/video_${safeVideo}_featurebuy.`;
  const src = Object.keys(images || {}).find((path) => path.startsWith(prefix));
  return src ? { src } : null;
}

function getItemForColumn(video, columnKey) {
  if (columnKey.startsWith("bigwin_")) {
    const index = Number(columnKey.split("_")[1]) - 1;
    return Array.isArray(video.items.bigwins) ? video.items.bigwins[index] : null;
  }
  return video.items[COLUMN_KEY_TO_ITEM[columnKey] || columnKey];
}

async function buildBoard(manifest, images) {
  await ensureFonts();

  const layout = manifest.layout || {};
  const thumbWidth = layout.thumbWidth || 180;
  const thumbHeight = layout.thumbHeight || 270;
  const columnGap = layout.columnGap || 70;
  const rowGap = layout.rowGap || 90;
  const left = 160;
  const top = 150;
  const columns = manifest.columns || [];
  const videos = manifest.videos || [];

  const nodes = [];

  const title = createText("Board Title", manifest.title || "Slot Game Screen Research Board", 0, 0, 42, "Bold", "#069B47");
  figma.currentPage.appendChild(title);
  nodes.push(title);

  const subtitle = createText("Board Subtitle", manifest.subtitle || "", 0, 58, 18, "Regular", "#4F4F4F");
  figma.currentPage.appendChild(subtitle);
  nodes.push(subtitle);

  columns.forEach((column, index) => {
    const x = left + index * (thumbWidth + columnGap);
    const header = createText(`Column Header / ${column.label}`, column.label, x, top - 48, 18, "Bold", "#00A651");
    figma.currentPage.appendChild(header);
    nodes.push(header);
  });

  for (let rowIndex = 0; rowIndex < videos.length; rowIndex += 1) {
    const video = videos[rowIndex];
    const y = top + rowIndex * (thumbHeight + rowGap);
    const label = createText(`Row Label / ${video.label}`, video.label || `Video ${video.id}`, 0, y + 12, 22, "Bold", "#333333");
    figma.currentPage.appendChild(label);
    nodes.push(label);

    for (let columnIndex = 0; columnIndex < columns.length; columnIndex += 1) {
      const column = columns[columnIndex];
      const x = left + columnIndex * (thumbWidth + columnGap);
      let item = getItemForColumn(video, column.key);
      if (!item && column.key === "featurebuy") {
        item = findFeatureBuyFallback(video, images);
      }

      const card = figma.createFrame();
      card.name = `Cell / ${video.label || video.id} / ${column.label}`;
      card.x = x - 8;
      card.y = y - 8;
      card.resize(thumbWidth + 16, thumbHeight + 16);
      card.fills = [{ type: "SOLID", color: color("#F4F4F4") }];
      card.cornerRadius = 8;
      figma.currentPage.appendChild(card);
      nodes.push(card);

      if (!item) {
        const empty = createText(`Empty / ${video.id} / ${column.label}`, "No sample", x + 36, y + thumbHeight / 2 - 10, 15, "Regular", "#999999");
        figma.currentPage.appendChild(empty);
        nodes.push(empty);
        continue;
      }

      const payload = findImagePayload(images, item.src);
      if (!payload) {
        const missing = createText(`Missing / ${video.id} / ${column.label}`, "Missing image", x + 25, y + thumbHeight / 2 - 10, 15, "Regular", "#B00020");
        figma.currentPage.appendChild(missing);
        nodes.push(missing);
        continue;
      }

      const image = figma.createImage(new Uint8Array(payload.bytes));
      const rect = figma.createRectangle();
      rect.name = `${video.id} / ${column.label} / ${payload.name}`;
      rect.x = x;
      rect.y = y;
      rect.resize(thumbWidth, thumbHeight);
      rect.fills = [{ type: "IMAGE", imageHash: image.hash, scaleMode: "FIT" }];
      figma.currentPage.appendChild(rect);
      nodes.push(rect);

      const caption = createText(`Caption / ${video.id} / ${column.label}`, payload.name, x, y + thumbHeight + 10, 11, "Regular", "#666666");
      caption.resize(thumbWidth, 28);
      figma.currentPage.appendChild(caption);
      nodes.push(caption);
    }
  }

  figma.viewport.scrollAndZoomIntoView(nodes);
  figma.notify(`Created ${videos.length} video rows with editable image nodes.`);
}

figma.ui.onmessage = async (message) => {
  if (message.type === "cancel") {
    figma.closePlugin();
    return;
  }

  if (message.type !== "import-board") return;

  try {
    await buildBoard(message.manifest, message.images || {});
    figma.ui.postMessage({ type: "done" });
  } catch (error) {
    figma.ui.postMessage({ type: "error", message: error && error.message ? error.message : String(error) });
    figma.notify("Import failed. See plugin UI for details.", { error: true });
  }
};
