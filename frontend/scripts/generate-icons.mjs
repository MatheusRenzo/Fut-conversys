import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";

const ICON_DIR = path.join(process.cwd(), "public", "icons");
const SOURCE = path.join(ICON_DIR, "fut-conversys-logo.png");
const BG = { r: 4, g: 30, b: 66, alpha: 1 }; // #041E42

async function renderIcon(size, logoScale, outName) {
  const logoSize = Math.round(size * logoScale);
  const logoBuffer = await sharp(SOURCE)
    .trim({ threshold: 12 })
    .resize(logoSize, logoSize, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer();

  await sharp({
    create: {
      width: size,
      height: size,
      channels: 4,
      background: BG,
    },
  })
    .composite([{ input: logoBuffer, gravity: "center" }])
    .png({ compressionLevel: 9 })
    .toFile(path.join(ICON_DIR, outName));

  console.log(`wrote ${outName} (${size}x${size}, scale ${Math.round(logoScale * 100)}%)`);
}

async function main() {
  if (!fs.existsSync(SOURCE)) {
    throw new Error(`Source logo not found: ${SOURCE}`);
  }

  await renderIcon(32, 0.82, "favicon-32.png");
  await renderIcon(180, 0.88, "apple-touch-icon.png");
  await renderIcon(192, 0.88, "fut-conversys-192.png");
  await renderIcon(512, 0.88, "fut-conversys-512.png");
  await renderIcon(512, 0.72, "fut-conversys-maskable.png");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
