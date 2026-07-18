from __future__ import annotations

import json
import re
from pathlib import Path

from app.agents.base import LLMAgent
from app.domain.schemas import KnowledgeBundle, PaperKnowledge, PaperMetadata
from app.services.llm import LLMClient

_SYSTEM = """\
You are a specialist in analyzing computer vision research papers.
Your task is to extract ALL technically relevant information from the provided paper text.

FOCUS AREAS (this is a computer vision paper — extract CV-specific details):
- Model architecture: every named module, layer type, attention mechanism, backbone
- Loss functions: exact names (e.g., "focal loss", "dice loss", "contrastive loss")
- Preprocessing pipeline: resize, normalize, augment steps
- Postprocessing: NMS, softmax, argmax, connected components, etc.
- Hyperparameters: learning rate, batch size, input resolution, number of classes
- External libraries: PyTorch, torchvision, OpenCV, mmcv, detectron2, etc.
- Pseudocode / algorithm blocks
- Equations

Return a SINGLE valid JSON object with these exact keys:
{
  "title": "string",
  "authors": ["string"],
  "abstract": "string",
  "problem_statement": "string",
  "contributions": ["string"],
  "methodology": ["string"],
  "architecture": ["string — each named architectural component"],
  "backbone": "string or null",
  "loss_functions": ["string"],
  "training_procedure": ["string"],
  "hyperparameters": {"key": "value"},
  "implementation_notes": ["string"],
  "preprocessing": ["string"],
  "postprocessing": ["string"],
  "inference_pipeline": ["string"],
  "external_libraries": ["string"],
  "pseudocode": ["string"],
  "equations": ["string"],
  "figures": ["string"],
  "tables": ["string"],
  "pipeline": ["string"],
  "algorithms": ["string"]
}

Return ONLY the JSON object. No markdown, no explanation.\
"""


