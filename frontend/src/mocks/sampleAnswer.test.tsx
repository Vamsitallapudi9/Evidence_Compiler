import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/hooks";
import { AnswerView } from "../components/AnswerView";
import { ClaimInspector } from "../components/ClaimInspector";
import { EvidenceCard } from "../components/EvidenceCard";
import { ProgressTimeline } from "../components/ProgressTimeline";
import { SourcesPanel } from "../components/SourcesPanel";
import { parseAnswer } from "../lib/parseAnswer";
import { sampleAnswer, sampleEvents, samplePages, sampleSources } from "./sampleAnswer";

const wrap = (node: React.ReactNode, client = new QueryClient()) =>
  renderToString(<QueryClientProvider client={client}>{node}</QueryClientProvider>);

describe("sample answer", () => {
  it("is internally consistent", () => {
    const a = sampleAnswer;
    const ids = new Set(a.graph.nodes.map((x) => x.id));
    for (const e of a.graph.edges) {
      expect(ids.has(e.source)).toBe(true);
      expect(ids.has(e.target)).toBe(true);
    }
    for (const c of a.claims) for (const l of c.links) expect(a.evidence[l.evidence_id]).toBeDefined();
    for (const calc of Object.values(a.calculations)) {
      for (const i of calc.inputs) expect(a.evidence[i.evidence_id]).toBeDefined();
      expect(a.evidence[calc.output_evidence_id]).toBeDefined();
    }
    const claimSegments = parseAnswer(a.text, a.claims.map((c) => c.id)).filter((s) => s.kind === "claim");
    expect(claimSegments).toHaveLength(4);
  });

  it("renders the answer view without markers", () => {
    const html = wrap(<AnswerView answer={sampleAnswer} />);
    expect(html).not.toContain("[c:");
    expect(html).toContain("Unsupported &amp; rejected");
    expect(html).toContain("Healthcare customers caused the decline.");
  });

  it("renders the inspector for every claim", () => {
    for (const c of sampleAnswer.claims) {
      const html = wrap(
        <ClaimInspector answer={sampleAnswer} target={{ kind: "claim", id: c.id }} onClose={() => {}} onSelect={() => {}} />,
      );
      expect(html).toContain("Model verifier note (not evidence)");
    }
    const eu = wrap(
      <ClaimInspector answer={sampleAnswer} target={{ kind: "claim", id: "clm_eu_cd34" }} onClose={() => {}} onSelect={() => {}} />,
    );
    expect(eu).toContain("share_of_total");
    expect(eu).toContain("$7.1M");
    expect(eu).toContain("71.0%");
  });

  it("has a web evidence item whose text location indexes into its page text", () => {
    const web = Object.values(sampleAnswer.evidence).find((e) => e.location.kind === "text");
    expect(web).toBeDefined();
    const loc = web!.location;
    if (loc.kind !== "text") throw new Error("unreachable");
    const page = samplePages[`${web!.source_ids[0]}:${loc.page}`];
    expect(page.text.slice(loc.char_start, loc.char_end)).toBe(web!.text);
    const html = wrap(<EvidenceCard evidenceId={web!.id} answer={sampleAnswer} />);
    expect(html).toContain("Document");
    expect(html).toContain("View in document");
    expect(html).not.toContain("View page");
  });

  it("links web sources in the inspector", () => {
    const html = wrap(
      <ClaimInspector answer={sampleAnswer} target={{ kind: "claim", id: "clm_int_7a8b" }} onClose={() => {}} onSelect={() => {}} />,
    );
    expect(html).toContain('href="https://www.example.com/insights/european-enterprise-software-q2-2026"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("renders the sources panel for every kind, with links and add-source forms", () => {
    const client = new QueryClient();
    client.setQueryData(queryKeys.sources, sampleSources);
    const html = wrap(<SourcesPanel />, client);
    expect(html).toContain("3 evidence</p>");
    expect(html).toContain("17 evidence · 4 sections");
    expect(html).toContain("1 table · queried via SQL · 2000 passages");
    expect(html).toContain('href="https://huggingface.co/datasets/stanfordnlp/imdb"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain("License: other");
    for (const label of ["WEB", "DOC", "HF", "Add from link", "Add Hugging Face dataset", "Add Postgres"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("Tables are queried with SQL; long text columns become searchable passages.");
  });

  it("labels the fetch stage in the progress timeline", () => {
    const html = wrap(<ProgressTimeline events={sampleEvents} running={false} />);
    expect(html).toContain("Fetching links");
    expect(html).toContain("Fetched example.com/");
    expect(html).toContain("text-amber-800");
  });
});
