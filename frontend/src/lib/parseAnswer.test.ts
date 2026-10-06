import { describe, expect, it } from "vitest";
import { parseAnswer, stripMarkers } from "./parseAnswer";

const ids = ["clm_ab12", "clm_cd34", "clm_x"];

describe("parseAnswer", () => {
  it("attaches each marker to the sentence before it and hides markers", () => {
    const text =
      "Q2 revenue declined 8.4% [c:clm_ab12]. Europe accounted for about 71% of the decline [c:clm_cd34].";
    expect(parseAnswer(text, ids)).toEqual([
      { kind: "claim", text: "Q2 revenue declined 8.4%", claimIds: ["clm_ab12"] },
      { kind: "text", text: ". " },
      { kind: "claim", text: "Europe accounted for about 71% of the decline", claimIds: ["clm_cd34"] },
      { kind: "text", text: "." },
    ]);
  });

  it("only spans the final sentence when earlier unmarked sentences precede a marker", () => {
    const text = "Some context here. Revenue fell 8.4% [c:clm_ab12].";
    expect(parseAnswer(text, ids)).toEqual([
      { kind: "text", text: "Some context here. " },
      { kind: "claim", text: "Revenue fell 8.4%", claimIds: ["clm_ab12"] },
      { kind: "text", text: "." },
    ]);
  });

  it("keeps dangling punctuation outside a phrase-level span", () => {
    const text = "Revenue fell [c:clm_ab12], mostly in Europe [c:clm_cd34].";
    expect(parseAnswer(text, ids)).toEqual([
      { kind: "claim", text: "Revenue fell", claimIds: ["clm_ab12"] },
      { kind: "text", text: ", " },
      { kind: "claim", text: "mostly in Europe", claimIds: ["clm_cd34"] },
      { kind: "text", text: "." },
    ]);
  });

  it("ignores unknown claim ids gracefully, leaving the text plain", () => {
    const text = "Revenue fell [c:clm_missing]. Europe led [c:clm_cd34].";
    const segments = parseAnswer(text, ids);
    expect(segments).toEqual([
      { kind: "text", text: "Revenue fell. " },
      { kind: "claim", text: "Europe led", claimIds: ["clm_cd34"] },
      { kind: "text", text: "." },
    ]);
    expect(segments.map((s) => s.text).join("")).not.toContain("[c:");
  });

  it("merges adjacent markers onto the same span", () => {
    expect(parseAnswer("Revenue fell [c:clm_ab12][c:clm_cd34] [c:clm_x].", ids)).toEqual([
      { kind: "claim", text: "Revenue fell", claimIds: ["clm_ab12", "clm_cd34", "clm_x"] },
      { kind: "text", text: "." },
    ]);
  });

  it("supports comma-separated ids inside one marker", () => {
    expect(parseAnswer("Revenue fell [c:clm_ab12, clm_missing,clm_cd34].", ids)).toEqual([
      { kind: "claim", text: "Revenue fell", claimIds: ["clm_ab12", "clm_cd34"] },
      { kind: "text", text: "." },
    ]);
  });

  it("returns a single text segment when there are no markers", () => {
    expect(parseAnswer("No claims here.", ids)).toEqual([{ kind: "text", text: "No claims here." }]);
    expect(parseAnswer("", ids)).toEqual([]);
  });

  it("does not treat decimals as sentence boundaries and handles paragraphs", () => {
    const text = "Intro paragraph.\n\nMargin was 61.2% [c:clm_x].";
    expect(parseAnswer(text, ids)).toEqual([
      { kind: "text", text: "Intro paragraph.\n\n" },
      { kind: "claim", text: "Margin was 61.2%", claimIds: ["clm_x"] },
      { kind: "text", text: "." },
    ]);
  });

  it("round-trips the prose with markers removed", () => {
    const text = "A [c:clm_ab12]. B [c:unknown]. C [c:clm_cd34].";
    const joined = parseAnswer(text, ids)
      .map((s) => s.text)
      .join("");
    expect(joined).toBe(stripMarkers(text));
    expect(joined).toBe("A. B. C.");
  });
});
