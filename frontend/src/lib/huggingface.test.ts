import { describe, expect, it } from "vitest";
import { normalizeHfDataset } from "./huggingface";

describe("normalizeHfDataset", () => {
  it("accepts plain owner/name and legacy single names", () => {
    expect(normalizeHfDataset("stanfordnlp/imdb")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("  openai/gsm8k  ")).toBe("openai/gsm8k");
    expect(normalizeHfDataset("allenai/c4.en-v1_2")).toBe("allenai/c4.en-v1_2");
    expect(normalizeHfDataset("imdb")).toBe("imdb");
    expect(normalizeHfDataset("datasets/stanfordnlp/imdb")).toBe("stanfordnlp/imdb");
  });

  it("extracts owner/name from full hub URLs", () => {
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb/")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("http://www.huggingface.co/datasets/stanfordnlp/imdb")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("huggingface.co/datasets/stanfordnlp/imdb")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("https://hf.co/datasets/stanfordnlp/imdb")).toBe("stanfordnlp/imdb");
  });

  it("strips /tree/main, viewer paths, query strings and fragments", () => {
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb/tree/main")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb/tree/main/plain_text")).toBe(
      "stanfordnlp/imdb",
    );
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb/viewer/plain_text/train")).toBe(
      "stanfordnlp/imdb",
    );
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb?row=3&split=test")).toBe(
      "stanfordnlp/imdb",
    );
    expect(normalizeHfDataset("https://huggingface.co/datasets/stanfordnlp/imdb#dataset-card")).toBe("stanfordnlp/imdb");
    expect(normalizeHfDataset("https://huggingface.co/datasets/imdb/tree/main")).toBe("imdb");
  });

  it("rejects invalid input", () => {
    expect(normalizeHfDataset("")).toBeNull();
    expect(normalizeHfDataset("   ")).toBeNull();
    expect(normalizeHfDataset("owner/name/extra")).toBeNull();
    expect(normalizeHfDataset("owner/")).toBeNull();
    expect(normalizeHfDataset("/name")).toBeNull();
    expect(normalizeHfDataset("has space/name")).toBeNull();
    expect(normalizeHfDataset("owner/na#me")).toBeNull();
    // Models and spaces are not datasets.
    expect(normalizeHfDataset("https://huggingface.co/bert-base-uncased")).toBeNull();
    expect(normalizeHfDataset("https://huggingface.co/spaces/owner/app")).toBeNull();
    expect(normalizeHfDataset("https://huggingface.co/datasets")).toBeNull();
    // Other hosts and schemes.
    expect(normalizeHfDataset("https://example.com/datasets/owner/name")).toBeNull();
    expect(normalizeHfDataset("ftp://huggingface.co/datasets/owner/name")).toBeNull();
    expect(normalizeHfDataset("javascript:alert(1)")).toBeNull();
  });
});
