#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value.startsWith("--")) {
      args[value.slice(2)] = argv[index + 1] || "";
      index += 1;
    }
  }
  return args;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readEvents(eventsFile) {
  if (!fs.existsSync(eventsFile)) {
    return [];
  }
  return fs
    .readFileSync(eventsFile, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function selectionFromEvents(events) {
  const selected = {
    scope: "us",
    sources: "public_community",
    depth: "deep",
    ready: false,
    event_count: events.length,
  };

  for (const event of events) {
    const choice = String(event.choice || event.value || "");
    const [key, value] = choice.split(":", 2);
    if (key === "scope" && value) selected.scope = value;
    if (key === "sources" && value) selected.sources = value;
    if (key === "depth" && value) selected.depth = value;
    if (choice === "run:start") selected.ready = true;
  }
  return selected;
}

const args = parseArgs(process.argv.slice(2));
const stateDir = args["state-dir"];
const waitMs = Number(args["wait-ms"] || 0);

if (!stateDir) {
  console.error(JSON.stringify({ error: "--state-dir is required" }));
  process.exit(1);
}

const eventsFile = path.join(stateDir, "events");
const start = Date.now();

while (true) {
  const events = readEvents(eventsFile);
  const selection = selectionFromEvents(events);
  if (selection.ready || waitMs <= 0 || Date.now() - start >= waitMs) {
    selection.timed_out = !selection.ready && waitMs > 0;
    console.log(JSON.stringify(selection, null, 2));
    process.exit(selection.ready || waitMs <= 0 ? 0 : 2);
  }
  await sleep(250);
}
