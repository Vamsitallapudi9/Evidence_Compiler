import { describe, expect, it } from "vitest";
import type { SourceOut } from "../api/types";
import {
  displayRow,
  formatCallSeconds,
  formatCost,
  formatDuration,
  formatTokens,
  formatTokensCompact,
  displayUrl,
  formatFieldValue,
  formatLocation,
  formatUsd,
  formatValue,
  humanize,
  isDocumentKind,
  isHttpUrl,
  opLabel,
  parseDecimal,
  sourceKindLabel,
  sourceSubtitle,
} from "./format";
import { findHighlight, splitAt } from "./highlight";

describe("parseDecimal", () => {
  it("parses decimal strings", () => {
    expect(parseDecimal("71.0000")).toBe(71);
    expect(parseDecimal("-6200000")).toBe(-6200000);
    expect(parseDecimal("1,234.5")).toBe(1234.5);
    expect(parseDecimal(" 3 ")).toBe(3);
  });
  it("returns null for non-numbers", () => {
    expect(parseDecimal("abc")).toBeNull();
    expect(parseDecimal("")).toBeNull();
    expect(parseDecimal("NaN")).toBeNull();
    expect(parseDecimal(null)).toBeNull();
  });
});

describe("formatValue", () => {
  it("formats percentages with one decimal", () => {
    expect(formatValue("71", "%")).toBe("71.0%");
    expect(formatValue("-8.3822296730930427", "%")).toBe("-8.4%");
  });
  it("formats USD with $ and abbreviations", () => {
    expect(formatValue("7100000", "USD")).toBe("$7.1M");
    expect(formatValue("10000000", "USD")).toBe("$10M");
    expect(formatValue("1250000000", "USD")).toBe("$1.25B");
    expect(formatValue("-6200000", "USD")).toBe("-$6.2M");
    expect(formatValue("950", "USD")).toBe("$950");
    expect(formatValue("12.5", "USD")).toBe("$12.5");
  });
  it("formats other units and unitless values", () => {
    expect(formatValue("1234.5", "units")).toBe("1,234.5 units");
    expect(formatValue("0.7100", null)).toBe("0.71");
    expect(formatValue("2", undefined)).toBe("2");
  });
  it("passes through unparsable values", () => {
    expect(formatValue("n/a", "%")).toBe("n/a");
  });
});

describe("formatUsd", () => {
  it("rolls up when rounding would reach the next unit", () => {
    expect(formatUsd(999_999)).toBe("$1M");
    expect(formatUsd(45_300)).toBe("$45.3K");
  });
});

describe("formatLocation", () => {
  it("formats pdf locations", () => {
    expect(formatLocation({ kind: "pdf", page: 12, char_start: 0, char_end: 10 })).toBe("Page 12");
    expect(
      formatLocation({ kind: "pdf", page: 3, char_start: 0, char_end: 1, table_index: 0, row_index: 2 }),
    ).toBe("Page 3, table 1, row 3");
  });
  it("formats table locations (0-based rows shown 1-based)", () => {
    expect(formatLocation({ kind: "table", table: "regional_sales", row_index: 4, columns: [] })).toBe(
      "regional_sales, row 5",
    );
    expect(formatLocation({ kind: "table", table: "t", sheet: "Q2", row_index: 0, columns: [] })).toBe(
      "Q2 / t, row 1",
    );
    expect(displayRow(0)).toBe(1);
  });
  it("formats query and calc locations", () => {
    expect(
      formatLocation({
        kind: "query",
        engine: "duckdb",
        sql: "select 1",
        tables: [],
        executed_at: "",
        row_count: 3,
        row_index: 0,
      }),
    ).toBe("SQL result row 1 of 3 rows (duckdb)");
    expect(formatLocation({ kind: "calc", calculation_id: "calc_1" })).toBe("Calculation calc_1");
  });
});

describe("formatLocation for text (web / docx / text) sources", () => {
  const loc = { kind: "text", page: 1, char_start: 10, char_end: 42 } as const;
  it("shows the section when the source has several", () => {
    expect(formatLocation({ ...loc, page: 3 }, { pageCount: 5 })).toBe("Section 3");
    expect(formatLocation(loc, { pageCount: 2 })).toBe("Section 1");
    // A section number above 1 implies multiple sections even if the count is unknown.
    expect(formatLocation({ ...loc, page: 2 })).toBe("Section 2");
  });
  it("falls back to the source name or 'Document' for single-section sources", () => {
    expect(formatLocation(loc)).toBe("Document");
    expect(formatLocation(loc, { pageCount: 1 })).toBe("Document");
    expect(formatLocation(loc, { pageCount: 1, sourceName: "example.com/report" })).toBe("example.com/report");
  });
  it("still formats huggingface dataset rows as table rows", () => {
    expect(formatLocation({ kind: "table", table: "imdb_train", row_index: 41, columns: ["text", "label"] })).toBe(
      "imdb_train, row 42",
    );
  });
});

