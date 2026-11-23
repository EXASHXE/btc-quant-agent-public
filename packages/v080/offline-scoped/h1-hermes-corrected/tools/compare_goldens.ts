// Independent Node.js 24 TypeScript cross-language canonical JSON & SHA-256 verifier (P0-C03).
// Runs natively under Node >=22.19 / 24.13.1 without third-party dependencies.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const CONTRACT_ID = "V080_QUANT_AGENT_CONTRACT_V1";
const MAX_SAFE_JS_INT = 9007199254740991;
const PRINTABLE_ASCII_RE = /^[\x21-\x7e]{1,256}$/;
const MARKET_STATUSES = new Set([
  "EXECUTABLE",
  "WATCH",
  "INVALID",
  "NO_SETUP",
  "SOURCE_BLOCKED",
  "NOT_EVALUATED",
]);

interface GoldenCase {
  preimage: string;
  sha256: string;
  input_obj: unknown;
}

interface OracleFile {
  data: Record<string, { preimage: string; sha256: string }>;
}

function assertNoUnpairedSurrogates(text: string, pathLabel: string): void {
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        i++;
        continue;
      }
      throw new Error(`Unpaired high UTF-16 surrogate at ${pathLabel}[${i}]`);
    }
    if (code >= 0xdc00 && code <= 0xdfff) {
      throw new Error(`Unpaired low UTF-16 surrogate at ${pathLabel}[${i}]`);
    }
  }
}

function assertAsciiString(value: string, pathLabel: string): void {
  assertNoUnpairedSurrogates(value, pathLabel);
  for (let i = 0; i < value.length; i++) {
    if (value.charCodeAt(i) > 0x7f) {
      throw new Error(`Non-ASCII key/identifier forbidden at ${pathLabel}: ${JSON.stringify(value)}`);
    }
  }
}

function canonicalJson(value: unknown, pathLabel = "$"): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error(`Nonfinite number forbidden at ${pathLabel}`);
    }
    if (!Number.isInteger(value)) {
      throw new Error(`Float forbidden in canonical profile at ${pathLabel}: ${value}`);
    }
    if (Math.abs(value) > MAX_SAFE_JS_INT) {
      throw new Error(`Unsafe JS integer at ${pathLabel}: ${value}`);
    }
    return Object.is(value, -0) ? "0" : String(value);
  }
  if (typeof value === "string") {
    assertNoUnpairedSurrogates(value, pathLabel);
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    const parts = value.map((item, idx) => canonicalJson(item, `${pathLabel}[${idx}]`));
    return `[${parts.join(",")}]`;
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj);
    for (const k of keys) {
      assertAsciiString(k, `${pathLabel}.<key>`);
    }
    // Strict ASCII code-unit sort matching Python json.dumps(sort_keys=True)
    keys.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    const entries: string[] = [];
    for (const k of keys) {
      const v = obj[k];
      if (v === undefined) {
        throw new Error(`Undefined property value at ${pathLabel}.${k}`);
      }
      entries.push(`${JSON.stringify(k)}:${canonicalJson(v, `${pathLabel}.${k}`)}`);
    }
    return `{${entries.join(",")}}`;
  }
  throw new Error(`Unsupported value type at ${pathLabel}: ${typeof value}`);
}

