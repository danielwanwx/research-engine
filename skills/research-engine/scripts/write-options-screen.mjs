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

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const args = parseArgs(process.argv.slice(2));
const screenDir = args["screen-dir"];
const topic = args.topic || "Research task";

if (!screenDir) {
  console.error(JSON.stringify({ error: "--screen-dir is required" }));
  process.exit(1);
}

fs.mkdirSync(screenDir, { recursive: true });

const html = `
<h2>Research setup</h2>
<p class="subtitle">Topic: ${escapeHtml(topic)}</p>

<div class="section">
  <div class="label">Scope</div>
  <div class="options">
    <div class="option selected" data-choice="scope:us" onclick="toggleSelect(this)">
      <div class="letter">A</div>
      <div class="content">
        <h3>United States / North America</h3>
        <p>Recommended for job market, investment, and product research focused on US demand.</p>
      </div>
    </div>
    <div class="option" data-choice="scope:global" onclick="toggleSelect(this)">
      <div class="letter">B</div>
      <div class="content">
        <h3>Global English market</h3>
        <p>Broader coverage across US, Europe, Singapore, remote, and English-language sources.</p>
      </div>
    </div>
    <div class="option" data-choice="scope:compare" onclick="toggleSelect(this)">
      <div class="letter">C</div>
      <div class="content">
        <h3>Cross-market comparison</h3>
        <p>Compare regions or segments. Useful for strategic and go-to-market questions.</p>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="label">Sources</div>
  <div class="options">
    <div class="option" data-choice="sources:public" onclick="toggleSelect(this)">
      <div class="letter">A</div>
      <div class="content">
        <h3>Official and public sources only</h3>
        <p>Cleaner evidence from public web pages, official posts, public APIs, and company pages.</p>
      </div>
    </div>
    <div class="option selected" data-choice="sources:public_community" onclick="toggleSelect(this)">
      <div class="letter">B</div>
      <div class="content">
        <h3>Public sources + community signals</h3>
        <p>Recommended. Adds forums, open-source signals, and public social discussion when available.</p>
      </div>
    </div>
    <div class="option" data-choice="sources:logged_in" onclick="toggleSelect(this)">
      <div class="letter">C</div>
      <div class="content">
        <h3>Include authorized logged-in exports</h3>
        <p>Use only read-only exports from sources you are allowed to access. No cookies or tokens.</p>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="label">Depth</div>
  <div class="options">
    <div class="option" data-choice="depth:quick" onclick="toggleSelect(this)">
      <div class="letter">A</div>
      <div class="content">
        <h3>Quick scan</h3>
        <p>Fast overview with lighter source coverage.</p>
      </div>
    </div>
    <div class="option selected" data-choice="depth:deep" onclick="toggleSelect(this)">
      <div class="letter">B</div>
      <div class="content">
        <h3>Deep research</h3>
        <p>Recommended balance of coverage, reliability, and speed.</p>
      </div>
    </div>
    <div class="option" data-choice="depth:audit" onclick="toggleSelect(this)">
      <div class="letter">C</div>
      <div class="content">
        <h3>Audit-grade review</h3>
        <p>Stricter evidence checks, more uncertainty labeling, and slower completion.</p>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="options">
    <div class="option" data-choice="run:start" onclick="toggleSelect(this)">
      <div class="letter">✓</div>
      <div class="content">
        <h3>Start research</h3>
        <p>Use the selected options. If a section is untouched, Research Engine uses the recommended default.</p>
      </div>
    </div>
  </div>
</div>
`;

const filePath = path.join(screenDir, `research-options-${Date.now()}.html`);
fs.writeFileSync(filePath, html, "utf8");
console.log(JSON.stringify({ status: "written", file: filePath }));