class PaperParserAgent(LLMAgent):
    """
    Parses a research paper PDF into a structured KnowledgeBundle.

    Strategy:
    1. Extract raw text via pypdf (I/O — not LLM's job)
    2. Send chunked text to Qwen3-8B with a structured extraction prompt
    3. Parse JSON response into PaperKnowledge
    4. Fallback to regex heuristics if LLM fails or returns incomplete data
    """

    name = "parser"

    def __init__(self, llm: LLMClient | None = None) -> None:
        super().__init__(llm)

    def run(self, pdf_path: Path) -> KnowledgeBundle:
        self.log.info("parsing_pdf", path=str(pdf_path))
        text, pages = self._extract_text(pdf_path)

        # LLM extraction — fallback heuristics fill any gaps below
        llm_knowledge = self._llm_extract(text, pdf_path.name)

        # Fill in fields using regex/heuristics fallbacks
        self._fill_fallbacks(llm_knowledge, text)

        knowledge = PaperKnowledge(
            metadata=PaperMetadata(
                title=llm_knowledge.get("title") or self._title(text),
                authors=llm_knowledge.get("authors") or [],
                abstract=llm_knowledge.get("abstract") or self._section(text, "abstract", ["introduction"]),
                source_filename=pdf_path.name,
                page_count=pages,
            ),
            problem_statement=llm_knowledge.get("problem_statement") or "",
            contributions=llm_knowledge.get("contributions") or [],
            methodology=llm_knowledge.get("methodology") or [],
            architecture=llm_knowledge.get("architecture") or self._architecture(text),
            pipeline=llm_knowledge.get("pipeline") or [],
            algorithms=llm_knowledge.get("algorithms") or [],
            equations=llm_knowledge.get("equations") or re.findall(r"(?m)^\s*(?:Eq\.?\s*)?\(?\d+\)?\s*[:=].+$", text)[:20],
            figures=llm_knowledge.get("figures") or re.findall(r"(?i)fig(?:ure)?\.?\s+\d+[:. \-].{0,180}", text)[:30],
            tables=llm_knowledge.get("tables") or re.findall(r"(?i)table\s+\d+[:. \-].{0,180}", text)[:20],
            backbone=llm_knowledge.get("backbone") or self._detect_backbone(text),
            loss_functions=llm_knowledge.get("loss_functions") or self._find_terms(
                text, ["cross entropy", "dice loss", "focal loss", "contrastive loss", "triplet loss", "l1 loss", "l2 loss", "mse loss", "bce loss"]
            ),
            training_procedure=llm_knowledge.get("training_procedure") or [],
            hyperparameters=self._sanitize_hyperparams(
                llm_knowledge.get("hyperparameters") or self._hyperparameters(text)
            ),
            implementation_notes=llm_knowledge.get("implementation_notes") or [],
            preprocessing=llm_knowledge.get("preprocessing") or self._find_terms(
                text, ["resize", "crop", "normalize", "augmentation", "flip", "color jitter", "random erasing"]
            ),
            postprocessing=llm_knowledge.get("postprocessing") or self._find_terms(
                text, ["nms", "threshold", "softmax", "argmax", "connected components", "morphological"]
            ),
            inference_pipeline=llm_knowledge.get("inference_pipeline") or [],
            external_libraries=llm_knowledge.get("external_libraries") or self._find_terms(
                text, ["pytorch", "torchvision", "opencv", "numpy", "scipy", "detectron", "mmcv", "mmdetection"]
            ) or ["torch", "torchvision", "opencv-python"],
            dependencies=["python>=3.11", "torch", "torchvision", "numpy", "opencv-python", "pydantic"],
            folder_structure=re.findall(r"(?m)^\s*(?:[A-Za-z0-9_\-]+/){1,3}[A-Za-z0-9_\-.]*", text)[:20],
            pseudocode=llm_knowledge.get("pseudocode") or re.findall(r"(?is)algorithm\s+\d+.*?(?=\n\s*(?:algorithm\s+\d+|figure|table|references)|\Z)", text)[:5],
            appendix=self._sentences(self._section(text, "appendix", ["references"]), 8),
            raw_text=text,
        )

        self.log.info(
            "parsing_complete",
            title=knowledge.metadata.title,
            architecture_count=len(knowledge.architecture),
            loss_count=len(knowledge.loss_functions),
            llm_used=False,
        )
        return KnowledgeBundle(paper=knowledge, artifacts={"raw_text_chars": len(text), "pages": pages})

    # ------------------------------------------------------------------
    # LLM extraction
    # ------------------------------------------------------------------

    def _llm_extract(self, text: str, filename: str) -> dict:
        """Send paper text to LLM for structured extraction. Returns parsed dict."""
        # Chunk: send first 12000 chars (covers abstract, intro, method — most important)
        chunk = self._truncate(text, max_chars=12000)
        user = f"Research paper filename: {filename}\n\nPaper text:\n{chunk}"
        try:
            result = self._ask_json(_SYSTEM, user)
            self.log.info("llm_extraction_ok", fields=list(result.keys()))
            return result
        except Exception as exc:
            self.log.warning("llm_extraction_failed", error=str(exc))
            return {}

    # ------------------------------------------------------------------
    # Fallback enrichment — fill missing LLM fields with regex heuristics
    # ------------------------------------------------------------------

    def _fill_fallbacks(self, llm_data: dict, text: str) -> None:
        """Enrich llm_data in-place with regex results for any empty list fields."""
        if not llm_data.get("architecture"):
            llm_data["architecture"] = self._architecture(text)

    # ------------------------------------------------------------------
    # Regex helpers (fallback layer)
    # ------------------------------------------------------------------

    def _extract_text(self, pdf_path: Path) -> tuple[str, int]:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages), len(reader.pages)
        except Exception:
            data = pdf_path.read_bytes()
            return data.decode("utf-8", errors="ignore"), 0

    def _title(self, text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip()
            if 12 <= len(cleaned) <= 180 and not cleaned.lower().startswith(("arxiv", "abstract", "http")):
                return cleaned
        return "Untitled Computer Vision Paper"

    def _section(self, text: str, start: str, stops: list[str]) -> str:
        pattern = re.compile(rf"(?is)\b{re.escape(start)}\b\s*(.*)")
        match = pattern.search(text)
        if not match:
            return ""
        section = match.group(1)
        stop_positions = [section.lower().find(s.lower()) for s in stops if section.lower().find(s.lower()) > 80]
        if stop_positions:
            section = section[: min(stop_positions)]
        return section.strip()[:6000]

    def _sentences(self, text: str, limit: int) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
        return [s.strip() for s in sentences if len(s.strip()) > 30][:limit]

    def _architecture(self, text: str) -> list[str]:
        candidates = self._find_terms(
            text,
            ["encoder", "decoder", "attention", "transformer", "cnn", "resnet", "unet",
             "feature pyramid", "backbone", "fpn", "neck", "head", "pooling", "conv"]
        )
        return candidates or ["feature_extractor", "prediction_head"]

    def _detect_backbone(self, text: str) -> str | None:
        matches = self._find_terms(
            text,
            ["resnet", "resnet50", "resnet101", "efficientnet", "vit", "swin",
             "mobilenet", "vgg", "densenet", "convnext", "regnet"]
        )
        return matches[0] if matches else None

    def _find_terms(self, text: str, terms: list[str]) -> list[str]:
        lowered = text.lower()
        return [term for term in terms if term.lower() in lowered]

    def _hyperparameters(self, text: str) -> dict[str, str]:
        patterns = {
            "learning_rate": r"learning rate(?:\s+of)?\s*(?:=|:)?\s*([0-9.eE-]+)",
            "batch_size": r"batch size(?:\s+of)?\s*(?:=|:)?\s*(\d+)",
            "epochs": r"(?:trained for|epochs)\s*(?:=|:)?\s*(\d+)",
            "optimizer": r"\b(SGD|AdamW?|RMSProp|Adam)\b",
            "input_size": r"(?:input|image)\s+(?:size|resolution)\s*(?:of|=|:)?\s*(\d+\s*[x×]\s*\d+)",
        }
        values: dict[str, str] = {}
        for key, pattern in patterns.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                values[key] = m.group(1)
        return values

    @staticmethod
    def _sanitize_hyperparams(raw: dict | list | None) -> dict[str, str]:
        """Strip None values and coerce remaining to str for pydantic dict[str, str]."""
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items() if v is not None}