function sha256Utf8(text: string): string {
  return createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

function computeEventId(parts: unknown[]): string {
  if (parts.length !== 7) {
    throw new Error(`Expected 7 event_id components, got ${parts.length}`);
  }
  for (let i = 0; i < parts.length; i++) {
    const item = parts[i];
    if (typeof item !== "string") {
      throw new Error(`Component ${i} must be opaque string, got ${typeof item}`);
    }
    assertNoUnpairedSurrogates(item, `event_id[${i}]`);
    if (item !== item.trim() || !PRINTABLE_ASCII_RE.test(item)) {
      throw new Error(`Component ${i} must be trimmed printable ASCII`);
    }
  }
  const [contractId, , , episodeId, , , marketStatus] = parts as string[];
  if (contractId !== CONTRACT_ID) {
    throw new Error(`Invalid contract_id: ${contractId}`);
  }
  if (episodeId.startsWith("noep:")) {
    throw new Error(`Synthetic noep: episode_id forbidden: ${episodeId}`);
  }
  if (!MARKET_STATUSES.has(marketStatus)) {
    throw new Error(`Invalid market_status: ${marketStatus}`);
  }
  return sha256Utf8(canonicalJson(parts, "event_id"));
}

function parseArgs(argv: string[]): { exportDir: string; oraclePath: string } {
  let exportDir = "";
  let oraclePath = "";
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--export-dir" && argv[i + 1]) {
      exportDir = argv[++i];
    } else if (argv[i] === "--oracle" && argv[i + 1]) {
      oraclePath = argv[++i];
    }
  }
  if (!exportDir || !oraclePath) {
    throw new Error("Usage: node tools/compare_goldens.ts --export-dir <dir> --oracle <oracle.json>");
  }
  return { exportDir: resolve(exportDir), oraclePath: resolve(oraclePath) };
}

function readJson<T>(filePath: string): T {
  return JSON.parse(readFileSync(filePath, "utf8")) as T;
}

function assertByteEqual(label: string, expectedPreimage: string, actualPreimage: string, expectedSha: string): void {
  const expectedBuf = Buffer.from(expectedPreimage, "utf8");
  const actualBuf = Buffer.from(actualPreimage, "utf8");
  if (!expectedBuf.equals(actualBuf)) {
    throw new Error(`UTF-8 preimage mismatch for ${label}\nexpected: ${expectedPreimage}\nactual:   ${actualPreimage}`);
  }
  const actualSha = createHash("sha256").update(actualBuf).digest("hex");
  if (actualSha !== expectedSha) {
    throw new Error(`SHA-256 mismatch for ${label}: expected=${expectedSha} actual=${actualSha}`);
  }
}

