import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import YAML from "yaml";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_CONFIG = path.resolve(__dirname, "..", "config.yaml");

export function loadConfig(configPath = DEFAULT_CONFIG) {
  if (!fs.existsSync(configPath)) {
    return {
      api: { baseUrl: "http://127.0.0.1:10102" },
      audio: { ffmpegPath: "", tmpDir: "" }
    };
  }
  const raw = fs.readFileSync(configPath, "utf-8");
  const data = YAML.parse(raw) || {};
  const api = data.api || {};
  const audio = data.audio || {};
  return {
    api: { baseUrl: api.baseUrl || "http://127.0.0.1:10102" },
    audio: {
      ffmpegPath: audio.ffmpegPath || "",
      tmpDir: audio.tmpDir || ""
    }
  };
}

export function flattenSpeakers(speakers) {
  if (!Array.isArray(speakers)) {
    return [];
  }
  const items = [];
  for (const speaker of speakers) {
    const name = speaker?.name || "unknown";
    const styles = Array.isArray(speaker?.styles) ? speaker.styles : [];
    for (const style of styles) {
      items.push({
        id: style.id,
        name,
        styleName: style.name || "default",
        label: `${name} / ${style.name || "default"}`
      });
    }
  }
  return items;
}

export async function fetchSpeakers(baseUrl) {
  const res = await fetch(`${baseUrl}/speakers`);
  if (!res.ok) {
    throw new Error(`speakers failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function audioQuery(baseUrl, text, speakerId) {
  const url = new URL(`${baseUrl}/audio_query`);
  url.searchParams.set("text", text);
  url.searchParams.set("speaker", String(speakerId));
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) {
    throw new Error(`audio_query failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function synthesis(baseUrl, query, speakerId) {
  const url = new URL(`${baseUrl}/synthesis`);
  url.searchParams.set("speaker", String(speakerId));
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query)
  });
  if (!res.ok) {
    throw new Error(`synthesis failed: ${res.status} ${res.statusText}`);
  }
  const buf = await res.arrayBuffer();
  return Buffer.from(buf);
}

export function ensureDir(dirPath) {
  if (!dirPath) {
    return;
  }
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

