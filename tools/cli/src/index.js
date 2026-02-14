import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import readline from "node:readline/promises";
import { spawnSync } from "node:child_process";

import {
  audioQuery,
  ensureDir,
  fetchSpeakers,
  flattenSpeakers,
  loadConfig,
  synthesis
} from "./lib.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function usage() {
  console.log(
    [
      "Usage:",
      "  node src/index.js list",
      "  node src/index.js play --speaker-id 4 --text \"hello\"",
      "  node src/index.js save --speaker-id 4 --text \"hello\" --out \"path/to/file.mp3\"",
      "Options:",
      "  --config path/to/config.yaml"
    ].join("\n")
  );
}

function getArgValue(args, key) {
  const idx = args.indexOf(key);
  if (idx === -1 || idx === args.length - 1) {
    return null;
  }
  return args[idx + 1];
}

async function promptSelectSpeaker(items) {
  if (items.length === 0) {
    throw new Error("No speakers available.");
  }
  items.forEach((item, idx) => {
    console.log(`${idx + 1}. ${item.label} (id: ${item.id})`);
  });
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const answer = await rl.question("Select speaker (number): ");
  rl.close();
  const pick = Number.parseInt(answer, 10);
  if (!Number.isFinite(pick) || pick < 1 || pick > items.length) {
    throw new Error("Invalid selection.");
  }
  return items[pick - 1];
}

function writeTempWav(tmpDir, buffer) {
  const dir = tmpDir || path.join(os.tmpdir(), "qwen3tts-cli");
  ensureDir(dir);
  const filename = `speech_${Date.now()}.wav`;
  const filePath = path.join(dir, filename);
  fs.writeFileSync(filePath, buffer);
  return filePath;
}

function playWav(filePath) {
  const ps = [
    "[System.Media.SoundPlayer]::new(",
    "'",
    filePath,
    "'",
    ").PlaySync()"
  ].join("");
  spawnSync("powershell", ["-NoLogo", "-Command", ps], { stdio: "inherit" });
}

function resolveFfmpegPath(cfg) {
  if (cfg.audio.ffmpegPath && fs.existsSync(cfg.audio.ffmpegPath)) {
    return cfg.audio.ffmpegPath;
  }
  return null;
}

function wavToMp3(ffmpegPath, wavPath, outPath) {
  const args = ["-y", "-i", wavPath, "-codec:a", "libmp3lame", "-q:a", "2", outPath];
  const res = spawnSync(ffmpegPath, args, { stdio: "inherit" });
  if (res.status !== 0) {
    throw new Error("ffmpeg failed.");
  }
}

async function run() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    usage();
    process.exit(1);
  }

  const configPath = getArgValue(args, "--config") || path.resolve(__dirname, "..", "config.yaml");
  const cfg = loadConfig(configPath);
  const baseUrl = cfg.api.baseUrl;

  const cmd = args[0];
  if (cmd === "list") {
    const speakers = await fetchSpeakers(baseUrl);
    const items = flattenSpeakers(speakers);
    items.forEach((item) => {
      console.log(`${item.id}\t${item.label}`);
    });
    return;
  }

  if (cmd !== "play" && cmd !== "save") {
    usage();
    process.exit(1);
  }

  const text = getArgValue(args, "--text");
  if (!text) {
    throw new Error("--text is required");
  }

  let speakerId = getArgValue(args, "--speaker-id");
  if (!speakerId) {
    const speakers = await fetchSpeakers(baseUrl);
    const items = flattenSpeakers(speakers);
    const selected = await promptSelectSpeaker(items);
    speakerId = String(selected.id);
  }

  const query = await audioQuery(baseUrl, text, speakerId);
  const wavBuffer = await synthesis(baseUrl, query, speakerId);
  const wavPath = writeTempWav(cfg.audio.tmpDir, wavBuffer);

  if (cmd === "play") {
    playWav(wavPath);
    return;
  }

  const outPath = getArgValue(args, "--out");
  if (!outPath) {
    throw new Error("--out is required for save");
  }
  const ffmpegPath = resolveFfmpegPath(cfg);
  if (!ffmpegPath) {
    throw new Error("ffmpegPath is not set or not found.");
  }
  wavToMp3(ffmpegPath, wavPath, outPath);
  console.log(`Saved: ${outPath}`);
}

run().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