describe("sources", () => {
  const base: Pick<SourceOut, "kind" | "evidence_count" | "tables" | "page_count"> = {
    kind: "pdf",
    evidence_count: 23,
    tables: [],
    page_count: null,
  };
  it("labels every source kind", () => {
    expect(["pdf", "csv", "xlsx", "postgres", "web", "docx", "text", "huggingface"].map(sourceKindLabel)).toEqual([
      "PDF",
      "CSV",
      "XLSX",
      "PG",
      "WEB",
      "DOC",
      "TXT",
      "HF",
    ]);
    expect(sourceKindLabel("parquet")).toBe("PARQUET");
  });
  it("treats web/docx/text like PDFs (documents)", () => {
    expect(isDocumentKind("web") && isDocumentKind("docx") && isDocumentKind("text") && isDocumentKind("pdf")).toBe(true);
    expect(isDocumentKind("huggingface") || isDocumentKind("csv")).toBe(false);
    expect(sourceSubtitle({ ...base, page_count: 6 })).toBe("23 evidence · 6 pages");
    expect(sourceSubtitle({ ...base, kind: "web", page_count: 1 })).toBe("23 evidence");
    expect(sourceSubtitle({ ...base, kind: "web" })).toBe("23 evidence");
    expect(sourceSubtitle({ ...base, kind: "docx", evidence_count: 17, page_count: 4 })).toBe("17 evidence · 4 sections");
    expect(sourceSubtitle({ ...base, kind: "text", evidence_count: 1 })).toBe("1 evidence");
  });
  it("describes tabular sources by their tables", () => {
    expect(sourceSubtitle({ ...base, kind: "csv", evidence_count: 48, tables: ["regional_sales"] })).toBe(
      "1 table · queried via SQL",
    );
    expect(sourceSubtitle({ ...base, kind: "postgres", evidence_count: 0, tables: ["a", "b"] })).toBe(
      "2 tables · queried via SQL",
    );
  });
  it("adds passages for huggingface datasets with indexed text", () => {
    expect(sourceSubtitle({ ...base, kind: "huggingface", evidence_count: 0, tables: ["imdb_train"] })).toBe(
      "1 table · queried via SQL",
    );
    expect(sourceSubtitle({ ...base, kind: "huggingface", evidence_count: 2000, tables: ["imdb_train", "imdb_test"] })).toBe(
      "2 tables · queried via SQL · 2000 passages",
    );
    expect(sourceSubtitle({ ...base, kind: "huggingface", evidence_count: 1, tables: ["t"] })).toBe(
      "1 table · queried via SQL · 1 passage",
    );
  });
  it("formats and validates URLs", () => {
    expect(displayUrl("https://www.example.com/a/report.pdf")).toBe("example.com/a/report.pdf");
    expect(displayUrl("https://huggingface.co/datasets/stanfordnlp/imdb/")).toBe("huggingface.co/datasets/stanfordnlp/imdb");
    expect(isHttpUrl("https://example.com")).toBe(true);
    expect(isHttpUrl("http://localhost:8000/x")).toBe(true);
    expect(isHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpUrl("file://data/x.pdf")).toBe(false);
    expect(isHttpUrl(null)).toBe(false);
  });
});

describe("misc helpers", () => {
  it("formats field values", () => {
    expect(formatFieldValue(null)).toBe("—");
    expect(formatFieldValue(true)).toBe("true");
    expect(formatFieldValue(48200000)).toBe("48,200,000");
    expect(formatFieldValue("Europe")).toBe("Europe");
  });
  it("labels ops and humanizes names", () => {
    expect(opLabel("share_of_total")).toBe("Share of total");
    expect(opLabel("unknown_op")).toBe("unknown_op");
    expect(humanize("numbers_match")).toBe("Numbers match");
  });
});

describe("findHighlight", () => {
  const text = "Total revenue was $109.3 million, a decrease of 8.4%.";
  it("uses a valid quote_span", () => {
    expect(findHighlight(text, null, [0, 5])).toEqual([0, 5]);
  });
  it("falls back to locating the quote", () => {
    expect(findHighlight(text, "a decrease of 8.4%", [999, 1000])).toEqual([34, 52]);
    expect(findHighlight(text, "TOTAL REVENUE")).toEqual([0, 13]);
  });
  it("returns null when nothing matches", () => {
    expect(findHighlight(text, "not present")).toBeNull();
    expect(findHighlight(text)).toBeNull();
  });
  it("splits text around a span", () => {
    expect(splitAt("abcdef", [2, 4])).toEqual(["ab", "cd", "ef"]);
    expect(splitAt("abc", [2, 99])).toEqual(["ab", "c", ""]);
  });
});

describe("usage formatting", () => {
  it("formats token counts", () => {
    expect(formatTokens(0)).toBe("0");
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(12345)).toBe("12,345");
    expect(formatTokens(999_999)).toBe("999,999");
    expect(formatTokens(1_234_567)).toBe("1.2M");
    expect(formatTokens(null)).toBe("—");
  });
  it("formats compact token counts", () => {
    expect(formatTokensCompact(950)).toBe("950");
    expect(formatTokensCompact(48_213)).toBe("48.2k");
    expect(formatTokensCompact(6_100)).toBe("6.1k");
    expect(formatTokensCompact(482_000)).toBe("482k");
    expect(formatTokensCompact(999_700)).toBe("1M");
    expect(formatTokensCompact(1_250_000)).toBe("1.3M");
  });
  it("formats durations as m:ss", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(7.9)).toBe("0:07");
    expect(formatDuration(92)).toBe("1:32");
    expect(formatDuration(3723)).toBe("1:02:03");
    expect(formatDuration(-5)).toBe("0:00");
    expect(formatDuration(null)).toBe("0:00");
    expect(formatCallSeconds(0.84)).toBe("0.8s");
    expect(formatCallSeconds(28.4)).toBe("28s");
    expect(formatCallSeconds(92)).toBe("1:32");
  });
  it("formats estimated cost", () => {
    expect(formatCost(0.031)).toBe("$0.031");
    expect(formatCost(0.04)).toBe("$0.04");
    expect(formatCost(0.0412)).toBe("$0.041");
    expect(formatCost(0.25)).toBe("$0.25");
    expect(formatCost(12.4)).toBe("$12.40");
    expect(formatCost(0.0004)).toBe("<$0.001");
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(null)).toBe("—");
  });
});