function main(): void {
  const { exportDir, oraclePath } = parseArgs(process.argv.slice(2));
  const oracle = readJson<OracleFile>(oraclePath);

  // 1. Verify Controller's 7 Golden Vectors match exported H1 pack byte-for-byte
  const exportedGoldens = readJson<{
    controller_cases: Record<string, GoldenCase>;
    negative_cases: Array<{ name: string; kind: string; raw_input: unknown; python_rejected: boolean }>;
  }>(resolve(exportDir, "controller_seven_goldens_verification.json"));

  const oracleKeys = Object.keys(oracle.data);
  if (oracleKeys.length !== 7) {
    throw new Error(`Expected 7 oracle cases, got ${oracleKeys.length}`);
  }
  for (const name of oracleKeys) {
    const oCase = oracle.data[name];
    const pyCase = exportedGoldens.controller_cases[name];
    if (!pyCase) {
      throw new Error(`Missing exported case ${name}`);
    }
    const tsPreimage = canonicalJson(pyCase.input_obj, name);
    assertByteEqual(`oracle:${name}`, oCase.preimage, tsPreimage, oCase.sha256);
    assertByteEqual(`exported:${name}`, pyCase.preimage, tsPreimage, pyCase.sha256);
  }

  // 2. Independently verify negative canonical/identity rejections in Node/TS
  for (const neg of exportedGoldens.negative_cases) {
    if (!neg.python_rejected) {
      throw new Error(`Negative case ${neg.name} was not rejected by Python exporter`);
    }
    let rejected = false;
    try {
      if (neg.kind === "event_id") {
        computeEventId(neg.raw_input as unknown[]);
      } else if (neg.kind === "canonical_surrogate_json_escape") {
        const parsed = JSON.parse((neg.raw_input as { raw_json_escape: string }).raw_json_escape);
        canonicalJson(parsed, neg.name);
      } else {
        canonicalJson(neg.raw_input, neg.name);
      }
    } catch {
      rejected = true;
    }
    if (!rejected) {
      throw new Error(`Node/TS comparator failed to reject negative case ${neg.name}`);
    }
  }
  // Direct runtime checks for nonfinite float, unpaired surrogate, non-ASCII object key
  for (const [label, fn] of [
    ["nan_number", () => canonicalJson({ v: Number.NaN })],
    ["float_number", () => canonicalJson({ price: 101.23 })],
    ["unpaired_surrogate", () => canonicalJson({ bad: "\ud800" })],
    ["non_ascii_key", () => canonicalJson({ 键: "值" })],
    ["numeric_card_version", () => computeEventId([CONTRACT_ID, "feishu", "ou_owner001", "abc", "c", 7 as unknown as string, "WATCH"])],
    ["whitespace_recipient", () => computeEventId([CONTRACT_ID, "feishu", " ou_owner001", "abc", "c", "jseq:1:a:b", "WATCH"])],
    ["noep_episode", () => computeEventId([CONTRACT_ID, "feishu", "ou_owner001", "noep:123", "c", "jseq:1:a:b", "NO_SETUP"])],
  ] as const) {
    let failed = false;
    try {
      fn();
    } catch {
      failed = true;
    }
    if (!failed) {
      throw new Error(`Node runtime canonical guard failed to reject ${label}`);
    }
  }

  // 3. Verify all exported reference facade envelopes, version invariance, and rendered event IDs
  const envelopes = readJson<{ cases: Record<string, { envelope: unknown; canonical_preimage: string; sha256: string }> }>(
    resolve(exportDir, "facade_envelopes.json"),
  );
  let envelopeCount = 0;
  for (const [caseName, entry] of Object.entries(envelopes.cases)) {
    const tsPre = canonicalJson(entry.envelope, `envelope:${caseName}`);
    assertByteEqual(`envelope:${caseName}`, entry.canonical_preimage, tsPre, entry.sha256);
    envelopeCount++;
  }

  const versionReplay = readJson<{
    before_unrelated_event: { watch_card_version: string; exec_card_version: string; watch_event_id: string };
    after_unrelated_event: { watch_card_version: string; exec_card_version: string; watch_event_id: string };
  }>(resolve(exportDir, "version_invariance_replay.json"));
  if (
    versionReplay.before_unrelated_event.watch_card_version !== versionReplay.after_unrelated_event.watch_card_version ||
    versionReplay.before_unrelated_event.exec_card_version !== versionReplay.after_unrelated_event.exec_card_version ||
    versionReplay.before_unrelated_event.watch_event_id !== versionReplay.after_unrelated_event.watch_event_id
  ) {
    throw new Error("Version invariance replay check failed");
  }

  const renderedPack = readJson<{
    cards: Array<{ label: string; rendered_utf8: string; rendered_sha256: string; event_id_components: string[] | null; event_id: string | null }>;
  }>(resolve(exportDir, "rendered_cards_and_event_ids.json"));
  for (const item of renderedPack.cards) {
    const rSha = sha256Utf8(item.rendered_utf8);
    if (rSha !== item.rendered_sha256) {
      throw new Error(`Rendered SHA mismatch for ${item.label}`);
    }
    if (item.event_id_components) {
      const tsEid = computeEventId(item.event_id_components);
      if (tsEid !== item.event_id) {
        throw new Error(`Event ID mismatch for ${item.label}: expected=${item.event_id} actual=${tsEid}`);
      }
    }
  }

  // 4. Verify export manifest hashes match raw files on disk
  const manifest = readJson<{ files: Array<{ path: string; bytes: number; sha256: string }> }>(
    resolve(exportDir, "REFERENCE_EXPORT_MANIFEST.json"),
  );
  for (const row of manifest.files) {
    const buf = readFileSync(resolve(exportDir, row.path));
    if (buf.length !== row.bytes) {
      throw new Error(`Manifest byte length mismatch for ${row.path}`);
    }
    const sha = createHash("sha256").update(buf).digest("hex");
    if (sha !== row.sha256) {
      throw new Error(`Manifest SHA mismatch for ${row.path}`);
    }
  }

  console.log(
    JSON.stringify({
      status: "CROSS_LANGUAGE_MATCH_OK",
      node_version: process.version,
      oracle_cases_matched: oracleKeys.length,
      negative_rejections_verified: exportedGoldens.negative_cases.length + 7,
      facade_envelopes_matched: envelopeCount,
      rendered_items_matched: renderedPack.cards.length,
      manifest_files_verified: manifest.files.length,
    }),
  );
}

main();
